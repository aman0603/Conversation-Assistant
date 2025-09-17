# MCP Architecture Implementation Guide

## Overview

MCP (Model Context Protocol) is now fully integrated into your WhatsApp AI system, providing a centralized, scalable architecture for all components.

## Architecture Components

```
┌─────────────────────────────────────────────────────┐
│                  MCP Server (ws:8002)                │
│  • WebSocket Hub                                     │
│  • Message Router                                    │
│  • Session Manager                                   │
│  • AI Coordinator                                    │
└──────────────────┬──────────────────────────────────┘
                   │
    ┌──────────────┼──────────────┬─────────────────┐
    ↓              ↓              ↓                 ↓
WhatsApp AI    Terminal      Web Client      API Gateway
Control MCP     Client       (Future)         (REST)
    │              │              │                 │
    └──────────────┴──────────────┴─────────────────┘
                   Shared Session State
```

## How to Use MCP Architecture

### 1. Start MCP Server (Always First)

```bash
# Terminal 1: Start the MCP server
python -m src.mcp.server

# Output:
# INFO: Starting MCP server on localhost:8002
# INFO: MCP server running on ws://localhost:8002
```

### 2. Run WhatsApp AI Control with MCP

```bash
# Terminal 2: Run with MCP flag
python run_ai_control_mcp.py --mcp

# Or specify custom MCP server
python run_ai_control_mcp.py --mcp --mcp-url ws://192.168.1.100:8002
```

### 3. Run Multiple Clients Simultaneously

```bash
# Terminal 3: Another client instance
python run_ai_control_mcp.py --mcp

# Terminal 4: Terminal client
python -m src.client.terminal --mcp

# All clients share the same session through MCP!
```

## MCP Message Protocol

### Client → Server Messages

```python
# 1. Registration
{
    "type": "register",
    "client_id": "whatsapp_ai_abc123",
    "client_name": "whatsapp_client"
}

# 2. WhatsApp AI Command
{
    "type": "whatsapp_ai_command",
    "command": "send john a message saying hello",
    "context": {
        "last_contact": "Sarah",
        "contact_list": ["John", "Sarah", "Mike"]
    }
}

# 3. Direct WhatsApp Command
{
    "type": "whatsapp_command",
    "command": {
        "action": "send",
        "contact": "John",
        "message": "Hello!"
    }
}

# 4. AI Request
{
    "type": "ai_request",
    "prompt": "Summarize this conversation",
    "context": "Chat history here..."
}
```

### Server → Client Messages

```python
# 1. Registration Confirmation
{
    "type": "registration_confirmed",
    "client_id": "whatsapp_ai_abc123"
}

# 2. Command Response
{
    "type": "response",
    "response_type": "whatsapp_command_result",
    "content": {
        "success": true,
        "contact": "John",
        "message": "Hello!"
    }
}

# 3. Contact List Broadcast
{
    "type": "contact_list_broadcast",
    "contacts": ["John", "Sarah", "Mike"],
    "total_count": 150
}
```

## Benefits of MCP Architecture

### 1. **Centralized AI Processing**
- Single Gemini service instance
- Consistent AI responses across clients
- Reduced API calls and costs

### 2. **Shared Session State**
- Multiple devices can control same WhatsApp
- Synchronized contact lists
- Shared conversation history

### 3. **Scalability**
- Add new clients without modifying core
- Load balancing capability
- Microservice-ready architecture

### 4. **Real-time Updates**
- WebSocket for instant communication
- Broadcasting to all connected clients
- Live session synchronization

### 5. **Modular Design**
- Swap AI providers (Gemini → GPT)
- Change storage backends
- Add new client types easily

## File Structure

```
src/
├── mcp/
│   ├── server.py          # MCP server with WhatsApp handlers
│   ├── client.py          # Base MCP client class
│   └── whatsapp_tools.py  # WhatsApp-specific tools
│
├── client/
│   ├── whatsapp_ai_control.py      # Original standalone
│   ├── whatsapp_ai_control_mcp.py  # MCP-enabled version
│   └── [other clients]
│
└── services/
    ├── gemini.py          # AI service
    └── database.py        # Storage service
```

## Running Tests

### Test 1: Basic MCP Connection
```bash
# Start MCP server
python -m src.mcp.server

# In another terminal
python -c "from src.mcp.client import MCPClient; import asyncio; client = MCPClient(); asyncio.run(client.connect())"
```

### Test 2: Multi-Client Session
```bash
# Terminal 1: MCP Server
python -m src.mcp.server

# Terminal 2: First client
python run_ai_control_mcp.py --mcp

# Terminal 3: Second client
python run_ai_control_mcp.py --mcp

# Both clients should share contact lists and session state
```

## Comparison: Standalone vs MCP

| Feature | Standalone | MCP Mode |
|---------|-----------|----------|
| **Setup** | Simple (1 process) | Complex (2+ processes) |
| **Performance** | Direct, fast | Small network overhead |
| **Multi-device** | Not supported | Full support |
| **Resource Usage** | Per-client AI | Shared AI instance |
| **Scaling** | Vertical only | Horizontal + Vertical |
| **Session Sharing** | No | Yes |
| **Best For** | Single user | Teams/Multiple devices |

## Commands Comparison

### Standalone Mode
```bash
# Simple, direct execution
python run_ai_control.py

# Everything runs in one process
# Direct Gemini API calls
# No session sharing
```

### MCP Mode
```bash
# Step 1: Start server
python -m src.mcp.server

# Step 2: Start client(s)
python run_ai_control_mcp.py --mcp

# Distributed architecture
# Centralized AI processing
# Full session sharing
```

## Troubleshooting

### Issue: "Failed to connect to MCP server"
**Solution:** Ensure MCP server is running first:
```bash
python -m src.mcp.server
```

### Issue: "Port 8002 already in use"
**Solution:** Kill existing process or use different port:
```bash
# Kill existing
taskkill /F /IM python.exe

# Or use different port
# Edit .env: MCP_SERVER_PORT=8003
```

### Issue: "WebSocket connection closed"
**Solution:** Check firewall and ensure both client and server are on same network

## Advanced Configuration

### Custom MCP Server Settings
Edit `.env` file:
```env
MCP_SERVER_HOST=0.0.0.0  # Listen on all interfaces
MCP_SERVER_PORT=8002      # Change port if needed
```

### Running MCP Server in Docker
```dockerfile
# Dockerfile.mcp
FROM python:3.9
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["python", "-m", "src.mcp.server"]
```

```bash
docker build -f Dockerfile.mcp -t mcp-server .
docker run -p 8002:8002 mcp-server
```

## Future Enhancements

1. **Authentication**: Add JWT tokens for secure connections
2. **Persistence**: Store session state in Redis
3. **Load Balancing**: Multiple MCP servers with HAProxy
4. **Monitoring**: Add Prometheus metrics
5. **Web Dashboard**: Real-time client monitoring UI

## Summary

MCP architecture transforms your WhatsApp AI system from a single-user tool to an enterprise-ready platform with:

- ✅ Centralized control
- ✅ Multi-client support
- ✅ Shared AI processing
- ✅ Real-time synchronization
- ✅ Scalable architecture

Use **Standalone** for simplicity, use **MCP** for power!