import asyncio
import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
import websockets
from websockets.server import WebSocketServerProtocol

from src.utils.config import settings
from src.services.database import DatabaseService
from src.services.gemini import GeminiService
from src.models.conversation import Conversation
from src.models.message import Message, MessageType, MessageDirection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MCPServer:
    def __init__(self):
        self.db_service = DatabaseService()
        self.gemini_service = GeminiService()
        self.clients: Dict[str, WebSocketServerProtocol] = {}
        self.user_sessions: Dict[str, Dict[str, Any]] = {}
        
    async def register_client(self, websocket: WebSocketServerProtocol, client_id: str):
        self.clients[client_id] = websocket
        self.user_sessions[client_id] = {
            "user_id": None,
            "conversation_id": None,
            "context": []
        }
        logger.info(f"Client {client_id} connected")
        
        await self.send_message(websocket, {
            "type": "connection",
            "status": "connected",
            "client_id": client_id,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    async def unregister_client(self, client_id: str):
        if client_id in self.clients:
            del self.clients[client_id]
            del self.user_sessions[client_id]
            logger.info(f"Client {client_id} disconnected")
    
    async def send_message(self, websocket: WebSocketServerProtocol, message: Dict[str, Any]):
        await websocket.send(json.dumps(message))
    
    async def handle_message(self, websocket: WebSocketServerProtocol, client_id: str, data: Dict[str, Any]):
        message_type = data.get("type")
        logger.info(f"Received message type: {message_type} from {client_id}")

        handlers = {
            "initialize": self.handle_initialize,
            "send_message": self.handle_send_message,
            "load_conversation": self.handle_load_conversation,
            "list_conversations": self.handle_list_conversations,
            "create_conversation": self.handle_create_conversation,
            "get_summary": self.handle_get_summary,
            "search": self.handle_search,
            # New MCP handlers
            "register": self.handle_register,
            "whatsapp_command": self.handle_whatsapp_command,
            "whatsapp_ai_command": self.handle_whatsapp_ai_command,
            "ai_request": self.handle_ai_request,
            "contact_list_update": self.handle_contact_list_update,
            "ping": self.handle_ping,
        }

        handler = handlers.get(message_type)
        if handler:
            try:
                await handler(websocket, client_id, data)
            except Exception as e:
                logger.error(f"Error handling {message_type}: {e}")
                await self.send_message(websocket, {
                    "type": "error",
                    "error": str(e),
                    "request_type": message_type
                })
        else:
            await self.send_message(websocket, {
                "type": "error",
                "error": f"Unknown message type: {message_type}"
            })
    
    async def handle_initialize(self, websocket: WebSocketServerProtocol, client_id: str, data: Dict[str, Any]):
        user_id = data.get("user_id")
        if not user_id:
            user_id = f"user_{client_id}"
        
        self.user_sessions[client_id]["user_id"] = user_id
        
        user = await self.db_service.get_or_create_user(user_id, data.get("name"))
        
        await self.send_message(websocket, {
            "type": "initialized",
            "user_id": user_id,
            "user_name": user.get("name"),
            "timestamp": datetime.utcnow().isoformat()
        })
    
    async def handle_send_message(self, websocket: WebSocketServerProtocol, client_id: str, data: Dict[str, Any]):
        session = self.user_sessions[client_id]
        user_id = session.get("user_id")
        conversation_id = session.get("conversation_id")
        
        if not user_id:
            await self.send_message(websocket, {
                "type": "error",
                "error": "User not initialized. Please initialize first."
            })
            return
        
        content = data.get("content")
        if not content:
            await self.send_message(websocket, {
                "type": "error",
                "error": "Message content is required"
            })
            return
        
        if not conversation_id:
            conversation = await self.db_service.create_conversation(
                participants=[user_id],
                metadata={"source": "terminal"}
            )
            conversation_id = str(conversation["_id"])
            session["conversation_id"] = conversation_id
        
        user_message = await self.db_service.add_message(
            conversation_id=conversation_id,
            sender_id=user_id,
            content=content,
            message_type=MessageType.TEXT,
            direction=MessageDirection.INCOMING
        )
        
        await self.send_message(websocket, {
            "type": "message_sent",
            "message_id": str(user_message["_id"]),
            "conversation_id": conversation_id,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        session["context"].append({
            "role": "user",
            "content": content
        })
        
        recent_messages = await self.db_service.get_recent_messages(
            conversation_id, 
            limit=10
        )
        
        context = self._build_context(recent_messages)
        
        try:
            ai_response = await self.gemini_service.generate_response(
                prompt=content,
                context=context,
                system_prompt="You are a helpful conversation assistant. Provide clear, concise, and helpful responses."
            )
            
            ai_message = await self.db_service.add_message(
                conversation_id=conversation_id,
                sender_id="assistant",
                content=ai_response,
                message_type=MessageType.TEXT,
                direction=MessageDirection.OUTGOING
            )
            
            session["context"].append({
                "role": "assistant",
                "content": ai_response
            })
            
            await self.send_message(websocket, {
                "type": "message_received",
                "message_id": str(ai_message["_id"]),
                "conversation_id": conversation_id,
                "content": ai_response,
                "sender": "assistant",
                "timestamp": datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Error generating AI response: {e}")
            await self.send_message(websocket, {
                "type": "error",
                "error": f"Failed to generate response: {str(e)}"
            })
    
    async def handle_load_conversation(self, websocket: WebSocketServerProtocol, client_id: str, data: Dict[str, Any]):
        conversation_id = data.get("conversation_id")
        if not conversation_id:
            await self.send_message(websocket, {
                "type": "error",
                "error": "conversation_id is required"
            })
            return
        
        conversation = await self.db_service.get_conversation(conversation_id)
        if not conversation:
            await self.send_message(websocket, {
                "type": "error",
                "error": "Conversation not found"
            })
            return
        
        messages = await self.db_service.get_messages(conversation_id, limit=50)
        
        self.user_sessions[client_id]["conversation_id"] = conversation_id
        self.user_sessions[client_id]["context"] = self._build_context(messages)
        
        await self.send_message(websocket, {
            "type": "conversation_loaded",
            "conversation_id": conversation_id,
            "messages": [self._format_message(msg) for msg in messages],
            "participants": conversation.get("participants", []),
            "timestamp": datetime.utcnow().isoformat()
        })
    
    async def handle_list_conversations(self, websocket: WebSocketServerProtocol, client_id: str, data: Dict[str, Any]):
        session = self.user_sessions[client_id]
        user_id = session.get("user_id")
        
        if not user_id:
            await self.send_message(websocket, {
                "type": "error",
                "error": "User not initialized"
            })
            return
        
        conversations = await self.db_service.get_user_conversations(user_id)
        
        formatted_conversations = []
        for conv in conversations:
            last_message = await self.db_service.get_last_message(str(conv["_id"]))
            formatted_conversations.append({
                "id": str(conv["_id"]),
                "created_at": conv["created_at"].isoformat(),
                "updated_at": conv["updated_at"].isoformat(),
                "message_count": conv.get("message_count", 0),
                "last_message": self._format_message(last_message) if last_message else None
            })
        
        await self.send_message(websocket, {
            "type": "conversations_list",
            "conversations": formatted_conversations,
            "total": len(formatted_conversations),
            "timestamp": datetime.utcnow().isoformat()
        })
    
    async def handle_create_conversation(self, websocket: WebSocketServerProtocol, client_id: str, data: Dict[str, Any]):
        session = self.user_sessions[client_id]
        user_id = session.get("user_id")
        
        if not user_id:
            await self.send_message(websocket, {
                "type": "error",
                "error": "User not initialized"
            })
            return
        
        participants = data.get("participants", [user_id])
        if user_id not in participants:
            participants.append(user_id)
        
        conversation = await self.db_service.create_conversation(
            participants=participants,
            metadata=data.get("metadata", {})
        )
        
        conversation_id = str(conversation["_id"])
        session["conversation_id"] = conversation_id
        
        await self.send_message(websocket, {
            "type": "conversation_created",
            "conversation_id": conversation_id,
            "participants": participants,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    async def handle_get_summary(self, websocket: WebSocketServerProtocol, client_id: str, data: Dict[str, Any]):
        conversation_id = data.get("conversation_id") or self.user_sessions[client_id].get("conversation_id")
        
        if not conversation_id:
            await self.send_message(websocket, {
                "type": "error",
                "error": "conversation_id is required"
            })
            return
        
        messages = await self.db_service.get_messages(conversation_id, limit=100)
        
        if not messages:
            await self.send_message(websocket, {
                "type": "summary",
                "conversation_id": conversation_id,
                "summary": "No messages to summarize",
                "key_points": []
            })
            return
        
        conversation_text = "\n".join([
            f"{msg.get('sender_id', 'Unknown')}: {msg.get('content', '')}"
            for msg in messages if msg.get('content')
        ])
        
        try:
            summary = await self.gemini_service.generate_summary(conversation_text)
            
            await self.send_message(websocket, {
                "type": "summary",
                "conversation_id": conversation_id,
                "summary": summary,
                "message_count": len(messages),
                "timestamp": datetime.utcnow().isoformat()
            })
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            await self.send_message(websocket, {
                "type": "error",
                "error": f"Failed to generate summary: {str(e)}"
            })
    
    async def handle_search(self, websocket: WebSocketServerProtocol, client_id: str, data: Dict[str, Any]):
        query = data.get("query")
        if not query:
            await self.send_message(websocket, {
                "type": "error",
                "error": "Search query is required"
            })
            return
        
        user_id = self.user_sessions[client_id].get("user_id")
        results = await self.db_service.search_messages(query, user_id)
        
        formatted_results = []
        for result in results:
            formatted_results.append({
                "message_id": str(result["_id"]),
                "conversation_id": result["conversation_id"],
                "content": result["content"],
                "sender_id": result["sender_id"],
                "timestamp": result["timestamp"].isoformat()
            })
        
        await self.send_message(websocket, {
            "type": "search_results",
            "query": query,
            "results": formatted_results,
            "count": len(formatted_results),
            "timestamp": datetime.utcnow().isoformat()
        })
    
    def _build_context(self, messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        context = []
        for msg in messages:
            if msg.get("content"):
                role = "assistant" if msg.get("sender_id") == "assistant" else "user"
                context.append({
                    "role": role,
                    "content": msg["content"]
                })
        return context
    
    def _format_message(self, message: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not message:
            return None
        
        return {
            "id": str(message["_id"]),
            "sender_id": message.get("sender_id"),
            "content": message.get("content"),
            "type": message.get("type"),
            "timestamp": message.get("timestamp").isoformat() if message.get("timestamp") else None
        }
    
    async def handle_client(self, websocket: WebSocketServerProtocol):
        client_id = f"client_{datetime.utcnow().timestamp()}"
        await self.register_client(websocket, client_id)
        
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self.handle_message(websocket, client_id, data)
                except json.JSONDecodeError:
                    await self.send_message(websocket, {
                        "type": "error",
                        "error": "Invalid JSON format"
                    })
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            await self.unregister_client(client_id)
    
    # New MCP handler methods for WhatsApp integration

    async def handle_register(self, websocket: WebSocketServerProtocol, client_id: str, data: Dict[str, Any]):
        """Handle client registration"""
        client_name = data.get("client_name", "unknown")
        logger.info(f"Client {client_name} registered as {client_id}")

        await self.send_message(websocket, {
            "type": "registration_confirmed",
            "client_id": client_id,
            "timestamp": datetime.utcnow().isoformat()
        })

    async def handle_whatsapp_command(self, websocket: WebSocketServerProtocol, client_id: str, data: Dict[str, Any]):
        """Handle WhatsApp command execution"""
        command = data.get("command", {})
        action = command.get("action")

        logger.info(f"Processing WhatsApp command: {action}")

        # Simulate command execution (in production, integrate with actual WhatsApp automation)
        response_data = {
            "type": "response",
            "response_type": "whatsapp_command_result",
            "action": action,
            "success": True
        }

        if action == "send":
            response_data["content"] = {
                "contact": command.get("contact"),
                "message": command.get("message"),
                "sent": True
            }
        elif action == "list":
            response_data["content"] = {
                "contacts": ["John", "Sarah", "Mike", "Emma", "David"]
            }
        elif action == "read":
            response_data["content"] = {
                "contact": command.get("contact"),
                "messages": ["Hello", "How are you?", "Thanks!"]
            }

        await self.send_message(websocket, response_data)

    async def handle_whatsapp_ai_command(self, websocket: WebSocketServerProtocol, client_id: str, data: Dict[str, Any]):
        """Handle AI-processed WhatsApp command"""
        command = data.get("command")
        context = data.get("context", {})
        request_id = data.get("request_id")

        # Process with Gemini AI
        system_prompt = f"""Parse WhatsApp command to JSON action.
Context: {context}
Actions: send, list, read, summary, suggest, auto_on, auto_off
Return only JSON."""

        try:
            ai_response = await self.gemini_service.generate_response(
                prompt=command,
                system_prompt=system_prompt
            )

            # Parse and execute the AI response
            import re
            json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
            if json_match:
                action_data = json.loads(json_match.group())

                # Process the action and get result
                result = await self.process_whatsapp_action(action_data, context)

                # Send response with request_id
                await self.send_message(websocket, {
                    "type": "response",
                    "request_id": request_id,
                    "response_type": "whatsapp_command_result",
                    "content": result
                })
            else:
                await self.send_message(websocket, {
                    "type": "response",
                    "request_id": request_id,
                    "response_type": "ai_parse_error",
                    "content": "Could not parse command"
                })

        except Exception as e:
            logger.error(f"AI command processing error: {e}")
            await self.send_message(websocket, {
                "type": "error",
                "request_id": request_id,
                "error": str(e)
            })

    async def process_whatsapp_action(self, action_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Process WhatsApp action and return result"""
        action = action_data.get("action")

        # Get contact list from context for matching
        contact_list = context.get("contact_list", [])

        if action == "list":
            return {
                "action": "list",
                "contacts": contact_list
            }

        elif action in ["send", "read", "summary", "suggest"]:
            # Get the contact name and try to match it
            contact = action_data.get("contact", "")

            # Try to find best match from contact list
            if contact and contact_list:
                # Exact match first (case insensitive)
                for c in contact_list:
                    if c.lower() == contact.lower():
                        contact = c
                        break
                else:
                    # Fuzzy match
                    from difflib import get_close_matches
                    matches = get_close_matches(contact, contact_list, n=1, cutoff=0.6)
                    if matches:
                        contact = matches[0]

            result = {
                "action": action,
                "contact": contact
            }

            if action == "send":
                result["message"] = action_data.get("message")
                result["sent"] = True

            return result

        elif action in ["auto_on", "auto_off", "status"]:
            return {"action": action}

        else:
            return {"action": action, "result": "Processed"}

    async def handle_ai_request(self, websocket: WebSocketServerProtocol, client_id: str, data: Dict[str, Any]):
        """Handle direct AI request"""
        prompt = data.get("prompt")
        context = data.get("context")
        request_id = data.get("request_id")

        try:
            response = await self.gemini_service.generate_response(
                prompt=prompt,
                system_prompt=context
            )

            await self.send_message(websocket, {
                "type": "ai_response",
                "request_id": request_id,
                "content": response,
                "timestamp": datetime.utcnow().isoformat()
            })

        except Exception as e:
            logger.error(f"AI request error: {e}")
            await self.send_message(websocket, {
                "type": "error",
                "request_id": request_id,
                "error": str(e)
            })

    async def handle_contact_list_update(self, websocket: WebSocketServerProtocol, client_id: str, data: Dict[str, Any]):
        """Handle contact list update from client"""
        contacts = data.get("contacts", [])

        # Store in session
        self.user_sessions[client_id]["contacts"] = contacts

        logger.info(f"Updated contact list for {client_id}: {len(contacts)} contacts")

        # Broadcast to other clients if needed
        for other_client_id, other_websocket in self.clients.items():
            if other_client_id != client_id:
                await self.send_message(other_websocket, {
                    "type": "contact_list_broadcast",
                    "contacts": contacts[:20],  # Send first 20 for efficiency
                    "total_count": len(contacts)
                })

    async def handle_ping(self, websocket: WebSocketServerProtocol, client_id: str, data: Dict[str, Any]):
        """Handle ping message for keepalive"""
        await self.send_message(websocket, {
            "type": "pong",
            "timestamp": datetime.utcnow().isoformat()
        })

    async def start(self):
        await self.db_service.initialize()
        
        host = settings.MCP_SERVER_HOST
        port = settings.MCP_SERVER_PORT
        
        logger.info(f"Starting MCP server on {host}:{port}")
        
        async with websockets.serve(self.handle_client, host, port):
            logger.info(f"MCP server running on ws://{host}:{port}")
            await asyncio.Future()


def main():
    server = MCPServer()
    asyncio.run(server.start())


if __name__ == "__main__":
    main()