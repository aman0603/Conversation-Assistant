from pydantic_settings import BaseSettings
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    DEBUG: bool = True
    
    DATABASE_URL: str = "mongodb://localhost:27017/conversation_assistant"
    DATABASE_TYPE: str = "mongodb"  # mongodb or postgresql
    
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-1.5-flash"
    GEMINI_MAX_TOKENS: int = 2000
    GEMINI_TEMPERATURE: float = 0.7
    GEMINI_TOP_P: float = 0.95
    GEMINI_TOP_K: int = 40
    
    MCP_SERVER_HOST: str = "localhost"
    MCP_SERVER_PORT: int = 8001
    
    REDIS_URL: str = "redis://localhost:6379"
    
    SECRET_KEY: str = "your-secret-key-here-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()