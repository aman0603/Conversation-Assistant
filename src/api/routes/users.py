from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()


class UserCreate(BaseModel):
    phone_number: str
    name: Optional[str] = None
    metadata: Optional[dict] = {}


class UserResponse(BaseModel):
    id: str
    phone_number: str
    name: Optional[str]
    created_at: datetime
    updated_at: datetime
    conversation_count: int


@router.get("/", response_model=List[UserResponse])
async def list_users(
    limit: int = 20,
    offset: int = 0
):
    # TODO: Fetch from database
    return []


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: str):
    # TODO: Fetch user from database
    raise HTTPException(status_code=404, detail="User not found")


@router.post("/", response_model=UserResponse)
async def create_user(user: UserCreate):
    # TODO: Create user in database
    return UserResponse(
        id="temp_id",
        phone_number=user.phone_number,
        name=user.name,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        conversation_count=0
    )


@router.get("/{user_id}/conversations")
async def get_user_conversations(
    user_id: str,
    limit: int = 20,
    offset: int = 0
):
    # TODO: Fetch user's conversations from database
    return {
        "user_id": user_id,
        "conversations": [],
        "total": 0
    }