from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING, TEXT
from bson import ObjectId

from src.utils.config import settings
from src.models.user import User
from src.models.conversation import Conversation, ConversationType
from src.models.message import Message, MessageType, MessageDirection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseService:
    def __init__(self):
        self.client = None
        self.db = None
        self.users_collection = None
        self.conversations_collection = None
        self.messages_collection = None
    
    async def initialize(self):
        try:
            self.client = AsyncIOMotorClient(settings.DATABASE_URL)
            self.db = self.client.conversation_assistant
            
            self.users_collection = self.db.users
            self.conversations_collection = self.db.conversations
            self.messages_collection = self.db.messages
            
            await self.create_indexes()
            
            logger.info("Database service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    async def create_indexes(self):
        await self.users_collection.create_index([("phone_number", ASCENDING)], unique=True, sparse=True)
        await self.users_collection.create_index([("created_at", DESCENDING)])
        
        await self.conversations_collection.create_index([("participants", ASCENDING)])
        await self.conversations_collection.create_index([("updated_at", DESCENDING)])
        await self.conversations_collection.create_index([("created_at", DESCENDING)])
        
        await self.messages_collection.create_index([("conversation_id", ASCENDING)])
        await self.messages_collection.create_index([("sender_id", ASCENDING)])
        await self.messages_collection.create_index([("timestamp", DESCENDING)])
        await self.messages_collection.create_index([("content", TEXT)])
    
    async def get_or_create_user(self, user_id: str, name: Optional[str] = None) -> Dict[str, Any]:
        user = await self.users_collection.find_one({"_id": user_id})
        
        if not user:
            user_data = {
                "_id": user_id,
                "name": name,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "is_active": True,
                "metadata": {}
            }
            
            await self.users_collection.insert_one(user_data)
            user = user_data
        elif name and not user.get("name"):
            await self.users_collection.update_one(
                {"_id": user_id},
                {"$set": {"name": name, "updated_at": datetime.utcnow()}}
            )
            user["name"] = name
        
        return user
    
    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        return await self.users_collection.find_one({"_id": user_id})
    
    async def create_conversation(
        self,
        participants: List[str],
        conversation_type: ConversationType = ConversationType.DIRECT,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        conversation_data = {
            "type": conversation_type.value,
            "participants": participants,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "message_count": 0,
            "metadata": metadata or {},
            "is_active": True
        }
        
        result = await self.conversations_collection.insert_one(conversation_data)
        conversation_data["_id"] = result.inserted_id
        
        return conversation_data
    
    async def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        try:
            obj_id = ObjectId(conversation_id)
            return await self.conversations_collection.find_one({"_id": obj_id})
        except:
            return await self.conversations_collection.find_one({"_id": conversation_id})
    
    async def get_user_conversations(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        cursor = self.conversations_collection.find(
            {"participants": user_id, "is_active": True}
        ).sort("updated_at", DESCENDING).limit(limit)
        
        conversations = []
        async for conv in cursor:
            conversations.append(conv)
        
        return conversations
    
    async def add_message(
        self,
        conversation_id: str,
        sender_id: str,
        content: str,
        message_type: MessageType = MessageType.TEXT,
        direction: MessageDirection = MessageDirection.INCOMING,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        message_data = {
            "conversation_id": conversation_id,
            "sender_id": sender_id,
            "type": message_type.value,
            "direction": direction.value,
            "content": content,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow(),
            "is_deleted": False
        }
        
        result = await self.messages_collection.insert_one(message_data)
        message_data["_id"] = result.inserted_id
        
        try:
            conv_obj_id = ObjectId(conversation_id)
        except:
            conv_obj_id = conversation_id
        
        await self.conversations_collection.update_one(
            {"_id": conv_obj_id},
            {
                "$inc": {"message_count": 1},
                "$set": {
                    "updated_at": datetime.utcnow(),
                    "last_message_at": datetime.utcnow()
                }
            }
        )
        
        return message_data
    
    async def get_messages(
        self,
        conversation_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        cursor = self.messages_collection.find(
            {"conversation_id": conversation_id, "is_deleted": False}
        ).sort("timestamp", ASCENDING).skip(offset).limit(limit)
        
        messages = []
        async for msg in cursor:
            messages.append(msg)
        
        return messages
    
    async def get_recent_messages(
        self,
        conversation_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        cursor = self.messages_collection.find(
            {"conversation_id": conversation_id, "is_deleted": False}
        ).sort("timestamp", DESCENDING).limit(limit)
        
        messages = []
        async for msg in cursor:
            messages.append(msg)
        
        return list(reversed(messages))
    
    async def get_last_message(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        return await self.messages_collection.find_one(
            {"conversation_id": conversation_id, "is_deleted": False},
            sort=[("timestamp", DESCENDING)]
        )
    
    async def search_messages(
        self,
        query: str,
        user_id: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        search_filter = {
            "$text": {"$search": query},
            "is_deleted": False
        }
        
        if user_id:
            user_conversations = await self.get_user_conversations(user_id, limit=100)
            conv_ids = [str(conv["_id"]) for conv in user_conversations]
            search_filter["conversation_id"] = {"$in": conv_ids}
        
        cursor = self.messages_collection.find(
            search_filter,
            {"score": {"$meta": "textScore"}}
        ).sort([("score", {"$meta": "textScore"})]).limit(limit)
        
        results = []
        async for msg in cursor:
            results.append(msg)
        
        return results
    
    async def delete_message(self, message_id: str) -> bool:
        try:
            obj_id = ObjectId(message_id)
        except:
            obj_id = message_id
        
        result = await self.messages_collection.update_one(
            {"_id": obj_id},
            {"$set": {"is_deleted": True, "updated_at": datetime.utcnow()}}
        )
        
        return result.modified_count > 0
    
    async def update_user_metadata(self, user_id: str, metadata: Dict[str, Any]) -> bool:
        result = await self.users_collection.update_one(
            {"_id": user_id},
            {
                "$set": {
                    "metadata": metadata,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        return result.modified_count > 0
    
    async def get_conversation_stats(self, conversation_id: str) -> Dict[str, Any]:
        try:
            obj_id = ObjectId(conversation_id)
        except:
            obj_id = conversation_id
        
        pipeline = [
            {"$match": {"conversation_id": str(obj_id), "is_deleted": False}},
            {"$group": {
                "_id": "$sender_id",
                "count": {"$sum": 1},
                "first_message": {"$min": "$timestamp"},
                "last_message": {"$max": "$timestamp"}
            }}
        ]
        
        cursor = self.messages_collection.aggregate(pipeline)
        
        stats = {
            "participants": {},
            "total_messages": 0,
            "conversation_id": conversation_id
        }
        
        async for result in cursor:
            sender = result["_id"]
            stats["participants"][sender] = {
                "message_count": result["count"],
                "first_message": result["first_message"].isoformat(),
                "last_message": result["last_message"].isoformat()
            }
            stats["total_messages"] += result["count"]
        
        return stats
    
    async def close(self):
        if self.client:
            self.client.close()
            logger.info("Database connection closed")