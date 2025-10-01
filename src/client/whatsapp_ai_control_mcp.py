"""
WhatsApp AI Control with MCP Integration
Enhanced version that can work standalone or through MCP server
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, List, Optional
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Confirm
import re
from difflib import get_close_matches

# Import both standalone and MCP capabilities
from src.services.gemini import GeminiService
from src.mcp.client import WhatsAppMCPClient

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


class WhatsAppAIControlMCP:
    """WhatsApp AI Control with optional MCP integration"""

    def __init__(self, use_mcp: bool = False, mcp_url: str = "ws://localhost:8002"):
        self.console = Console()
        self.driver = None
        self.running = False
        self.authenticated = False
        self.auto_reply = False
        self.message_history = {}
        self.contact_list = []
        self.last_contact = None

        # MCP or Standalone mode
        self.use_mcp = use_mcp
        self.mcp_client = None
        self.gemini_service = None

        if use_mcp:
            self.console.print("[yellow]Initializing MCP mode...[/yellow]")
            self.mcp_client = WhatsAppMCPClient(mcp_url)
        else:
            self.console.print("[green]Initializing standalone mode...[/green]")
            self.gemini_service = GeminiService()

    def print_welcome(self):
        mode = "MCP Connected" if self.use_mcp else "Standalone"
        welcome_text = f"""# WhatsApp AI Control
**Mode:** {mode}

