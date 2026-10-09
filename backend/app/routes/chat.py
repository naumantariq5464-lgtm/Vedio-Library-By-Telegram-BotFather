"""
AI Chat endpoint — uses Google Gemini to answer questions about videos.

Features:
  - Local Disk Cache: Video files are cached on disk so they are never re-downloaded from Telegram twice.
  - Gemini File Cache: Uploaded Gemini File references are persisted to disk (gemini_cache.json, valid for 47h).
  - Background Pre-warm: /api/videos/{video_id}/chat/prepare can be called when player opens.
  - Dynamic Fallback Models: gemini-3.8-flash -> gemini-flash-latest -> gemini-3.5-flash.
  - Processing State Polling: Waits until Gemini video processing state is ACTIVE.
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from pathlib import Path
import httpx
import logging
import time
import json
import asyncio
import os

from app.database import get_db, AsyncSessionLocal
from app.models import Video
from app.config import settings
from app.routes.videos import _get_stream_url

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/videos", tags=["AI Chat"])

# ─── Directories & Persistent Cache ──────────────────────────────────────────
CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)
GEMINI_CACHE_FILE = CACHE_DIR / "gemini_cache.json"
GEMINI_FILE_TTL = 46 * 3600  # 46 hours (Gemini files expire at 48h)

# Supported Gemini models in priority order
MODELS = ["gemini-3.8-flash", "gemini-flash-latest", "gemini-3.5-flash"]

# Lock to avoid duplicate concurrent uploads for the same video
_upload_locks: dict[int, asyncio.Lock] = {}


def _get_persistent_cache() -> dict:
    if GEMINI_CACHE_FILE.exists():
        try:
            with open(GEMINI_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_persistent_cache(data: dict):
    try:
        with open(GEMINI_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"[AI Chat] Could not save gemini cache: {e}")


# ─── Request / Response schemas ──────────────────────────────────────────────
class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str
    video_id: int


class PrepareResponse(BaseModel):
    status: str
    video_id: int


def _get_gemini_client():
    if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY.strip() in ("", "your_gemini_api_key_here"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gemini API key is not configured in backend/.env"
        )
    try:
        from google import genai
        return genai.Client(api_key=settings.GEMINI_API_KEY.strip())
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="google-genai library is not installed."
        )


async def _ensure_local_video(video_id: int, telegram_file_id: str) -> Path:
    """
    Downloads video from Telegram to local cache if not already present on disk.
    """
    local_path = CACHE_DIR / f"video_{video_id}.mp4"
    if local_path.exists() and local_path.stat().st_size > 1024:
        return local_path

    logger.info(f"[AI Chat] Downloading video {video_id} from Telegram to local disk cache...")
    download_url = await _get_stream_url(video_id, telegram_file_id)

    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=30.0), follow_redirects=True) as http_client:
        async with http_client.stream("GET", download_url) as resp:
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Failed to download video from Telegram storage."
                )
            temp_path = CACHE_DIR / f"video_{video_id}.tmp"
            with open(temp_path, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=1024 * 512):
                    f.write(chunk)
            if temp_path.exists():
                temp_path.replace(local_path)

    logger.info(f"[AI Chat] Video {video_id} downloaded to {local_path} ({local_path.stat().st_size} bytes)")
    return local_path


async def _get_or_upload_gemini_file(client, video_id: int, telegram_file_id: str, title: str):
    """
    Returns a valid Google Gemini File reference.
    Uses disk cache -> Gemini File API -> polls until ACTIVE.
    """
    from google.genai import types

    if video_id not in _upload_locks:
        _upload_locks[video_id] = asyncio.Lock()

    async with _upload_locks[video_id]:
        cache = _get_persistent_cache()
        entry = cache.get(str(video_id))
        now = time.time()

        if entry and (now - entry.get("uploaded_at", 0)) < GEMINI_FILE_TTL:
            file_name = entry.get("file_name")
            try:
                # Verify file is still valid and active on Gemini
                file_ref = client.files.get(name=file_name)
                if file_ref and file_ref.state.name == "ACTIVE":
                    return file_ref
            except Exception as e:
                logger.info(f"[AI Chat] Cached Gemini file expired or invalid ({e}), re-uploading...")

        # Step 1: Ensure we have the video file on disk
        local_path = await _ensure_local_video(video_id, telegram_file_id)

        # Step 2: Upload to Gemini File API
        logger.info(f"[AI Chat] Uploading {local_path} to Gemini...")
        display_name = f"video_{video_id}_{title[:30]}".replace(" ", "_")
        
        # Run synchronous upload in thread pool
        uploaded = await asyncio.to_thread(
            client.files.upload,
            file=str(local_path),
            config=types.UploadFileConfig(
                mime_type="video/mp4",
                display_name=display_name
            )
        )

        logger.info(f"[AI Chat] Uploaded to Gemini: {uploaded.name}, state={uploaded.state}")

        # Step 3: Wait for video processing if needed
        attempts = 0
        while uploaded.state.name == "PROCESSING" and attempts < 24:
            await asyncio.sleep(5)
            attempts += 1
            uploaded = await asyncio.to_thread(client.files.get, name=uploaded.name)

        if uploaded.state.name != "ACTIVE":
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Gemini video processing did not complete (state: {uploaded.state.name})"
            )

        # Save to persistent cache
        cache[str(video_id)] = {
            "file_name": uploaded.name,
            "uri": uploaded.uri,
            "uploaded_at": now
        }
        _save_persistent_cache(cache)
        logger.info(f"[AI Chat] Gemini file cached for video {video_id}: {uploaded.name}")
        return uploaded


# ─── Endpoints ───────────────────────────────────────────────────────────────

async def _bg_prepare_task(video_id: int):
    try:
        client = _get_gemini_client()
        async with AsyncSessionLocal() as session:
            stmt = select(Video).where(Video.id == video_id)
            res = await session.execute(stmt)
            video = res.scalar_one_or_none()
            if video:
                await _get_or_upload_gemini_file(client, video.id, video.telegram_file_id, video.title)
    except Exception as e:
        logger.warning(f"[AI Chat] Background pre-warm failed for video {video_id}: {e}")


@router.post("/{video_id}/chat/prepare", response_model=PrepareResponse)
async def prepare_video_chat(
    video_id: int,
    bg_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Called when video player opens. Quietly prepares the video for Gemini in background
    so user gets instant answers when they ask a question.
    """
    cache = _get_persistent_cache()
    entry = cache.get(str(video_id))
    if entry and (time.time() - entry.get("uploaded_at", 0)) < GEMINI_FILE_TTL:
        return PrepareResponse(status="ready", video_id=video_id)

    # Launch background preparation
    bg_tasks.add_task(_bg_prepare_task, video_id)
    return PrepareResponse(status="preparing", video_id=video_id)


