import asyncio
import json
import logging
import sys
import select
from typing import Optional, Dict, Any, List
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.prompt import Prompt, Confirm
import re

from src.utils.config import settings
from src.services.database import DatabaseService
from src.services.gemini import GeminiService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WhatsAppAIControl:
    def __init__(self):
        self.console = Console()
        self.driver = None
        self.db_service = DatabaseService()
        self.gemini_service = GeminiService()
        self.running = False
        self.authenticated = False
        self.auto_reply = False
        self.message_history = {}
        self.last_command_time = datetime.now()

    def print_welcome(self):
        welcome_text = """
# WhatsApp AI Control System

## How to Use:
1. **During monitoring**, just type your command and press Enter
2. **No need for special modes** - AI understands your intent
3. **Natural language** - Talk naturally to control WhatsApp

## Example Commands:
- "Send a message to John saying I'll be there soon"
- "List my contacts"
- "Summarize my chat with Sarah"
- "What should I reply to Mike?"
- "Read last 5 messages from Emma"
- "Turn on auto-reply"
- "help" - Show command examples
- "quit" - Exit application
        """
        self.console.print(Panel(Markdown(welcome_text), title="WhatsApp AI Control", border_style="green"))

    def setup_driver(self):
        """Setup Chrome driver for WhatsApp Web"""
        import tempfile
        temp_dir = tempfile.mkdtemp(prefix="whatsapp_session_")

        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument(f"--user-data-dir={temp_dir}")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        chrome_options.add_experimental_option("detach", True)

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options
        )
        self.driver.get("https://web.whatsapp.com")
        logger.info("Chrome browser opened")

    def wait_for_login(self):
        """Wait for WhatsApp Web login"""
        try:
            try:
                side_panel = self.driver.find_element(By.CSS_SELECTOR, "div[id='side']")
                if side_panel:
                    self.console.print("[green]Already logged in to WhatsApp Web![/green]")
                    self.authenticated = True
                    return True
            except:
                pass

            qr_element = WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "canvas[aria-label*='Scan'], div[data-ref]"))
            )
            self.console.print("\n[yellow]QR Code detected! Scan with WhatsApp mobile app[/yellow]")

            WebDriverWait(self.driver, 120).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[id='side']"))
            )

            self.authenticated = True
            self.console.print("[green]Successfully logged in![/green]")
            return True

        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False

    def get_chats(self) -> List[Dict[str, Any]]:
        """Get list of WhatsApp chats with better error handling"""
        chats = []
        try:
            # Wait for chat list to be present
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='listitem']"))
            )

            # Re-find elements to avoid stale references
            import time
            time.sleep(0.5)  # Small delay to ensure DOM is stable

            chat_elements = self.driver.find_elements(By.CSS_SELECTOR, "div[role='listitem']")

            for chat in chat_elements[:20]:
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
                            if name_element:
                                # Try title attribute first, then text
                                title_attr = name_element.get_attribute('title')
                                if title_attr:
                                    name = title_attr
                                    break
                                elif name_element.text:
                                    name = name_element.text
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

                    if name != "Unknown":  # Only add chats with valid names
                        chats.append({
                            "name": name,
                            "last_message": last_message,
                            "element": chat
                        })
                except Exception as inner_e:
                    # Log but continue processing other chats
                    logger.debug(f"Error processing chat element: {inner_e}")
                    continue

        except TimeoutException:
            logger.warning("Timeout waiting for chat list to load")
        except Exception as e:
            logger.error(f"Error getting chats: {e}")

        return chats

    def get_chat_messages(self, chat_name: str, count: int = 20) -> List[Dict[str, str]]:
        """Get recent messages from a specific chat with sender information and timestamps"""
        messages = []
        try:
            chats = self.get_chats()
            chat_found = False

            for chat in chats:
                if chat["name"].lower() == chat_name.lower():
                    chat["element"].click()
                    chat_found = True
                    break

            if not chat_found:
                return messages

            import time
            time.sleep(2)

            # Get all message containers to maintain chronological order
            message_containers = self.driver.find_elements(By.CSS_SELECTOR,
                "div[class*='message-in'], div[class*='message-out']")

            # Process last N message containers
            for idx, container in enumerate(message_containers[-count:]):
                try:
                    # Determine if it's incoming or outgoing
                    is_incoming = 'message-in' in container.get_attribute('class')

                    # Try to get timestamp
                    timestamp = None
                    try:
                        time_elements = container.find_elements(By.CSS_SELECTOR,
                            "span[dir='auto'][class*='_11JPr'], span[class*='_1LKHN']")
                        if time_elements:
                            timestamp = time_elements[-1].text
                    except:
                        pass

                    # Get the actual message text
                    text_elements = container.find_elements(By.CSS_SELECTOR,
                        "span[class*='selectable-text']")

                    for elem in text_elements:
                        if elem.text and elem.text.strip():
                            messages.append({
                                "text": elem.text.strip(),
                                "sender": chat_name if is_incoming else "You",
                                "type": "incoming" if is_incoming else "outgoing",
                                "timestamp": timestamp,
                                "index": idx  # Track position for ordering
                            })
                            break  # Only take the first valid text from each container
                except:
                    continue

        except Exception as e:
            logger.error(f"Error getting messages: {e}")

        return messages

    def get_chat_messages_simple(self, chat_name: str, count: int = 20) -> List[str]:
        """Get recent messages as simple text list (backward compatibility)"""
        structured_messages = self.get_chat_messages(chat_name, count)
        return [msg["text"] for msg in structured_messages]

    def send_message(self, chat_name: str, message: str) -> bool:
        """Send a message to a WhatsApp chat with improved contact matching"""
        try:
            chat_found = False
            chats = self.get_chats()

            # First try exact match
            for chat in chats:
                if chat["name"].lower() == chat_name.lower():
                    logger.info(f"Found exact match for '{chat_name}': {chat['name']}")
                    chat["element"].click()
                    chat_found = True
                    break

            # If no exact match, try partial match (but be careful)
            if not chat_found:
                for chat in chats:
                    # Check if the search term is contained in the contact name
                    # but avoid false matches (e.g., "Rin" matching "Rinku")
                    if chat_name.lower() in chat["name"].lower() and len(chat_name) >= 3:
                        logger.info(f"Found partial match for '{chat_name}': {chat['name']}")
                        chat["element"].click()
                        chat_found = True
                        break

            # If still not found, use search
            if not chat_found:
                logger.info(f"Contact '{chat_name}' not in recent chats, using search...")
                search_box = self.driver.find_element(By.CSS_SELECTOR, "div[contenteditable='true'][data-tab='3']")
                search_box.click()
                search_box.clear()
                search_box.send_keys(chat_name)

                import time
                time.sleep(2)

                # Look for search results
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
                    time.sleep(1)
                elif not results:
                    logger.error(f"Contact '{chat_name}' not found")
                    return False

            import time
            time.sleep(1)

            input_selectors = [
                "div[contenteditable='true'][data-tab='10']",
                "div[contenteditable='true'][data-tab='1']",
                "footer div[contenteditable='true']",
                "div[contenteditable='true']"
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

            if not input_box:
                logger.error("Could not find message input")
                return False

            input_box.click()
            input_box.clear()
            input_box.send_keys(message)
            input_box.send_keys(Keys.ENTER)

            logger.info(f"Message sent to {chat_name}")
            return True

        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False

    async def process_command(self, command: str) -> str:
        """Process natural language command with Gemini AI"""
        try:
            # Special commands
            if command.lower() in ['help', '?']:
                return """**Command Examples:**
• Send a message: "Send John a message saying hello"
• List contacts: "Show me my contacts" or "list"
• Read messages: "What did Sarah say?" or "Read Emma's messages"
• Summarize: "Summarize my chat with Mike"
• Get suggestions: "What should I reply to David?"
• Auto-reply: "Turn on auto-reply" or "disable auto-reply"
• Exit: "quit" or "exit"
"""

            if command.lower() in ['quit', 'exit', 'stop']:
                self.running = False
                return "Stopping application..."

            # AI command parsing
            system_prompt = """You are a WhatsApp control assistant. Parse the user's command and respond with a JSON action.

Actions:
1. {"action": "send", "contact": "name", "message": "text"}
2. {"action": "list"}
3. {"action": "summary", "contact": "name", "count": 20}
4. {"action": "suggest", "contact": "name"}
5. {"action": "read", "contact": "name", "count": 10, "query_type": "all|last_from_contact|last_from_me|position_from_contact", "position": N}
   - Use query_type: "last_from_contact" when user asks for last message FROM a contact
   - Use query_type: "last_from_me" when user asks for last message TO a contact
   - Use query_type: "position_from_contact" when user asks for Nth last message (second last, third last, etc.)
   - Use query_type: "all" for general message reading
   - position: 1 for last, 2 for second last, 3 for third last, etc.
6. {"action": "auto_on"} or {"action": "auto_off"}
7. {"action": "status"}
8. {"action": "error", "message": "explanation"}

Examples:
- "What did John say last?" -> {"action": "read", "contact": "John", "count": 20, "query_type": "last_from_contact"}
- "What is the second last message of mehul?" -> {"action": "read", "contact": "Mehul", "count": 20, "query_type": "position_from_contact", "position": 2}
- "What was mehul's third last message?" -> {"action": "read", "contact": "Mehul", "count": 20, "query_type": "position_from_contact", "position": 3}
- "What did I last send to Sarah?" -> {"action": "read", "contact": "Sarah", "count": 20, "query_type": "last_from_me"}
- "Show messages with Emma" -> {"action": "read", "contact": "Emma", "count": 10, "query_type": "all"}

Return ONLY the JSON, no other text."""

            ai_response = await self.gemini_service.generate_response(
                prompt=command,
                system_prompt=system_prompt
            )

            json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
            if json_match:
                action_data = json.loads(json_match.group())
                return await self.execute_action(action_data)
            else:
                # If AI doesn't return JSON, try to handle the command directly
                return await self.handle_direct_command(command)

        except Exception as e:
            logger.error(f"Error processing command: {e}")
            return f"Error: {str(e)}"

    async def execute_action(self, action_data: Dict[str, Any]) -> str:
        """Execute the parsed AI action"""
        action = action_data.get("action", "")

        if action == "send":
            contact = action_data.get("contact", "")
            message = action_data.get("message", "")

            if self.send_message(contact, message):
                return f"✅ Sent to {contact}: '{message}'"
            else:
                return f"❌ Failed to send to {contact}"

        elif action == "list":
            chats = self.get_chats()
            if not chats:
                return "No chats found."

            result = "📋 **Your Contacts:**\n"
            for i, chat in enumerate(chats[:15], 1):
                result += f"{i}. {chat['name']}\n"
            return result

        elif action == "summary":
            contact = action_data.get("contact", "")
            messages = self.get_chat_messages(contact, 20)

            if not messages:
                return f"No messages found with {contact}"

            # Convert to text for summary
            message_texts = [f"{msg['sender']}: {msg['text']}" for msg in messages]
            summary_prompt = f"Summarize in 3 bullet points:\n" + "\n".join(message_texts)
            summary = await self.gemini_service.generate_response(
                prompt=summary_prompt,
                system_prompt="Create a concise summary."
            )
            return f"📊 **Summary of {contact}:**\n{summary}"

        elif action == "suggest":
            contact = action_data.get("contact", "")
            messages = self.get_chat_messages(contact, 10)

            # Get last few incoming messages from contact for context
            incoming_msgs = [msg for msg in messages if msg["type"] == "incoming"]
            context = "\n".join([msg["text"] for msg in incoming_msgs[-3:]]) if incoming_msgs else "No messages"

            suggestions = await self.gemini_service.generate_response(
                prompt=f"Suggest 3 replies for:\n{context}",
                system_prompt="Generate 3 brief message suggestions."
            )
            return f"💡 **Suggestions for {contact}:**\n{suggestions}"

        elif action == "read":
            contact = action_data.get("contact", "")
            count = action_data.get("count", 10)
            query_type = action_data.get("query_type", "all")
            position = action_data.get("position", 1)  # For positional queries
            messages = self.get_chat_messages(contact, count)

            if not messages:
                return f"No messages with {contact}"

            # Handle specific query types
            if query_type == "last_from_contact":
                # Get last message from the contact
                incoming = [msg for msg in messages if msg["type"] == "incoming"]
                if incoming:
                    last_msg = incoming[-1]
                    return f"📖 **Last message from {contact}:** {last_msg['text']}"
                else:
                    return f"No recent messages from {contact}"

            elif query_type == "position_from_contact":
                # Get Nth last message from the contact
                incoming = [msg for msg in messages if msg["type"] == "incoming"]
                if incoming and len(incoming) >= position:
                    # -1 for last, -2 for second last, etc.
                    target_msg = incoming[-position]
                    position_text = "last" if position == 1 else f"{self._ordinal(position)} last"
                    return f"📖 **{position_text.capitalize()} message from {contact}:** {target_msg['text']}"
                else:
                    return f"Not enough messages from {contact} (only {len(incoming)} found)"

            elif query_type == "last_from_me":
                # Get last message I sent
                outgoing = [msg for msg in messages if msg["type"] == "outgoing"]
                if outgoing:
                    last_msg = outgoing[-1]
                    return f"📖 **Last message you sent to {contact}:** {last_msg['text']}"
                else:
                    return f"No recent messages sent to {contact}"

            else:
                # Show recent conversation with better formatting
                result = f"📖 **Recent messages with {contact}:**\n"
                for msg in messages[-5:]:
                    prefix = "← " if msg["type"] == "incoming" else "→ "
                    time_str = f" [{msg['timestamp']}]" if msg.get('timestamp') else ""
                    result += f"{prefix}{msg['text']}{time_str}\n"
                return result

        elif action == "auto_on":
            self.auto_reply = True
            return "🤖 Auto-reply enabled"

        elif action == "auto_off":
            self.auto_reply = False
            return "🤖 Auto-reply disabled"

        elif action == "status":
            status = "enabled" if self.auto_reply else "disabled"
            return f"Status: Auto-reply is {status}"

        elif action == "error":
            return action_data.get("message", "Command not understood")

        return "Unknown action"

    def _ordinal(self, n: int) -> str:
        """Convert number to ordinal (1st, 2nd, 3rd, etc.)"""
        if 10 <= n % 100 <= 20:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
        return f"{n}{suffix}"

    async def handle_direct_command(self, command: str) -> str:
        """Handle commands that don't need AI parsing"""
        cmd_lower = command.lower()

        if "list" in cmd_lower or "contacts" in cmd_lower:
            return await self.execute_action({"action": "list"})

        elif "auto" in cmd_lower and "on" in cmd_lower:
            return await self.execute_action({"action": "auto_on"})

        elif "auto" in cmd_lower and "off" in cmd_lower:
            return await self.execute_action({"action": "auto_off"})

        elif "status" in cmd_lower:
            return await self.execute_action({"action": "status"})

        else:
            # Try to understand with AI
            return "I didn't understand. Try: 'Send John a message' or 'List contacts'"

    async def monitor_with_commands(self):
        """Monitor messages and handle commands"""
        last_messages = {}

        self.console.print("\n[green]Monitoring Active - Type commands anytime![/green]")
        self.console.print("[dim]Examples: 'Send John a message saying hi' or 'list contacts'[/dim]\n")

        # Non-blocking input setup
        import msvcrt
        input_buffer = ""

        # Counter for periodic chat checking
        check_counter = 0
        check_interval = 200  # Check chats every 200 iterations (0.01 seconds * 200 = 2 seconds)

        while self.running and self.authenticated:
            try:
                # Check for keyboard input (Windows) - this runs every iteration
                if msvcrt.kbhit():
                    char = msvcrt.getch()
                    if char == b'\r':  # Enter key
                        if input_buffer:
                            self.console.print(f"\n[cyan]You:[/cyan] {input_buffer}")
                            response = await self.process_command(input_buffer)
                            self.console.print(Panel(Markdown(response), border_style="green"))
                            input_buffer = ""
                            print("\n> ", end="", flush=True)
                    elif char == b'\x08':  # Backspace
                        if input_buffer:
                            input_buffer = input_buffer[:-1]
                            print("\b \b", end="", flush=True)
                    elif char == b'\x03':  # Ctrl+C
                        self.running = False
                        break
                    else:
                        try:
                            decoded = char.decode('utf-8')
                            input_buffer += decoded
                            print(decoded, end="", flush=True)
                        except:
                            pass

                # Monitor messages only periodically to avoid blocking input
                check_counter += 1
                if check_counter >= check_interval:
                    check_counter = 0

                    # Run chat checking in background to not block input
                    chats = self.get_chats()

                    for chat in chats:
                        chat_name = chat["name"]
                        last_msg = chat.get("last_message", "")

                        if chat_name not in self.message_history:
                            self.message_history[chat_name] = []

                        if last_msg and chat_name not in last_messages:
                            last_messages[chat_name] = last_msg
                        elif last_msg and last_messages.get(chat_name) != last_msg:
                            # New message
                            self.message_history[chat_name].append({
                                "time": datetime.now(),
                                "message": last_msg
                            })

                            print("\r" + " " * 50 + "\r", end="")  # Clear input line
                            self.console.print(f"\n[yellow]New message from {chat_name}:[/yellow] {last_msg}")

                            if self.auto_reply:
                                # Only auto-reply to actual incoming messages, not our own
                                last_structured = self.get_chat_messages(chat_name, 1)
                                if last_structured and last_structured[-1]["type"] == "incoming":
                                    ai_response = await self.gemini_service.generate_response(
                                        prompt=last_msg,
                                        system_prompt=f"Reply briefly to this WhatsApp message from {chat_name}."
                                    )
                                    if self.send_message(chat_name, ai_response):
                                        self.console.print(f"[green]Auto-replied:[/green] {ai_response}")

                            last_messages[chat_name] = last_msg
                            print("\n> " + input_buffer, end="", flush=True)  # Restore input line

                # Very short sleep for maximum input responsiveness
                await asyncio.sleep(0.01)

            except Exception as e:
                logger.error(f"Error: {e}")
                await asyncio.sleep(0.5)

    async def run(self):
        """Main run loop"""
        self.print_welcome()

        self.console.print("[cyan]Opening WhatsApp Web...[/cyan]")
        self.setup_driver()

        if self.wait_for_login():
            self.running = True

            # Show contacts
            chats = self.get_chats()
            self.console.print(f"\n[green]Found {len(chats)} contacts[/green]")

            # Ask about auto-reply
            self.auto_reply = Confirm.ask("Enable auto-reply?", default=False)

            print("\n> ", end="", flush=True)  # Initial prompt

            try:
                await self.monitor_with_commands()
            except KeyboardInterrupt:
                self.console.print("\n[yellow]Stopping...[/yellow]")

        if self.driver:
            self.driver.quit()

        self.console.print("[green]Goodbye![/green]")


def main():
    client = WhatsAppAIControl()
    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        print("\nExiting...")


if __name__ == "__main__":
    main()