Natural language commands:
• Send [name] a message
• Read [name]'s messages
• Summarize chat with [name]
• What should I reply to [name]?
• Turn on/off auto-reply
• Type 'help' for more"""

        self.console.print(Panel(Markdown(welcome_text),
                                border_style="green" if not self.use_mcp else "cyan"))

    async def process_command(self, command: str) -> str:
        """Process command through MCP or directly"""
        try:
            # Special commands
            if command.lower() in ['help', '?', 'h']:
                return self.get_help_text()

            if command.lower() in ['quit', 'exit', 'stop', 'q', 'bye']:
                self.running = False
                return "Stopping application..."

            if command.lower() in ['status']:
                return await self.get_status()

            # Process through MCP or direct AI
            if self.use_mcp:
                return await self.process_command_mcp(command)
            else:
                return await self.process_command_direct(command)

        except Exception as e:
            logger.error(f"Error processing command: {e}")
            return f"Error: {str(e)}"

    async def process_command_mcp(self, command: str) -> str:
        """Process command through MCP server"""
        # Send command to MCP and wait for response
        response = await self.mcp_client.send_request_and_wait({
            "type": "whatsapp_ai_command",
            "command": command,
            "context": {
                "last_contact": self.last_contact,
                "contact_list": self.contact_list[:20]
            }
        }, timeout=10.0)

        if response:
            # Extract the actual content from the response
            content = response.get('content', {})

            # Check response type
            response_type = response.get('response_type')

            if response_type == 'whatsapp_command_result':
                action = content.get('action')

                # MCP returns the parsed action, now execute it locally with real WhatsApp
                if action == 'list':
                    # Use actual contact list
                    result = f"📋 **Your Contacts ({len(self.contact_list)}):**\n\n"
                    for i, contact in enumerate(self.contact_list[:15], 1):
                        result += f"  {i}. {contact}\n"
                    return result

                elif action == 'send':
                    contact = content.get('contact')
                    message = content.get('message')
                    # Execute real send
                    if self.send_message(contact, message):
                        return f"✅ **Sent to {contact}:**\n→ {message}"
                    else:
                        return f"❌ Failed to send to {contact}"

                elif action == 'read':
                    contact = content.get('contact')
                    count = content.get('count', 10)
                    query_type = content.get('query_type', 'all')
                    print(f"[DEBUG] Execute command - Reading messages for contact: '{contact}', count: {count}, query_type: {query_type}")

                    # Get real messages
                    messages = self.get_chat_messages(contact, count)
                    print(f"[DEBUG] get_chat_messages returned {len(messages)} messages")

                    if not messages:
                        return f"No messages found with {contact}"

                    # Handle specific query types
                    if query_type == 'last_from_contact':
                        # Get last message from the contact
                        incoming = [msg for msg in messages if msg["type"] == "incoming"]
                        if incoming:
                            last_msg = incoming[-1]
                            return f"📖 **Last message from {contact}:**\n→ {last_msg['text']}"
                        else:
                            return f"❌ No recent messages from {contact}"

                    elif query_type == 'position_from_contact':
                        # Get Nth last message from the contact
                        incoming = [msg for msg in messages if msg["type"] == "incoming"]
                        if incoming and len(incoming) >= position:
                            # -1 for last, -2 for second last, etc.
                            target_msg = incoming[-position]
                            position_text = "Last" if position == 1 else f"{self._ordinal(position)} last"
                            return f"📖 **{position_text} message from {contact}:**\n→ {target_msg['text']}"
                        else:
                            return f"❌ Not enough messages from {contact} (only {len(incoming)} found)"

                    elif query_type == 'last_from_me':
                        # Get last message I sent
                        outgoing = [msg for msg in messages if msg["type"] == "outgoing"]
                        if outgoing:
                            last_msg = outgoing[-1]
                            return f"📖 **Last message you sent to {contact}:**\n→ {last_msg['text']}"
                        else:
                            return f"❌ No recent messages sent to {contact}"

                    else:
                        # Show recent conversation with better formatting
                        result = f"📖 **Recent messages with {contact}:**\n\n"
                        for msg in messages[-5:]:
                            prefix = "  ← " if msg["type"] == "incoming" else "  → "
                            result += f"{prefix}{msg['text']}\n"
                        return result

                elif action == 'summary':
                    contact = content.get('contact')
                    # Get real messages for summary
                    messages = self.get_chat_messages(contact, 20)
                    if messages:
                        # Convert to text with sender info for summary
                        message_texts = [f"{msg['sender']}: {msg['text']}" for msg in messages]
                        # Use local Gemini for summary
                        if not self.gemini_service:
                            self.gemini_service = GeminiService()
                        summary = await self.gemini_service.generate_response(
                            prompt=f"Summarize this WhatsApp conversation in 3 bullet points:\n" + "\n".join(message_texts),
                            system_prompt="Create a concise summary."
                        )
                        return f"📊 **Summary of chat with {contact}:**\n{summary}"
                    else:
                        return f"No messages to summarize with {contact}"

                elif action == 'suggest':
                    contact = content.get('contact')
                    messages = self.get_chat_messages(contact, 10)
                    if messages:
                        # Get last few incoming messages from contact for context
                        incoming_msgs = [msg for msg in messages if msg["type"] == "incoming"]
                        context = "\n".join([msg["text"] for msg in incoming_msgs[-3:]]) if incoming_msgs else "No messages"

                        if not self.gemini_service:
                            self.gemini_service = GeminiService()
                        suggestions = await self.gemini_service.generate_response(
                            prompt=f"Suggest 3 good replies for this conversation:\n{context}",
                            system_prompt="Generate 3 brief, natural message suggestions."
                        )
                        return f"💡 **Reply suggestions for {contact}:**\n{suggestions}"
                    else:
                        return f"No conversation to analyze with {contact}"

                elif action == 'auto_on':
                    self.auto_reply = True
                    return "Auto-reply ON"

                elif action == 'auto_off':
                    self.auto_reply = False
                    return "Auto-reply OFF"

                else:
                    return str(content)

            elif response_type == 'ai_parse_error':
                return "Could not understand command. Try: 'Send John a message' or 'List contacts'"
            else:
                return response.get('content', 'Command processed')
        else:
            # MCP connection lost, switch to standalone
            print("[WARNING] MCP server not responding. Switching to standalone mode...")
            self.use_mcp = False

            # Initialize Gemini service if not already done
            if not self.gemini_service:
                self.gemini_service = GeminiService()

            # Process the command in standalone mode
            return await self.process_command_direct(command)

    def _ordinal(self, n: int) -> str:
        """Convert number to ordinal (1st, 2nd, 3rd, etc.)"""
        if 10 <= n % 100 <= 20:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
        return f"{n}{suffix}"

    async def process_command_direct(self, command: str) -> str:
        """Process command directly with local AI"""
        # Enhanced AI command parsing with context
        context_info = f"\nLast contact: {self.last_contact}" if self.last_contact else ""

        # Pre-process command for pronouns
        cmd_processed = command
        if self.last_contact and any(pronoun in command.lower()
                                    for pronoun in ['him', 'her', 'them', 'their', 'his']):
            cmd_processed = f"{command} (referring to {self.last_contact})"

        system_prompt = f"""You are an intelligent WhatsApp assistant.
