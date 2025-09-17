"""
WhatsApp MCP Tools
Provides all WhatsApp operations as MCP tools that can be used by the terminal client.
Works with the whatsapp-bridge Go application.
"""

import sqlite3
import requests
import json
import os
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration - these should match your whatsapp-bridge setup
MESSAGES_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'whatsapp-mcp', 'whatsapp-bridge', 'store', 'messages.db')
WHATSAPP_API_BASE_URL = "http://localhost:8080/api"


@dataclass
class Message:
    timestamp: datetime
    sender: str
    content: str
    is_from_me: bool
    chat_jid: str
    id: str
    chat_name: Optional[str] = None
    media_type: Optional[str] = None


@dataclass
class Chat:
    jid: str
    name: Optional[str]
    last_message_time: Optional[datetime]
    last_message: Optional[str] = None
    last_sender: Optional[str] = None
    last_is_from_me: Optional[bool] = None

    @property
    def is_group(self) -> bool:
        return self.jid.endswith("@g.us")


@dataclass
class Contact:
    phone_number: str
    name: Optional[str]
    jid: str


class WhatsAppTools:
    """MCP Tools for WhatsApp operations"""
    
    def __init__(self):
        self.db_path = MESSAGES_DB_PATH
        self.api_url = WHATSAPP_API_BASE_URL
        
    def _get_db_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)
    
    def search_contacts(self, query: str) -> List[Dict[str, Any]]:
        """Search WhatsApp contacts by name or phone number"""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT DISTINCT jid, name
                FROM chats
                WHERE (LOWER(name) LIKE LOWER(?) OR jid LIKE ?)
                AND jid NOT LIKE '%@g.us'
                ORDER BY name
            """, (f"%{query}%", f"%{query}%"))
            
            contacts = []
            for row in cursor.fetchall():
                contacts.append({
                    "jid": row[0],
                    "name": row[1] or row[0],
                    "phone_number": row[0].split("@")[0] if "@" in row[0] else row[0]
                })
            
            conn.close()
            return contacts
            
        except Exception as e:
            logger.error(f"Error searching contacts: {e}")
            return []
    
    def list_chats(
        self,
        query: Optional[str] = None,
        limit: int = 20,
        include_last_message: bool = True,
        sort_by: str = "last_active"
    ) -> List[Dict[str, Any]]:
        """Get WhatsApp chats matching criteria"""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            
            # Build query
            query_parts = ["""
                SELECT DISTINCT 
                    c.jid,
                    c.name,
                    MAX(m.timestamp) as last_message_time
            """]
            
            if include_last_message:
                query_parts[0] += """,
                    (SELECT content FROM messages WHERE chat_jid = c.jid ORDER BY timestamp DESC LIMIT 1) as last_message,
                    (SELECT sender FROM messages WHERE chat_jid = c.jid ORDER BY timestamp DESC LIMIT 1) as last_sender,
                    (SELECT is_from_me FROM messages WHERE chat_jid = c.jid ORDER BY timestamp DESC LIMIT 1) as last_is_from_me
                """
            
            query_parts.append("FROM chats c LEFT JOIN messages m ON c.jid = m.chat_jid")
            
            where_clauses = []
            params = []
            
            if query:
                where_clauses.append("(LOWER(c.name) LIKE LOWER(?) OR c.jid LIKE ?)")
                params.extend([f"%{query}%", f"%{query}%"])
            
            if where_clauses:
                query_parts.append("WHERE " + " AND ".join(where_clauses))
            
            query_parts.append("GROUP BY c.jid, c.name")
            
            if sort_by == "last_active":
                query_parts.append("ORDER BY last_message_time DESC")
            else:
                query_parts.append("ORDER BY c.name")
            
            query_parts.append(f"LIMIT {limit}")
            
            cursor.execute(" ".join(query_parts), params)
            
            chats = []
            for row in cursor.fetchall():
                chat = {
                    "jid": row[0],
                    "name": row[1] or row[0],
                    "last_message_time": row[2],
                    "is_group": row[0].endswith("@g.us")
                }
                
                if include_last_message and len(row) > 3:
                    chat["last_message"] = row[3]
                    chat["last_sender"] = row[4]
                    chat["last_is_from_me"] = bool(row[5]) if row[5] is not None else None
                
                chats.append(chat)
            
            conn.close()
            return chats
            
        except Exception as e:
            logger.error(f"Error listing chats: {e}")
            return []
    
    def list_messages(
        self,
        chat_jid: Optional[str] = None,
        sender_phone: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 20,
        after: Optional[str] = None,
        before: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get messages matching criteria"""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            
            query_parts = ["""
                SELECT 
                    m.id,
                    m.timestamp,
                    m.sender,
                    m.content,
                    m.is_from_me,
                    m.chat_jid,
                    c.name as chat_name,
                    m.media_type
                FROM messages m
                JOIN chats c ON m.chat_jid = c.jid
            """]
            
            where_clauses = []
            params = []
            
            if chat_jid:
                where_clauses.append("m.chat_jid = ?")
                params.append(chat_jid)
            
            if sender_phone:
                where_clauses.append("m.sender = ?")
                params.append(sender_phone)
            
            if query:
                where_clauses.append("LOWER(m.content) LIKE LOWER(?)")
                params.append(f"%{query}%")
            
            if after:
                where_clauses.append("m.timestamp > ?")
                params.append(after)
            
            if before:
                where_clauses.append("m.timestamp < ?")
                params.append(before)
            
            if where_clauses:
                query_parts.append("WHERE " + " AND ".join(where_clauses))
            
            query_parts.append("ORDER BY m.timestamp DESC")
            query_parts.append(f"LIMIT {limit}")
            
            cursor.execute(" ".join(query_parts), params)
            
            messages = []
            for row in cursor.fetchall():
                messages.append({
                    "id": row[0],
                    "timestamp": row[1],
                    "sender": row[2],
                    "content": row[3],
                    "is_from_me": bool(row[4]),
                    "chat_jid": row[5],
                    "chat_name": row[6] or row[5],
                    "media_type": row[7]
                })
            
            conn.close()
            return messages
            
        except Exception as e:
            logger.error(f"Error listing messages: {e}")
            return []
    
    def send_message(self, recipient: str, message: str) -> Tuple[bool, str]:
        """Send a WhatsApp message"""
        try:
            # Ensure recipient has proper JID format
            if not recipient.endswith("@s.whatsapp.net") and not recipient.endswith("@g.us"):
                if "@" not in recipient:
                    recipient = f"{recipient}@s.whatsapp.net"
            
            url = f"{self.api_url}/send"
            payload = {
                "recipient": recipient,
                "message": message
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                return result.get("success", False), result.get("message", "Message sent")
            else:
                return False, f"Server returned status {response.status_code}"
                
        except requests.exceptions.ConnectionError:
            return False, "Cannot connect to WhatsApp bridge. Make sure it's running on port 8080"
        except Exception as e:
            return False, f"Error sending message: {str(e)}"
    
    def send_file(self, recipient: str, file_path: str) -> Tuple[bool, str]:
        """Send a file via WhatsApp"""
        try:
            if not os.path.exists(file_path):
                return False, f"File not found: {file_path}"
            
            # Ensure recipient has proper JID format
            if not recipient.endswith("@s.whatsapp.net") and not recipient.endswith("@g.us"):
                if "@" not in recipient:
                    recipient = f"{recipient}@s.whatsapp.net"
            
            url = f"{self.api_url}/send"
            payload = {
                "recipient": recipient,
                "media_path": file_path
            }
            
            response = requests.post(url, json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                return result.get("success", False), result.get("message", "File sent")
            else:
                return False, f"Server returned status {response.status_code}"
                
        except requests.exceptions.ConnectionError:
            return False, "Cannot connect to WhatsApp bridge. Make sure it's running on port 8080"
        except Exception as e:
            return False, f"Error sending file: {str(e)}"
    
    def download_media(self, message_id: str, chat_jid: str) -> Optional[str]:
        """Download media from a WhatsApp message"""
        try:
            url = f"{self.api_url}/download"
            payload = {
                "message_id": message_id,
                "chat_jid": chat_jid
            }
            
            response = requests.post(url, json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if result.get("success", False):
                    return result.get("path")
            
            return None
            
        except Exception as e:
            logger.error(f"Error downloading media: {e}")
            return None
    
    def get_chat_info(self, chat_jid: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a chat"""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            
            # Get chat info
            cursor.execute("""
                SELECT jid, name
                FROM chats
                WHERE jid = ?
            """, (chat_jid,))
            
            chat_row = cursor.fetchone()
            if not chat_row:
                conn.close()
                return None
            
            # Get message stats
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_messages,
                    SUM(CASE WHEN is_from_me = 1 THEN 1 ELSE 0 END) as sent_messages,
                    SUM(CASE WHEN is_from_me = 0 THEN 1 ELSE 0 END) as received_messages,
                    MIN(timestamp) as first_message,
                    MAX(timestamp) as last_message
                FROM messages
                WHERE chat_jid = ?
            """, (chat_jid,))
            
            stats_row = cursor.fetchone()
            
            chat_info = {
                "jid": chat_row[0],
                "name": chat_row[1] or chat_row[0],
                "is_group": chat_row[0].endswith("@g.us"),
                "stats": {
                    "total_messages": stats_row[0] or 0,
                    "sent_messages": stats_row[1] or 0,
                    "received_messages": stats_row[2] or 0,
                    "first_message": stats_row[3],
                    "last_message": stats_row[4]
                }
            }
            
            conn.close()
            return chat_info
            
        except Exception as e:
            logger.error(f"Error getting chat info: {e}")
            return None
    
    def search_all(self, query: str, limit: int = 50) -> Dict[str, List[Dict[str, Any]]]:
        """Search across messages, chats, and contacts"""
        results = {
            "messages": self.list_messages(query=query, limit=limit//3),
            "chats": self.list_chats(query=query, limit=limit//3),
            "contacts": self.search_contacts(query=query)
        }
        return results


# Create a global instance
whatsapp_tools = WhatsAppTools()


# Export functions that can be used as MCP tools
def search_contacts(query: str) -> List[Dict[str, Any]]:
    """Search WhatsApp contacts by name or phone number"""
    return whatsapp_tools.search_contacts(query)


def list_chats(
    query: Optional[str] = None,
    limit: int = 20,
    include_last_message: bool = True,
    sort_by: str = "last_active"
) -> List[Dict[str, Any]]:
    """Get WhatsApp chats"""
    return whatsapp_tools.list_chats(query, limit, include_last_message, sort_by)


def list_messages(
    chat_jid: Optional[str] = None,
    sender_phone: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 20,
    after: Optional[str] = None,
    before: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Get WhatsApp messages"""
    return whatsapp_tools.list_messages(chat_jid, sender_phone, query, limit, after, before)


def send_message(recipient: str, message: str) -> Tuple[bool, str]:
    """Send a WhatsApp message"""
    return whatsapp_tools.send_message(recipient, message)


def send_file(recipient: str, file_path: str) -> Tuple[bool, str]:
    """Send a file via WhatsApp"""
    return whatsapp_tools.send_file(recipient, file_path)


def download_media(message_id: str, chat_jid: str) -> Optional[str]:
    """Download media from a WhatsApp message"""
    return whatsapp_tools.download_media(message_id, chat_jid)


def get_chat_info(chat_jid: str) -> Optional[Dict[str, Any]]:
    """Get detailed information about a chat"""
    return whatsapp_tools.get_chat_info(chat_jid)


def search_all(query: str, limit: int = 50) -> Dict[str, List[Dict[str, Any]]]:
    """Search across messages, chats, and contacts"""
    return whatsapp_tools.search_all(query, limit)