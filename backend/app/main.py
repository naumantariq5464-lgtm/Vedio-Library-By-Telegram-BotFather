from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.config import settings
from app.database import init_db
from app.routes import auth, admin, videos
from app.routes import chat

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("uvicorn.error")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Video Library FastAPI Backend...")
    try:
        await init_db()
    except Exception as e:
        logger.warning(f"Database table initialization warning: {e}")
    yield
    logger.info("Shutting down Video Library FastAPI Backend...")

app = FastAPI(
    title="Video Library Backend API",
    description="FastAPI Backend for Video Library with Telegram Media Storage & PostgreSQL Metadata Indexing",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(videos.router)
app.include_router(chat.router)

@app.get("/", tags=["Health Check"])
async def root():
    return {
        "status": "online",
        "message": "Video Library API is running smoothly",
        "documentation": "/docs"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