Understand intent even with typos, slang, shortcuts.

Context:{context_info}
Known contacts: {', '.join(self.contact_list[:20]) if self.contact_list else 'Loading...'}

Parse commands flexibly and return JSON action:
{{"action": "send", "contact": "name", "message": "text"}}
{{"action": "list"}}
{{"action": "summary", "contact": "name"}}
{{"action": "suggest", "contact": "name"}}
{{"action": "read", "contact": "name"}}
{{"action": "auto_on"}} or {{"action": "auto_off"}}

Be VERY tolerant of typos and informal language. Return ONLY JSON."""

        ai_response = await self.gemini_service.generate_response(
            prompt=cmd_processed,
            system_prompt=system_prompt
        )

        # Try to find JSON in response
        json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
        if json_match:
            try:
                action_data = json.loads(json_match.group())
                return await self.execute_action(action_data)
            except json.JSONDecodeError:
                pass

        return "I can help with: Send messages, Read/Summarize chats, List contacts."

    async def execute_action(self, action_data: Dict[str, Any]) -> str:
        """Execute parsed action through MCP or directly"""
        if self.use_mcp:
            # Send action to MCP for execution
            await self.mcp_client.send_whatsapp_command(action_data)
            return f"Executing through MCP: {action_data.get('action')}"
        else:
            # Execute directly (existing implementation)
            return await self.execute_action_direct(action_data)

    async def execute_action_direct(self, action_data: Dict[str, Any]) -> str:
        """Execute action directly (existing WhatsApp automation)"""
        action = action_data.get("action", "")

        if action == "send":
            contact = action_data.get("contact", "")
            message = action_data.get("message", "")
            contact = self.find_best_contact_match(contact)
            self.last_contact = contact

            if self.send_message(contact, message):
                return f"✓ Sent to {contact}: '{message}'"
            else:
                return f"Failed to send to {contact}"

        elif action == "list":
            if self.use_mcp:
                contacts = await self.mcp_client.get_contacts()
            else:
                chats = self.get_chats()
                self.contact_list = [chat['name'] for chat in chats]
                contacts = self.contact_list

            result = f"Contacts ({len(contacts)}):\n"
            for i, contact in enumerate(contacts[:15], 1):
                result += f"{i}. {contact}\n"
            return result

        elif action == "read":
            contact = action_data.get("contact", "")
            contact = self.find_best_contact_match(contact)
            self.last_contact = contact

            if self.use_mcp:
                messages = await self.mcp_client.get_messages(contact, 10)
            else:
                messages = self.get_chat_messages(contact, 10)

            if not messages:
                return f"No messages found with {contact}"

            result = f"Messages with {contact}:\n"
            for msg in messages[-5:]:
                result += f"• {msg}\n"
            return result

        elif action == "summary":
            contact = action_data.get("contact", "")
            contact = self.find_best_contact_match(contact)
            self.last_contact = contact

            # Get messages to summarize
            messages = self.get_chat_messages(contact, 20)

            if not messages:
                return f"No messages found with {contact} to summarize"

            # Create a summary using AI
            messages_text = "\n".join(messages[-10:])  # Last 10 messages for summary

            summary_prompt = f"""Summarize this WhatsApp conversation with {contact}:
{messages_text}

Provide a brief, helpful summary of the key points discussed."""

            try:
                summary = await self.gemini_service.generate_response(
                    prompt=summary_prompt,
                    system_prompt="You are a helpful assistant that summarizes conversations concisely."
                )
                return f"Summary of chat with {contact}:\n{summary}"
            except:
                # Fallback to simple last messages display
                result = f"Last 5 messages with {contact}:\n"
                for msg in messages[-5:]:
                    result += f"• {msg}\n"
                return result

        elif action == "suggest":
            contact = action_data.get("contact", "")
            contact = self.find_best_contact_match(contact)
            self.last_contact = contact

            # Get recent messages for context
            messages = self.get_chat_messages(contact, 10)

            if not messages:
                return f"No conversation found with {contact}"

            # Generate reply suggestion
            context = "\n".join(messages[-5:])
            suggest_prompt = f"""Based on this conversation with {contact}, suggest a thoughtful reply:
{context}

