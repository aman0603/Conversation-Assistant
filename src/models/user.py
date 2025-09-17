from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class User(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    phone_number: str
    name: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True
    
    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "phone_number": "+1234567890",
                "name": "John Doe",
                "metadata": {"source": "whatsapp"},
                "is_active": True
            }
        }