@router.post("/{video_id}/chat", response_model=ChatResponse)
async def chat_with_video(
    video_id: int,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Ask an AI question about the video content.
    """
    question = body.question.strip()
    if not question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question cannot be empty."
        )

    # 1. Fetch video record
    stmt = select(Video).where(Video.id == video_id)
    result = await db.execute(stmt)
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video with ID {video_id} not found."
        )

    client = _get_gemini_client()

    # 2. Get active Gemini file reference
    file_ref = await _get_or_upload_gemini_file(client, video.id, video.telegram_file_id, video.title)

    # 3. System Prompt
    system_prompt = (
        f"You are a helpful, intelligent AI assistant for a Video Library. "
        f"The user is currently watching the video '{video.title}'. "
        "Analyze the video audio, visuals, text, and scenes carefully to answer the user's question accurately. "
        "If you mention specific events, include timestamps in format [mm:ss] or [hh:mm:ss]. "
        "Be concise, clear, and direct. Answer in the same language as the user's question."
    )

    # 4. Generate answer with model fallback and retry
    last_error = None
    for model_name in MODELS:
        for attempt in range(2):
            try:
                logger.info(f"[AI Chat] Querying Gemini model {model_name} for video {video_id}...")
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model_name,
                    contents=[file_ref, f"{system_prompt}\n\nQuestion: {question}"]
                )
                answer = (response.text or "").strip()
                if answer:
                    logger.info(f"[AI Chat] Success with {model_name}!")
                    return ChatResponse(answer=answer, video_id=video_id)
            except Exception as exc:
                last_error = exc
                logger.warning(f"[AI Chat] Attempt {attempt+1} with {model_name} failed: {exc}")
                await asyncio.sleep(1)

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Gemini could not generate an answer: {last_error}"
    )