Suggest a natural, appropriate response."""

            try:
                suggestion = await self.gemini_service.generate_response(
                    prompt=suggest_prompt,
                    system_prompt="You are helping compose a WhatsApp reply. Be friendly and natural."
                )
                return f"Suggested reply to {contact}:\n→ {suggestion}"
            except:
                return f"Could not generate suggestion for {contact}"

        elif action == "auto_on":
            self.auto_reply = True
            return "Auto-reply ON"

        elif action == "auto_off":
            self.auto_reply = False
            return "Auto-reply OFF"

        return "Unknown action"

    async def get_status(self) -> str:
        """Get current system status"""
        mode = "MCP Connected" if self.use_mcp else "Standalone"
        auto = "ON" if self.auto_reply else "OFF"
        connected = "Yes" if self.authenticated else "No"

        if self.use_mcp and self.mcp_client:
            mcp_status = "Connected" if self.mcp_client.connection_established else "Disconnected"
        else:
            mcp_status = "N/A"

        return f"""System Status:
• Mode: {mode}
• MCP Server: {mcp_status}
• WhatsApp: {connected}
• Auto-Reply: {auto}
• Last Contact: {self.last_contact or 'None'}
• Contacts Loaded: {len(self.contact_list)}"""

    def get_help_text(self) -> str:
        """Get help text"""
        return """Commands:
