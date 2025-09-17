from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn
from src.utils.config import settings
from src.api.routes import health, conversations, users, webhooks


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting up Conversation Assistant API...")
    yield
    print("Shutting down Conversation Assistant API...")


app = FastAPI(
    title="Conversation Assistant API",
    description="Multi-user conversation assistant with WhatsApp integration",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(webhooks.router, prefix="/api/webhook", tags=["webhooks"])
app.include_router(conversations.router, prefix="/api/conversations", tags=["conversations"])
app.include_router(users.router, prefix="/api/users", tags=["users"])


def main():
    uvicorn.run(
        "src.api.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
    )


if __name__ == "__main__":
    main()