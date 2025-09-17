import asyncio
import websockets
import json
import uuid
from datetime import datetime

class WhatsAppClient:
    def __init__(self, uri: str):
        self.uri = uri
        self.client_id = f"whatsapp_client_{uuid.uuid4().hex}"
        self.websocket = None
        self.user_id = None
        self.conversation_id = None

    async def connect(self):
        print(f"Connecting to MCP server at {self.uri}...")
        self.websocket = await websockets.connect(self.uri)
        print("Connected to MCP server.")
        await self.initialize_client()

    async def disconnect(self):
        if self.websocket:
            await self.websocket.close()
            print("Disconnected from MCP server.")

    async def send_message(self, message: dict):
        if self.websocket:
            await self.websocket.send(json.dumps(message))

    async def receive_message(self):
        if self.websocket:
            try:
                message = await self.websocket.recv()
                return json.loads(message)
            except websockets.exceptions.ConnectionClosedOK:
                print("Server closed the connection.")
                return None
            except Exception as e:
                print(f"Error receiving message: {e}")
                return None
        return None

    async def initialize_client(self):
        init_message = {
            "type": "initialize",
            "client_id": self.client_id,
            "user_id": "whatsapp_user_123", # Example user ID
            "name": "WhatsApp User"
        }
        await self.send_message(init_message)
        response = await self.receive_message()
        if response and response.get("type") == "initialized":
            self.user_id = response.get("user_id")
            print(f"Client initialized with user ID: {self.user_id}")
        else:
            print(f"Initialization failed: {response}")

    async def send_whatsapp_message(self, content: str):
        if not self.user_id:
            print("Client not initialized. Cannot send message.")
            return

        message_payload = {
            "type": "send_message",
            "client_id": self.client_id,
            "user_id": self.user_id,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        }
        await self.send_message(message_payload)
        print(f"Sent message: {content}")
        response = await self.receive_message()
        if response and response.get("type") == "message_sent":
            self.conversation_id = response.get("conversation_id")
            print(f"Message sent. Conversation ID: {self.conversation_id}")
        else:
            print(f"Failed to send message: {response}")

    async def listen_for_responses(self):
        while True:
            response = await self.receive_message()
            if response is None:
                break
            print(f"Received: {json.dumps(response, indent=2)}")
            if response.get("type") == "message_received":
                print(f"AI Assistant: {response.get('content')}")

async def main():
    # Assuming the MCP server is running on localhost:8000
    # You might need to adjust the URI based on your MCP server configuration
    uri = "ws://localhost:8001" 
    client = WhatsAppClient(uri)
    
    await client.connect()

    # Start listening for responses in a separate task
    asyncio.create_task(client.listen_for_responses())

    # Example: Send a message to the MCP server
    await client.send_whatsapp_message("Hello, how are you?")
    await asyncio.sleep(2) # Give some time for response
    await client.send_whatsapp_message("What is the weather like today?")
    await asyncio.sleep(2) # Give some time for response

    # Keep the client running to listen for messages
    await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Client stopped by user.")