• Send [name] a message
• List contacts
• Read [name]'s messages
• Summarize chat with [name]
• What should I reply to [name]?
• Turn on/off auto-reply
• status - Show system status
• quit - Exit"""

    def find_best_contact_match(self, name: str) -> Optional[str]:
        """Find best matching contact name"""
        if not self.contact_list:
            return name

        # Exact match first
        for contact in self.contact_list:
            if contact.lower() == name.lower():
                return contact

        # Fuzzy match
        matches = get_close_matches(name, self.contact_list, n=1, cutoff=0.6)
        if matches:
            return matches[0]

        # Partial match
        name_lower = name.lower()
        for contact in self.contact_list:
            if name_lower in contact.lower() or contact.lower() in name_lower:
                return contact

        return name

    # Include all the Selenium-based methods from original whatsapp_ai_control.py
    # (setup_driver, wait_for_login, get_chats, get_chat_messages, send_message, etc.)
    # These remain the same as they handle the actual WhatsApp Web automation

    def setup_driver(self):
        """Setup Chrome driver for WhatsApp Web"""
        import tempfile
        temp_dir = tempfile.mkdtemp(prefix="whatsapp_session_")

        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument(f"--user-data-dir={temp_dir}")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options
        )
        self.driver.get("https://web.whatsapp.com")

    def wait_for_login(self):
        """Wait for WhatsApp Web login"""
        try:
            WebDriverWait(self.driver, 120).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[id='side']"))
            )
            self.authenticated = True
            self.console.print("[green]Successfully logged in![/green]")
            return True
        except:
            return False

    def get_chats(self) -> List[Dict[str, Any]]:
        """Get list of WhatsApp chats"""
        chats = []
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='listitem']"))
            )

            chat_elements = self.driver.find_elements(By.CSS_SELECTOR, "div[role='listitem']")

            # Get ALL chats, not just first 20
            for chat in chat_elements:
                try:
                    name = "Unknown"
                    name_selectors = [
                        "span[dir='auto'][class*='ggj6brxn']",
                        "span[title]",
                        "span[dir='auto']"
                    ]

                    for selector in name_selectors:
                        try:
                            name_element = chat.find_element(By.CSS_SELECTOR, selector)
                            if name_element and name_element.text:
                                name = name_element.get_attribute('title') or name_element.text
                                break
                        except:
                            continue

                    last_message = ""
                    try:
                        msg_elements = chat.find_elements(By.CSS_SELECTOR, "span[class*='_11JPr'], span[dir='ltr']")
                        if msg_elements:
                            last_message = msg_elements[-1].text
                    except:
                        pass

                    chats.append({
                        "name": name,
                        "last_message": last_message,
                        "element": chat
                    })
                except:
                    continue

        except Exception as e:
            logger.error(f"Error getting chats: {e}")

        return chats

    def get_chat_messages(self, chat_name: str, count: int = 20) -> List[Dict[str, str]]:
        """Get recent messages from a specific chat with sender information"""
        import time
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.common.action_chains import ActionChains

        messages = []
        try:
            print(f"[DEBUG] Looking for chat: '{chat_name}'")

            # First, get all chats and look for the target chat
            chats = self.get_chats()
            chat_found = False
            chat_element = None

            print(f"[DEBUG] Checking {len(chats)} chats...")

            # Try exact match first, then fuzzy match
            for chat in chats:
                if chat["name"].lower() == chat_name.lower():
                    print(f"[DEBUG] Found exact match: {chat['name']}")
                    chat_element = chat["element"]
                    chat_found = True
                    break

            # If no exact match, try fuzzy match
            if not chat_found:
                for chat in chats:
                    if chat_name.lower() in chat["name"].lower() or chat["name"].lower() in chat_name.lower():
                        print(f"[DEBUG] Found fuzzy match: {chat['name']} for query '{chat_name}'")
                        chat_element = chat["element"]
                        chat_found = True
                        break

            if not chat_found:
                print(f"[DEBUG] Chat '{chat_name}' not found in chat list")
                return messages

            # Try to click the chat element with better error handling
            try:
                # First, try to dismiss any popups or overlays
                try:
                    body = self.driver.find_element(By.TAG_NAME, "body")
                    body.send_keys(Keys.ESCAPE)
                    time.sleep(0.2)
                except:
                    pass

                # Scroll element into view first
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", chat_element)
                time.sleep(0.5)

                # Try regular click
                chat_element.click()
                print("[DEBUG] Regular click succeeded")
            except Exception as e:
                print(f"[DEBUG] Regular click failed: {e}")
                try:
                    # Try JavaScript click as fallback
                    self.driver.execute_script("arguments[0].click();", chat_element)
                    print("[DEBUG] JavaScript click succeeded")
                except Exception as e2:
                    print(f"[DEBUG] JavaScript click also failed: {e2}")
                    # Try using ActionChains
                    try:
                        actions = ActionChains(self.driver)
                        actions.move_to_element(chat_element).click().perform()
                        print("[DEBUG] ActionChains click succeeded")
                    except Exception as e3:
                        print(f"[DEBUG] ActionChains click failed: {e3}")
                        return messages

            # Wait for messages to load
            time.sleep(2)

            print("[DEBUG] Looking for message elements...")

            # Get all message containers to maintain chronological order
            message_containers = self.driver.find_elements(By.CSS_SELECTOR,
                "div[class*='message-in'], div[class*='message-out']")

            print(f"[DEBUG] Found {len(message_containers)} message containers")

            # Process last N message containers
            for container in message_containers[-count:]:
                try:
                    # Determine if it's incoming or outgoing
                    is_incoming = 'message-in' in container.get_attribute('class')

                    # Get the actual message text
                    text_elements = container.find_elements(By.CSS_SELECTOR,
                        "span[class*='selectable-text']")

                    for elem in text_elements:
                        text = elem.text.strip()
                        if text and len(text) > 1:
                            # Filter out timestamps and UI elements
                            if not any(skip in text.lower() for skip in ['type a message', 'search', 'online', 'typing']):
                                messages.append({
                                    "text": text,
                                    "sender": chat_name if is_incoming else "You",
                                    "type": "incoming" if is_incoming else "outgoing"
                                })
                                sender_type = "incoming" if is_incoming else "outgoing"
                                print(f"[DEBUG] Added {sender_type} message: {text[:50]}..." if len(text) > 50 else f"[DEBUG] Added {sender_type} message: {text}")
                                break  # Only take the first valid text from each container
                except Exception as e:
                    print(f"[DEBUG] Error processing message container: {e}")
                    continue

            print(f"[DEBUG] Total messages collected: {len(messages)}")

        except Exception as e:
            print(f"[DEBUG] Error in get_chat_messages: {e}")
            logger.error(f"Error getting messages: {e}")

        return messages

    def get_chat_messages_simple(self, chat_name: str, count: int = 20) -> List[str]:
        """Get recent messages as simple text list (backward compatibility)"""
        structured_messages = self.get_chat_messages(chat_name, count)
        return [msg["text"] for msg in structured_messages]

    def send_message(self, chat_name: str, message: str) -> bool:
        """Send a message to a WhatsApp chat with improved contact matching"""
        try:
            import time
            chat_found = False

            # First, try to find contact in recent chats
            chats = self.get_chats()

            # Try exact match first
            for chat in chats:
                if chat["name"].lower() == chat_name.lower():
                    logger.info(f"Found exact match for '{chat_name}': {chat['name']}")
                    chat["element"].click()
                    chat_found = True
                    break

            # If not found in recent chats, use search
            if not chat_found:
                logger.info(f"Contact '{chat_name}' not in recent chats, using search...")
                # Search for contact
                search_box = self.driver.find_element(By.CSS_SELECTOR, "div[contenteditable='true'][data-tab='3']")
                search_box.click()
                search_box.send_keys(Keys.ESCAPE)
                time.sleep(0.5)

                search_box.click()
                search_box.send_keys(Keys.CONTROL + "a")
                search_box.send_keys(Keys.DELETE)
                search_box.send_keys(chat_name)
                time.sleep(1)

                results = self.driver.find_elements(By.CSS_SELECTOR, "div[role='listitem']")

                # Try to find exact match in search results
                for result in results:
                    try:
                        name_elem = result.find_element(By.CSS_SELECTOR, "span[title]")
                        if name_elem:
                            result_name = name_elem.get_attribute('title') or name_elem.text
                            if result_name.lower() == chat_name.lower():
                                logger.info(f"Found exact match in search: {result_name}")
                                result.click()
                                chat_found = True
                                break
                    except:
                        continue

                # If no exact match, click first result
                if not chat_found and results:
                    logger.info(f"No exact match, selecting first search result for '{chat_name}'")
                    results[0].click()
                elif not results:
                    logger.error(f"Contact '{chat_name}' not found")
                    return False

            time.sleep(1)

            # Find message input box
            input_selectors = [
                "div[contenteditable='true'][data-tab='10']",
                "footer div[contenteditable='true']"
            ]

            input_box = None
            for selector in input_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        input_box = elements[-1]
                        break
                except:
                    continue

            if input_box:
                input_box.click()
                input_box.clear()
                input_box.send_keys(message)
                input_box.send_keys(Keys.ENTER)
                logger.info(f"Message sent to {chat_name}")
                return True
            else:
                logger.error("Could not find message input box")
                return False

        except Exception as e:
            logger.error(f"Error sending message: {e}")

        return False

    async def monitor_with_commands(self):
        """Monitor messages and handle commands"""
        self.console.print("\n[green]Ready. Type commands:[/green]")

        mcp_task = None
        if self.use_mcp:
            # Start MCP message receiver
            mcp_task = asyncio.create_task(self.mcp_client.receive_messages())

        import msvcrt
        input_buffer = ""
        cursor_pos = 0

        try:
            while self.running and self.authenticated:
                try:
                    # Check for keyboard input
                    if msvcrt.kbhit():
                        char = msvcrt.getch()

                        # Check for special keys (arrow keys, function keys, etc.)
                        if char in [b'\x00', b'\xe0']:  # Special key prefix
                            # Get the second byte for special keys
                            special = msvcrt.getch()

                            if special == b'H':  # Up arrow
                                # Could implement command history here
                                continue
                            elif special == b'P':  # Down arrow
                                # Could implement command history here
                                continue
                            elif special == b'K':  # Left arrow
                                if cursor_pos > 0:
                                    cursor_pos -= 1
                                    print('\b', end='', flush=True)
                                continue
                            elif special == b'M':  # Right arrow
                                if cursor_pos < len(input_buffer):
                                    print(input_buffer[cursor_pos], end='', flush=True)
                                    cursor_pos += 1
                                continue
                            else:
                                # Ignore other special keys
                                continue

                        elif char == b'\r':  # Enter key
                            if input_buffer:
                                self.console.print(f"\n[cyan]You:[/cyan] {input_buffer}")
                                response = await self.process_command(input_buffer)
                                self.console.print(Panel(Markdown(response),
                                                        border_style="green"))
                                input_buffer = ""
                                cursor_pos = 0
                                print("> ", end="", flush=True)
                        elif char == b'\x08':  # Backspace
                            if input_buffer and cursor_pos > 0:
                                # Remove character at cursor position
                                input_buffer = input_buffer[:cursor_pos-1] + input_buffer[cursor_pos:]
                                cursor_pos -= 1
                                # Redraw the line from cursor position
                                print('\b', end='')
                                print(input_buffer[cursor_pos:] + ' ', end='')
                                print('\b' * (len(input_buffer) - cursor_pos + 1), end='', flush=True)
                        elif char == b'\x03':  # Ctrl+C
                            self.running = False
                            break
                        else:
                            try:
                                decoded = char.decode('utf-8')
                                # Insert character at cursor position
                                input_buffer = input_buffer[:cursor_pos] + decoded + input_buffer[cursor_pos:]
                                # Print the new character and everything after it
                                print(input_buffer[cursor_pos:], end='')
                                cursor_pos += 1
                                # Move cursor back to correct position
                                if cursor_pos < len(input_buffer):
                                    print('\b' * (len(input_buffer) - cursor_pos), end='', flush=True)
                                else:
                                    print('', end='', flush=True)
                            except:
                                pass

                    # Check if MCP connection is still alive
                    if self.use_mcp and mcp_task and mcp_task.done():
                        # MCP task finished unexpectedly
                        self.console.print("\n[yellow]MCP connection lost. Switching to standalone mode.[/yellow]")
                        self.use_mcp = False
                        if not self.gemini_service:
                            self.gemini_service = GeminiService()

                    await asyncio.sleep(0.01)

                except Exception as e:
                    logger.error(f"Error in monitor loop: {e}")
                    await asyncio.sleep(0.5)

        finally:
            if mcp_task and not mcp_task.done():
                mcp_task.cancel()
                try:
                    await mcp_task
                except asyncio.CancelledError:
                    pass

    async def run(self):
        """Main run loop"""
        self.print_welcome()

        # Connect to MCP if enabled
        if self.use_mcp:
            connected = await self.mcp_client.connect()
            if not connected:
                self.console.print("[red]Failed to connect to MCP server[/red]")
                self.console.print("[yellow]Falling back to standalone mode[/yellow]")
                self.use_mcp = False
                self.gemini_service = GeminiService()

        self.console.print("[cyan]Opening WhatsApp Web...[/cyan]")
        self.setup_driver()

        if self.wait_for_login():
            self.running = True

            # Load contacts
            self.console.print("[cyan]Loading contacts...[/cyan]")
            chats = self.get_chats()
            self.contact_list = [chat['name'] for chat in chats]
            self.console.print(f"[green]Loaded {len(self.contact_list)} contacts[/green]")

            # Share contact list with MCP if connected
            if self.use_mcp:
                await self.mcp_client.send_message({
                    "type": "contact_list_update",
                    "contacts": self.contact_list
                })

            # Ask about auto-reply
            self.auto_reply = Confirm.ask("\nEnable auto-reply?", default=False)

            print("> ", end="", flush=True)

            try:
                await self.monitor_with_commands()
            except KeyboardInterrupt:
                self.console.print("\n[yellow]Stopping...[/yellow]")

        # Cleanup
        if self.driver:
            self.driver.quit()

        if self.use_mcp and self.mcp_client:
            await self.mcp_client.disconnect()

        self.console.print("[green]Goodbye![/green]")


def main():
    """Main entry point with MCP option"""
    import sys

    # Check for MCP flag
    use_mcp = "--mcp" in sys.argv or "-m" in sys.argv

    if use_mcp:
        print("Starting WhatsApp AI Control with MCP integration...")
    else:
        print("Starting WhatsApp AI Control in standalone mode...")

    client = WhatsAppAIControlMCP(use_mcp=use_mcp)

    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        print("\nExiting...")


if __name__ == "__main__":
    main()