from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class ConversationType(str, Enum):
    DIRECT = "direct"
    GROUP = "group"


class Conversation(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    type: ConversationType = ConversationType.DIRECT
    participants: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_message_at: Optional[datetime] = None
    message_count: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    
    class Config:
        populate_by_name = True
        use_enum_values = True
        json_schema_extra = {
            "example": {
                "type": "direct",
                "participants": ["user_id_1", "user_id_2"],
                "message_count": 10,
                "is_active": True
            }
        }