"""
MCP Client Base Class
Provides WebSocket connection and message handling for all MCP clients
"""

import asyncio
import json
import logging
from typing import Optional, Dict, Any, Callable
import websockets
from datetime import datetime
import uuid

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MCPClient:
    """Base class for all MCP clients"""

    def __init__(self,
                 client_name: str = "generic_client",
                 mcp_url: str = "ws://localhost:8002"):
        self.client_name = client_name
        self.client_id = f"{client_name}_{uuid.uuid4().hex[:8]}"
        self.mcp_url = mcp_url
        self.websocket = None
        self.running = False
        self.message_handlers = {}
        self.connection_established = False
        self.pending_requests = {}  # Store pending requests for correlation
        self.response_futures = {}  # Store futures for async responses

    async def connect(self) -> bool:
        """Establish WebSocket connection to MCP server"""
        try:
            self.websocket = await websockets.connect(self.mcp_url)
            self.running = True

            # Send initial registration
            await self.send_message({
                "type": "register",
                "client_id": self.client_id,
                "client_name": self.client_name,
                "timestamp": datetime.utcnow().isoformat()
            })

            self.connection_established = True
            logger.info(f"Connected to MCP server at {self.mcp_url}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to MCP server: {e}")
            return False

    async def disconnect(self):
        """Disconnect from MCP server"""
        self.running = False
        if self.websocket:
            await self.websocket.close()
        logger.info("Disconnected from MCP server")

    async def send_message(self, message: Dict[str, Any]) -> bool:
        """Send message to MCP server"""
        if not self.websocket:
            logger.error("Not connected to MCP server")
            return False

        try:
            # Add client info to message
            message["client_id"] = self.client_id
            message["timestamp"] = datetime.utcnow().isoformat()

            await self.websocket.send(json.dumps(message))
            return True

        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False

    async def receive_messages(self):
        """Listen for messages from MCP server with keepalive"""
        last_ping = datetime.utcnow()
        ping_interval = 30  # Send ping every 30 seconds

        while self.running:
            try:
                if not self.websocket:
                    await asyncio.sleep(1)
                    continue

                # Send periodic ping to keep connection alive
                now = datetime.utcnow()
                if (now - last_ping).total_seconds() > ping_interval:
                    await self.send_message({"type": "ping"})
                    last_ping = now

                # Use timeout to check for messages
                try:
                    message = await asyncio.wait_for(self.websocket.recv(), timeout=1.0)
                    data = json.loads(message)

                    # Handle message based on type
                    await self.handle_message(data)

                except asyncio.TimeoutError:
                    # No message received, continue loop
                    continue

            except websockets.exceptions.ConnectionClosed:
                logger.warning("Connection to MCP server closed")
                self.running = False
                break

            except Exception as e:
                logger.error(f"Error receiving message: {e}")
                await asyncio.sleep(1)

    async def handle_message(self, message: Dict[str, Any]):
        """Handle incoming message from MCP server"""
        msg_type = message.get("type", "unknown")

        # Check for registered handlers
        if msg_type in self.message_handlers:
            await self.message_handlers[msg_type](message)
        else:
            # Default handling
            if msg_type == "connection":
                logger.info(f"Connection confirmed: {message.get('status')}")
            elif msg_type == "response":
                await self.handle_response(message)
            elif msg_type == "error":
                error_msg = message.get('error', 'Unknown error')
                # Don't log as error if it's just an unknown message type warning
                if "Unknown message type" in error_msg:
                    logger.debug(f"MCP Server: {error_msg}")
                else:
                    logger.warning(f"MCP Server Error: {error_msg}")
            else:
                logger.debug(f"Unhandled message type: {msg_type}")

    async def handle_response(self, message: Dict[str, Any]):
        """Handle response message"""
        request_id = message.get('request_id')

        # Check if this is a response to a pending request
        if request_id and request_id in self.response_futures:
            future = self.response_futures[request_id]
            if not future.done():
                future.set_result(message)
            del self.response_futures[request_id]
        else:
            logger.info(f"Received response: {message.get('content', 'No content')}")

    async def send_request_and_wait(self, message: Dict[str, Any], timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        """Send a request and wait for response"""
        request_id = str(uuid.uuid4())
        message['request_id'] = request_id

        # Create a future for this request
        future = asyncio.get_event_loop().create_future()
        self.response_futures[request_id] = future

        # Send the message
        if not await self.send_message(message):
            del self.response_futures[request_id]
            return None

        try:
            # Wait for response with timeout
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
        except asyncio.TimeoutError:
            logger.warning(f"Request {request_id} timed out")
            if request_id in self.response_futures:
                del self.response_futures[request_id]
            return None

    def register_handler(self, msg_type: str, handler: Callable):
        """Register a handler for specific message type"""
        self.message_handlers[msg_type] = handler

    async def request_ai_response(self, prompt: str, context: Optional[str] = None) -> str:
        """Request AI response from MCP server"""
        request_id = uuid.uuid4().hex

        await self.send_message({
            "type": "ai_request",
            "request_id": request_id,
            "prompt": prompt,
            "context": context,
            "service": "gemini"
        })

        # Wait for response (simplified - in production use proper async waiting)
        # This is a placeholder - implement proper response correlation
        await asyncio.sleep(2)
        return "AI response will be handled asynchronously"

    async def send_whatsapp_command(self, command: Dict[str, Any]) -> bool:
        """Send WhatsApp command through MCP"""
        await self.send_message({
            "type": "whatsapp_command",
            "command": command,
            "timestamp": datetime.utcnow().isoformat()
        })
        return True

    async def get_conversation_history(self, conversation_id: Optional[str] = None) -> list:
        """Get conversation history from MCP server"""
        await self.send_message({
            "type": "get_history",
            "conversation_id": conversation_id or "current"
        })
        # Placeholder for async response
        return []

    async def run(self):
        """Main run loop for the client"""
        if await self.connect():
            # Start message receiver in background
            receive_task = asyncio.create_task(self.receive_messages())

            try:
                # Keep running until stopped
                while self.running:
                    await asyncio.sleep(1)

            except KeyboardInterrupt:
                logger.info("Shutting down MCP client...")

            finally:
                await self.disconnect()
                receive_task.cancel()

    async def run_with_callback(self, callback: Callable):
        """Run client with a callback function for custom logic"""
        if await self.connect():
            receive_task = asyncio.create_task(self.receive_messages())

            try:
                # Run callback
                await callback(self)

            finally:
                await self.disconnect()
                receive_task.cancel()


class WhatsAppMCPClient(MCPClient):
    """Specialized MCP client for WhatsApp operations"""

    def __init__(self, mcp_url: str = "ws://localhost:8002"):
        super().__init__("whatsapp_client", mcp_url)
        self.current_contact = None
        self.contact_list = []

    async def send_message_to_contact(self, contact: str, message: str) -> bool:
        """Send WhatsApp message through MCP"""
        return await self.send_whatsapp_command({
            "action": "send",
            "contact": contact,
            "message": message
        })

    async def get_messages(self, contact: str, count: int = 10) -> list:
        """Get messages for a contact through MCP"""
        await self.send_message({
            "type": "whatsapp_get_messages",
            "contact": contact,
            "count": count
        })
        return []  # Async response will be handled

    async def get_contacts(self) -> list:
        """Get WhatsApp contacts through MCP"""
        await self.send_message({
            "type": "whatsapp_get_contacts"
        })
        return []  # Async response will be handled

    async def handle_response(self, message: Dict[str, Any]):
        """Handle WhatsApp-specific responses"""
        content = message.get("content", {})

        if message.get("response_type") == "contacts":
            self.contact_list = content.get("contacts", [])
            logger.info(f"Received {len(self.contact_list)} contacts")

        elif message.get("response_type") == "messages":
            contact = content.get("contact")
            messages = content.get("messages", [])
            logger.info(f"Received {len(messages)} messages from {contact}")

        else:
            await super().handle_response(message)


class ConversationMCPClient(MCPClient):
    """MCP client for conversation management"""

    def __init__(self, mcp_url: str = "ws://localhost:8002"):
        super().__init__("conversation_client", mcp_url)
        self.conversation_id = None

    async def start_conversation(self, user_id: str) -> str:
        """Start a new conversation"""
        conv_id = uuid.uuid4().hex
        await self.send_message({
            "type": "start_conversation",
            "user_id": user_id,
            "conversation_id": conv_id
        })
        self.conversation_id = conv_id
        return conv_id

    async def send_chat_message(self, message: str) -> bool:
        """Send a chat message in current conversation"""
        if not self.conversation_id:
            logger.error("No active conversation")
            return False

        return await self.send_message({
            "type": "chat_message",
            "conversation_id": self.conversation_id,
            "message": message
        })

    async def end_conversation(self) -> bool:
        """End current conversation"""
        if self.conversation_id:
            await self.send_message({
                "type": "end_conversation",
                "conversation_id": self.conversation_id
            })
            self.conversation_id = None
            return True
        return False