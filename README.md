# Conversation Assistant with MCP Server & WhatsApp Integration

A Python-based multi-user conversation assistant using Model Context Protocol (MCP) server architecture with both terminal and WhatsApp Web client interfaces. Features Google Gemini AI integration for intelligent conversation management and QR code-based WhatsApp authentication.

## Project Overview

This system captures WhatsApp conversations, provides intelligent assistance through LLM integration, and offers contextual summaries and alerts for multi-user conversations.

## Tech Stack

- **Backend**: FastAPI & MCP WebSocket Server
- **Database**: MongoDB (Motor) or PostgreSQL (SQLAlchemy)
- **Client Interfaces**: 
  - Terminal-based CLI with rich formatting
  - WhatsApp Web client with QR code authentication
- **AI Model**: Google Gemini API
- **Protocol**: Model Context Protocol (MCP) over WebSockets
- **Package Management**: uv
- **Deployment**: Docker
- **Testing**: pytest

## Architecture Overview

- **MCP Server**: WebSocket-based server handling all conversation logic
- **Terminal Client**: Interactive CLI for sending/receiving messages
- **Gemini Integration**: Direct integration with Google's Gemini API for AI responses
- **Database Layer**: Persistent storage for users, conversations, and messages
- **Real-time Communication**: WebSocket protocol for instant message delivery
- **Context Management**: Intelligent conversation context handling and memory

## Core Features

### 1. MCP Server Features
- WebSocket-based real-time communication
- Multi-client support with session management
- Message routing and processing
- Context-aware conversation handling

### 2. Database Management
- User and Conversation models
- Message history storage
- Efficient query capabilities

### 3. MCP Service Functions
- Load conversation history
- Append new messages
- Generate conversation summaries
- Context management for LLM interactions

### 4. Gemini AI Integration
- Direct Google Gemini API integration
- Context-aware response generation
- Conversation summarization
- Sentiment analysis and entity extraction

### 5. Client Features

#### Terminal Client
- Rich terminal interface with formatted output
- Command system for navigation and control
- Real-time message display
- Conversation management (list, load, create)
- Search functionality
- Interactive chat with AI assistant

#### WhatsApp Client
- QR code authentication (no API key required)
- Automatic session persistence
- Real-time message monitoring
- Sync WhatsApp messages to MCP server
- AI-powered responses via Gemini
- Support for multiple chats

## Project Structure

```
conversation-assistant/
├── src/
│   ├── api/                 # FastAPI routes
│   │   ├── __init__.py
│   │   ├── main.py         # FastAPI app entry point
│   │   └── routes/         # API route modules
│   ├── models/              # Database models
│   │   ├── __init__.py
│   │   ├── user.py         # User model
│   │   ├── conversation.py # Conversation model
│   │   └── message.py      # Message model
│   ├── services/            # Business logic
│   │   ├── __init__.py
│   │   ├── database.py     # Database operations
│   │   └── gemini.py       # Gemini AI integration
│   ├── mcp/                 # MCP service implementation
│   │   ├── __init__.py
│   │   ├── server.py       # MCP server
│   │   └── functions.py    # MCP service functions
│   ├── client/              # Terminal client
│   │   ├── __init__.py
│   │   └── terminal.py     # Terminal CLI interface
│   └── utils/               # Utility functions
│       ├── __init__.py
│       ├── config.py       # Configuration management
│       └── helpers.py      # Helper functions
├── tests/
│   ├── unit/               # Unit tests
│   └── integration/        # Integration tests
├── config/                  # Configuration files
│   ├── .env.example        # Environment variables template
│   └── settings.py         # Application settings
├── scripts/                 # Utility scripts
│   ├── setup.sh            # Setup script
│   └── migrate.py          # Database migration script
├── docs/                    # Documentation
├── docker/                  # Docker configuration
│   ├── Dockerfile
│   └── docker-compose.yml
├── pyproject.toml          # Project dependencies (uv)
├── .gitignore
├── .env
└── README.md

```

## Development Tasks

### Phase 1: Foundation
1. ✅ Scaffold project structure
2. ✅ Create README with requirements
3. Initialize uv project with dependencies
4. Set up Docker configuration

