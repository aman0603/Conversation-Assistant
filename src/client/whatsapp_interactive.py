import asyncio
import json
import logging
import re
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
import websockets
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.prompt import Prompt, Confirm
from rich.live import Live
from rich.layout import Layout
from rich.text import Text
import threading

from src.utils.config import settings
from src.services.database import DatabaseService
from src.services.gemini import GeminiService
from src.models.message import MessageType, MessageDirection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WhatsAppInteractiveClient:
    def __init__(self):
        self.console = Console()
        self.driver = None
        self.mcp_websocket = None
        self.db_service = DatabaseService()
        self.gemini_service = GeminiService()
        self.running = False
        self.authenticated = False
        self.auto_reply = False
        self.allowed_chats = []
        self.interactive_mode = False
        self.message_history = {}  # Store recent messages per chat
        self.command_mode = False

    def print_welcome(self):
        welcome_text = """
# WhatsApp Interactive Client with Gemini AI

## Features:
- 🤖 **AI-Powered Interactions**: Talk to Gemini to control WhatsApp
- 📨 **Smart Messaging**: AI helps compose and send messages
- 📋 **Contact Management**: List and search contacts via AI
- 📊 **Message Summarization**: Get AI summaries of conversations
- 💡 **Smart Suggestions**: AI suggests appropriate responses
- 🔄 **Auto-Reply Mode**: Optional automatic responses
- 🎯 **Command Mode**: Direct AI commands for WhatsApp control

## Commands (type during monitoring):
- `/cmd` - Enter AI command mode
- `/send <contact> <message>` - Send message
- `/list` - List all contacts
- `/summary <contact>` - Summarize recent conversation
- `/suggest <contact>` - Get message suggestions
- `/auto` - Toggle auto-reply
- `/help` - Show commands
- `/quit` - Exit application
        """
        self.console.print(Panel(Markdown(welcome_text), title="WhatsApp + Gemini Interactive", border_style="green"))

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
            # Check if already logged in
            try:
                side_panel = self.driver.find_element(By.CSS_SELECTOR, "div[id='side']")
                if side_panel:
                    self.console.print("[green]Already logged in to WhatsApp Web![/green]")
                    self.authenticated = True
                    return True
            except:
                pass

            # Wait for QR code
            qr_element = WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "canvas[aria-label*='Scan'], div[data-ref]"))
            )

            self.console.print("\n[yellow]QR Code detected! Scan with WhatsApp mobile app[/yellow]")

            # Wait for successful login
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
        """Get list of WhatsApp chats"""
        chats = []
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='listitem']"))
            )

            chat_elements = self.driver.find_elements(By.CSS_SELECTOR, "div[role='listitem']")

            for chat in chat_elements[:20]:  # Get more chats
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

    def get_chat_messages(self, chat_name: str, count: int = 20) -> List[str]:
        """Get recent messages from a specific chat"""
        messages = []
        try:
            # Find and click the chat
            chats = self.get_chats()
            chat_found = False

            for chat in chats:
                if chat["name"].lower() == chat_name.lower():
                    chat["element"].click()
                    chat_found = True
                    break

            if not chat_found:
                return messages

            # Wait for messages to load
            import time
            time.sleep(2)

            # Get messages
            msg_selectors = [
                "div[class*='message-in'] span[class*='selectable-text']",
                "div[class*='message-out'] span[class*='selectable-text']",
                "span[class*='selectable-text']"
            ]

            for selector in msg_selectors:
                try:
                    msg_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for elem in msg_elements[-count:]:
                        if elem.text:
                            messages.append(elem.text)
                except:
                    continue

        except Exception as e:
            logger.error(f"Error getting messages: {e}")

        return messages

    def send_message(self, chat_name: str, message: str) -> bool:
        """Send a message to a WhatsApp chat"""
        try:
            # Find and click the chat
            chat_found = False
            chats = self.get_chats()

            for chat in chats:
                if chat["name"].lower() == chat_name.lower():
                    chat["element"].click()
                    chat_found = True
                    break

            if not chat_found:
                # Try searching for the contact
                search_box = self.driver.find_element(By.CSS_SELECTOR, "div[contenteditable='true'][data-tab='3']")
                search_box.click()
                search_box.clear()
                search_box.send_keys(chat_name)

                import time
                time.sleep(2)

                # Click first search result
                results = self.driver.find_elements(By.CSS_SELECTOR, "div[role='listitem']")
                if results:
                    results[0].click()
                    time.sleep(1)
                else:
                    logger.error(f"Contact '{chat_name}' not found")
                    return False

            # Wait for chat to load
            import time
            time.sleep(1)

            # Find message input
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

            # Type and send message
            input_box.click()
            input_box.clear()
            input_box.send_keys(message)
            input_box.send_keys(Keys.ENTER)

            logger.info(f"Message sent to {chat_name}")
            return True

        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False

    async def process_ai_command(self, command: str) -> str:
        """Process natural language command with Gemini AI"""
        try:
            # Parse the command intent
            system_prompt = """You are a WhatsApp assistant. Analyze the user's command and respond with a JSON action.

Available actions:
1. {"action": "send", "contact": "name", "message": "text"} - Send a message
2. {"action": "list"} - List all contacts
3. {"action": "summary", "contact": "name", "count": 20} - Summarize recent messages
4. {"action": "suggest", "contact": "name", "context": "optional context"} - Suggest a message
5. {"action": "read", "contact": "name", "count": 10} - Read recent messages
6. {"action": "search", "query": "search term"} - Search for a contact
7. {"action": "help"} - Show help
8. {"action": "error", "message": "explanation"} - When command is unclear

Parse the user's natural language and return ONLY the JSON action, no other text."""

            # Get AI to parse the command
            ai_response = await self.gemini_service.generate_response(
                prompt=command,
                system_prompt=system_prompt
            )

            # Try to extract JSON from response
            import json
            json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
            if json_match:
                action_data = json.loads(json_match.group())
                return await self.execute_ai_action(action_data)
            else:
                return "I couldn't understand that command. Try: 'Send a message to John saying hello' or 'List my contacts'"

        except Exception as e:
            logger.error(f"Error processing AI command: {e}")
            return f"Error processing command: {str(e)}"

    async def execute_ai_action(self, action_data: Dict[str, Any]) -> str:
        """Execute the parsed AI action"""
        action = action_data.get("action", "")

        if action == "send":
            contact = action_data.get("contact", "")
            message = action_data.get("message", "")

            if not contact or not message:
                return "Please specify both contact name and message."

            if self.send_message(contact, message):
                return f"✅ Message sent to {contact}: '{message}'"
            else:
                return f"❌ Failed to send message to {contact}"

        elif action == "list":
            chats = self.get_chats()
            if not chats:
                return "No chats found."

            result = "📋 **Your WhatsApp Contacts:**\n"
            for i, chat in enumerate(chats, 1):
                last_msg = chat.get('last_message', '')[:30] + "..." if chat.get('last_message') else "No messages"
                result += f"{i}. **{chat['name']}** - {last_msg}\n"

            return result

        elif action == "summary":
            contact = action_data.get("contact", "")
            count = action_data.get("count", 20)

            if not contact:
                return "Please specify a contact name for summary."

            messages = self.get_chat_messages(contact, count)
            if not messages:
                return f"No messages found with {contact}"

            # Use AI to summarize
            summary_prompt = f"Summarize these WhatsApp messages in 3-4 bullet points:\n\n" + "\n".join(messages)
            summary = await self.gemini_service.generate_response(
                prompt=summary_prompt,
                system_prompt="Create a concise summary of the conversation. Focus on key topics and important information."
            )

            return f"📊 **Summary of conversation with {contact}:**\n{summary}"

        elif action == "suggest":
            contact = action_data.get("contact", "")
            context = action_data.get("context", "")

            if not contact:
                return "Please specify a contact name for suggestions."

            # Get recent messages for context
            messages = self.get_chat_messages(contact, 10)
            conversation_context = "\n".join(messages[-5:]) if messages else "No previous messages"

            # Generate suggestions
            suggest_prompt = f"""Based on this conversation with {contact}:
{conversation_context}

Additional context: {context if context else 'None'}

Suggest 3 appropriate message responses."""

            suggestions = await self.gemini_service.generate_response(
                prompt=suggest_prompt,
                system_prompt="Generate 3 brief, contextually appropriate WhatsApp message suggestions. Keep them natural and conversational."
            )

            return f"💡 **Message suggestions for {contact}:**\n{suggestions}"

        elif action == "read":
            contact = action_data.get("contact", "")
            count = action_data.get("count", 10)

            if not contact:
                return "Please specify a contact name."

            messages = self.get_chat_messages(contact, count)
            if not messages:
                return f"No messages found with {contact}"

            result = f"📖 **Recent messages with {contact}:**\n"
            for i, msg in enumerate(messages, 1):
                result += f"{i}. {msg}\n"

            return result

        elif action == "search":
            query = action_data.get("query", "")
            if not query:
                return "Please specify a search term."

            chats = self.get_chats()
            matches = [c for c in chats if query.lower() in c["name"].lower()]

            if not matches:
                return f"No contacts found matching '{query}'"

            result = f"🔍 **Search results for '{query}':**\n"
            for chat in matches:
                result += f"- {chat['name']}\n"

            return result

        elif action == "help":
            return """🤖 **AI Command Examples:**
• "Send a message to John saying I'll be there in 10 minutes"
• "List all my contacts"
• "Summarize my conversation with Sarah"
• "Suggest a reply to Mike"
• "Read the last 5 messages from David"
• "Search for contacts with 'work' in the name"
• "What should I say to apologize to Emma?"
"""

        elif action == "error":
            return action_data.get("message", "Command not understood")

        else:
            return "Unknown action. Try asking me to send a message, list contacts, or summarize a conversation."

    async def interactive_command_mode(self):
        """Enter interactive AI command mode"""
        self.console.print("\n[cyan]━━━ AI Command Mode ━━━[/cyan]")
        self.console.print("[dim]Type your commands in natural language. Type 'exit' to return to monitoring.[/dim]\n")

        while self.command_mode:
            try:
                # Get command from user
                command = Prompt.ask("[bold cyan]AI Command[/bold cyan]")

                if command.lower() in ['exit', 'quit', 'back']:
                    self.command_mode = False
                    self.console.print("[yellow]Returning to message monitoring...[/yellow]")
                    break

                # Process with AI
                self.console.print("[dim]Processing...[/dim]")
                response = await self.process_ai_command(command)

                # Display response
                self.console.print(Panel(Markdown(response), border_style="green"))

            except Exception as e:
                self.console.print(f"[red]Error: {e}[/red]")

    async def handle_command(self, cmd: str) -> bool:
        """Handle slash commands during monitoring"""
        parts = cmd.split(maxsplit=2)
        command = parts[0].lower()

        if command == "/cmd":
            self.command_mode = True
            await self.interactive_command_mode()
            return True

        elif command == "/send" and len(parts) >= 3:
            contact = parts[1]
            message = parts[2]
            if self.send_message(contact, message):
                self.console.print(f"[green]✓ Message sent to {contact}[/green]")
            else:
                self.console.print(f"[red]✗ Failed to send to {contact}[/red]")
            return True

        elif command == "/list":
            chats = self.get_chats()
            table = Table(show_header=True, header_style="bold cyan")
            table.add_column("#", style="dim", width=3)
            table.add_column("Contact", style="green")
            table.add_column("Last Message", style="white")

            for i, chat in enumerate(chats, 1):
                msg = chat.get('last_message', '')[:40] + "..." if chat.get('last_message') else ""
                table.add_row(str(i), chat['name'], msg)

            self.console.print(table)
            return True

        elif command == "/summary" and len(parts) >= 2:
            contact = parts[1]
            messages = self.get_chat_messages(contact, 20)
            if messages:
                summary_prompt = "Summarize these messages:\n" + "\n".join(messages)
                summary = await self.gemini_service.generate_response(
                    prompt=summary_prompt,
                    system_prompt="Create a brief summary in 3-4 bullet points."
                )
                self.console.print(Panel(Markdown(f"**Summary of {contact}:**\n{summary}"), border_style="cyan"))
            else:
                self.console.print(f"[red]No messages found with {contact}[/red]")
            return True

        elif command == "/suggest" and len(parts) >= 2:
            contact = parts[1]
            messages = self.get_chat_messages(contact, 10)
            context = "\n".join(messages[-5:]) if messages else "No previous messages"

            suggestions = await self.gemini_service.generate_response(
                prompt=f"Suggest 3 replies for this conversation:\n{context}",
                system_prompt="Generate 3 brief, appropriate message suggestions."
            )

            self.console.print(Panel(Markdown(f"**Suggestions for {contact}:**\n{suggestions}"), border_style="green"))
            return True

        elif command == "/auto":
            self.auto_reply = not self.auto_reply
            status = "enabled" if self.auto_reply else "disabled"
            self.console.print(f"[yellow]Auto-reply {status}[/yellow]")
            return True

        elif command == "/help":
            help_text = """
**Available Commands:**
• `/cmd` - Enter AI command mode
• `/send <contact> <message>` - Send a message
• `/list` - List all contacts
• `/summary <contact>` - Summarize conversation
• `/suggest <contact>` - Get message suggestions
• `/auto` - Toggle auto-reply
• `/help` - Show this help
• `/quit` - Exit application
"""
            self.console.print(Panel(Markdown(help_text), title="Commands", border_style="cyan"))
            return True

        elif command == "/quit":
            self.running = False
            return True

        return False

    async def monitor_with_interaction(self):
        """Monitor messages with interactive command support"""
        last_messages = {}

        self.console.print("\n[cyan]Interactive Monitoring Active[/cyan]")
        self.console.print("[yellow]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/yellow]")
        self.console.print("[green]Commands available during monitoring:[/green]")
        self.console.print("  • [cyan]/cmd[/cyan] - Enter AI command mode")
        self.console.print("  • [cyan]/send <contact> <message>[/cyan] - Quick send")
        self.console.print("  • [cyan]/list[/cyan] - List contacts")
        self.console.print("  • [cyan]/help[/cyan] - Show all commands")
        self.console.print("[yellow]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/yellow]")
        self.console.print("[dim]Type a command below (starting with /) while monitoring continues...[/dim]\n")

        # Start a thread for user input
        command_queue = asyncio.Queue()

        def input_thread():
            while self.running:
                try:
                    # Show prompt for better UX
                    user_input = input("Command> ")
                    if user_input:
                        asyncio.run_coroutine_threadsafe(
                            command_queue.put(user_input),
                            asyncio.get_event_loop()
                        )
                except EOFError:
                    break
                except KeyboardInterrupt:
                    self.running = False
                    break
                except Exception as e:
                    print(f"Input error: {e}")
                    break

        input_thread = threading.Thread(target=input_thread, daemon=True)
        input_thread.start()

        while self.running and self.authenticated:
            try:
                # Check for commands
                try:
                    command = await asyncio.wait_for(command_queue.get(), timeout=0.1)
                    if command.startswith("/"):
                        await self.handle_command(command)
                    else:
                        # Treat as AI command
                        self.console.print("[dim]Processing AI command...[/dim]")
                        response = await self.process_ai_command(command)
                        self.console.print(Panel(Markdown(response), border_style="green"))
                        self.console.print("")  # Add blank line for readability
                except asyncio.TimeoutError:
                    pass

                # Monitor messages
                chats = self.get_chats()

                for chat in chats:
                    chat_name = chat["name"]
                    last_msg = chat.get("last_message", "")

                    # Store messages for history
                    if chat_name not in self.message_history:
                        self.message_history[chat_name] = []

                    # Check for new message
                    if last_msg and chat_name not in last_messages:
                        last_messages[chat_name] = last_msg
                    elif last_msg and last_messages.get(chat_name) != last_msg:
                        # New message detected
                        self.message_history[chat_name].append({
                            "time": datetime.now(),
                            "message": last_msg,
                            "direction": "incoming"
                        })

                        # Keep only last 50 messages per chat
                        if len(self.message_history[chat_name]) > 50:
                            self.message_history[chat_name] = self.message_history[chat_name][-50:]

                        self.console.print(f"\n[yellow]━━━ New Message ━━━[/yellow]")
                        self.console.print(f"[cyan]From:[/cyan] {chat_name}")
                        self.console.print(f"[cyan]Message:[/cyan] {last_msg}")

                        # Process with Gemini
                        ai_response = await self.gemini_service.generate_response(
                            prompt=last_msg,
                            system_prompt=f"You are responding to a WhatsApp message from {chat_name}. Be concise and friendly."
                        )
                        self.console.print(f"[green]AI Suggestion:[/green] {ai_response}")

                        # Auto-reply if enabled
                        if self.auto_reply:
                            if not self.allowed_chats or chat_name in self.allowed_chats:
                                if self.send_message(chat_name, ai_response):
                                    self.console.print(f"[green]✓ Auto-reply sent[/green]")
                                    self.message_history[chat_name].append({
                                        "time": datetime.now(),
                                        "message": ai_response,
                                        "direction": "outgoing"
                                    })

                        last_messages[chat_name] = last_msg
                        self.console.print("[dim]━━━━━━━━━━━━━━━━━━━━[/dim]")

                        # Show command hint periodically
                        if len(last_messages) % 5 == 0:
                            self.console.print("[dim]Tip: Type /cmd to enter AI command mode[/dim]\n")

                await asyncio.sleep(3)

            except Exception as e:
                logger.error(f"Error in monitoring: {e}")
                await asyncio.sleep(5)

    async def run(self):
        """Main run loop"""
        self.print_welcome()

        # Initialize database
        await self.db_service.initialize()

        # Setup Chrome
        self.console.print("[cyan]Opening WhatsApp Web...[/cyan]")
        self.setup_driver()

        # Login
        if self.wait_for_login():
            self.running = True

            # Show initial chats
            self.console.print("\n[cyan]Available Chats:[/cyan]")
            chats = self.get_chats()

            table = Table(show_header=True, header_style="bold cyan")
            table.add_column("#", style="dim", width=3)
            table.add_column("Contact", style="green")
            table.add_column("Last Message", style="white")

            for i, chat in enumerate(chats[:10], 1):
                msg = chat.get('last_message', '')[:40] + "..." if chat.get('last_message') else ""
                table.add_row(str(i), chat['name'], msg)

            self.console.print(table)

            # Ask about auto-reply
            self.console.print("\n[cyan]Auto-Reply Configuration[/cyan]")
            self.auto_reply = Confirm.ask("Enable auto-reply for messages?", default=False)

            if self.auto_reply:
                self.console.print("[yellow]Auto-reply enabled. AI will respond to all messages.[/yellow]")

            # Start interactive monitoring
            self.console.print("\n[green]System Ready![/green]")
            self.console.print("[yellow]Press Ctrl+C to stop[/yellow]")

            try:
                await self.monitor_with_interaction()
            except KeyboardInterrupt:
                self.console.print("\n[yellow]Stopping...[/yellow]")

        # Cleanup
        self.running = False
        if self.driver:
            self.driver.quit()

        self.console.print("[green]Client stopped[/green]")


def main():
    client = WhatsAppInteractiveClient()
    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        print("\nExiting...")


if __name__ == "__main__":
    main()