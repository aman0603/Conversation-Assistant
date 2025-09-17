from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"
    LOCATION = "location"
    CONTACT = "contact"
    STICKER = "sticker"
    SYSTEM = "system"


class MessageDirection(str, Enum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"
    SYSTEM = "system"


class Message(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    conversation_id: str
    sender_id: str
    whatsapp_message_id: Optional[str] = None
    type: MessageType = MessageType.TEXT
    direction: MessageDirection
    content: Optional[str] = None
    media_url: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    is_deleted: bool = False
    
    class Config:
        populate_by_name = True
        use_enum_values = True
        json_schema_extra = {
            "example": {
                "conversation_id": "conv_123",
                "sender_id": "user_123",
                "type": "text",
                "direction": "incoming",
                "content": "Hello, how are you?",
                "timestamp": "2024-01-01T12:00:00Z"
            }
        }