### Phase 2: Backend Development
1. Scaffold FastAPI backend with DB connection
2. Create User and Conversation models
3. Implement MCP WebSocket server

### Phase 3: AI Integration
1. Implement Gemini AI service
2. Build conversation context management
3. Add summarization and analysis features

### Phase 4: Client Development
1. Build terminal client interface
2. Implement WebSocket communication
3. Add command system
4. Create rich formatting and display

### Phase 5: Testing & Deployment
1. Write pytest unit tests
2. Create integration tests
3. Set up CI/CD pipeline
4. Deploy with Docker

## WhatsApp Integration

### How it Works
1. **QR Code Authentication**: The WhatsApp client opens a Chrome browser with WhatsApp Web
2. **Scan QR Code**: Use your phone's WhatsApp to scan the QR code (Settings > Linked Devices)
3. **Message Sync**: All WhatsApp messages are automatically synced to the MCP server
4. **AI Processing**: Messages are processed by Gemini AI for intelligent responses
5. **Persistent Session**: Browser session is saved for automatic reconnection

### Running WhatsApp Client

1. Make sure the MCP server is running:
```bash
uv run python -m src.mcp.server
```

2. Start the WhatsApp client:
```bash
uv run python -m src.client.whatsapp_qr_client
```

3. A Chrome browser will open with WhatsApp Web
4. Scan the QR code with your phone
5. The client will start monitoring and syncing messages

## Installation

### Prerequisites
- Python 3.11+
- uv package manager
- Docker (for deployment)
- WhatsApp Business API access
- MongoDB or PostgreSQL

### Setup Instructions

1. Clone the repository:
```bash
git clone <repository-url>
cd conversation-assistant
```

2. Install uv if not already installed:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

3. Create virtual environment and install dependencies:
```bash
uv venv
uv pip install -e .
```

4. Copy environment variables:
```bash
cp config/.env.example .env
```

5. Configure your environment variables in `.env`:
```
# Database
DATABASE_URL=mongodb://localhost:27017/conversation_assistant
# or for PostgreSQL:
# DATABASE_URL=postgresql://user:password@localhost/conversation_assistant

# Gemini API Configuration
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-1.5-flash
GEMINI_MAX_TOKENS=2000
GEMINI_TEMPERATURE=0.7

# MCP Server
MCP_SERVER_HOST=localhost
MCP_SERVER_PORT=8001

# FastAPI
API_HOST=0.0.0.0
API_PORT=8000
```

6. Run database migrations:
```bash
python scripts/migrate.py
```

7. Start the services:

**FastAPI Backend:**
```bash
uv run python -m src.api.main
```

**MCP Server:**
```bash
uv run python -m src.mcp.server
```

**Terminal Client:**
```bash
uv run python -m src.client.terminal
```

**WhatsApp Client (QR Code Authentication):**
```bash
uv run python -m src.client.whatsapp_qr_client
```

## Testing

Run unit tests:
```bash
uv run pytest tests/unit
```

Run integration tests:
```bash
uv run pytest tests/integration
```

Run all tests with coverage:
```bash
uv run pytest --cov=src tests/
```

## Docker Deployment

Build and run with Docker Compose:
```bash
docker-compose up --build
```

## API Endpoints

### MCP WebSocket Commands

The MCP server accepts the following message types:

- `initialize` - Initialize user session
- `send_message` - Send a message to the assistant
- `load_conversation` - Load existing conversation
- `list_conversations` - List all user conversations
- `create_conversation` - Create new conversation
- `get_summary` - Get conversation summary
- `search` - Search through messages

### Terminal Client Commands

- `/help` - Show available commands
- `/list` - List all conversations
- `/new` - Start new conversation
- `/load [id]` - Load specific conversation
- `/summary` - Get conversation summary
- `/search [query]` - Search messages
- `/user` - Show user info
- `/clear` - Clear screen
- `/exit` - Exit application

### MCP Service Functions

- `load_conversation(conversation_id)` - Load conversation from database
- `append_message(conversation_id, message)` - Add message to conversation
- `summarize_conversation(conversation_id)` - Generate conversation summary
- `get_context(conversation_id, query)` - Get relevant context for query

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Write/update tests
5. Submit a pull request

## License

[Specify your license here]

## Support

For issues and questions, please create an issue in the GitHub repository.