from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from datetime import datetime

router = APIRouter()


@router.get("/status")
async def webhook_status():
    return {
        "status": "MCP Server Active",
        "message": "This system uses MCP WebSocket protocol instead of webhooks",
        "mcp_endpoint": "ws://localhost:8001",
        "timestamp": datetime.utcnow().isoformat()
    }


@router.post("/legacy")
async def legacy_webhook_handler(data: Dict[str, Any]):
    raise HTTPException(
        status_code=501,
        detail="Webhook integration has been replaced with MCP server. Please use the terminal client to interact with the system."
    )