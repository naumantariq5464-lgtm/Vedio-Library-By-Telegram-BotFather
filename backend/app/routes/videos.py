from fastapi import APIRouter, Depends, HTTPException, Header, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import httpx
import time
import logging

from app.database import get_db
from app.models import Video
from app.schemas import VideoResponse
from app.telegram import get_telegram_file_download_url

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/videos", tags=["Public Videos"])

# ─── In-process URL cache ─────────────────────────────────────
# Telegram getFile URLs are valid ~1 hour. Cache them to avoid
# one extra API round-trip on every range request (seek, buffering).
_url_cache: dict[int, tuple[str, float]] = {}   # video_id → (url, timestamp)
_URL_TTL = 3000  # 50 minutes — safely below Telegram's 1-hour expiry


async def _get_stream_url(video_id: int, file_id: str) -> str:
    now = time.monotonic()
    cached = _url_cache.get(video_id)
    if cached and (now - cached[1]) < _URL_TTL:
        return cached[0]
    url = await get_telegram_file_download_url(file_id)
    _url_cache[video_id] = (url, now)
    return url


@router.get("", response_model=List[VideoResponse])
async def list_videos(db: AsyncSession = Depends(get_db)):
    stmt = select(Video).order_by(Video.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{video_id}", response_model=VideoResponse)
async def get_video(video_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Video).where(Video.id == video_id)
    result = await db.execute(stmt)
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Video with ID {video_id} not found")
    return video


@router.get("/{video_id}/stream")
async def stream_video(
    video_id: int,
    range: str = Header(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Streams video from Telegram with Range request support (206 Partial Content).
    Caches the Telegram file URL to avoid redundant getFile calls on every seek.
    """
    stmt = select(Video).where(Video.id == video_id)
    result = await db.execute(stmt)
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Video record not found")

    download_url = await _get_stream_url(video_id, video.telegram_file_id)

    req_headers: dict = {"Accept-Encoding": "identity"}
    if range:
        req_headers["Range"] = range

    # Use a longer timeout for actual video bytes delivery
    client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=30.0),
                                follow_redirects=True)
    req = client.build_request("GET", download_url, headers=req_headers)
    resp = await client.send(req, stream=True)

    # If the cached URL has expired, evict and retry once
    if resp.status_code in (401, 403, 404):
        await resp.aclose()
        await client.aclose()
        _url_cache.pop(video_id, None)
        download_url = await _get_stream_url(video_id, video.telegram_file_id)
        client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=30.0),
                                    follow_redirects=True)
        req = client.build_request("GET", download_url, headers=req_headers)
        resp = await client.send(req, stream=True)

    if resp.status_code not in (200, 206):
        await resp.aclose()
        await client.aclose()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail="Failed to retrieve media stream from Telegram storage")

    async def _stream():
        try:
            async for chunk in resp.aiter_bytes(chunk_size=256 * 1024):
                yield chunk
        finally:
            await resp.aclose()
            await client.aclose()

    # Ensure Content-Length is always set so the HTML5 player can seek
    content_length = resp.headers.get("Content-Length") or str(video.file_size or 0)
    content_type = resp.headers.get("Content-Type", "video/mp4")

    out_headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": content_type,
        "Content-Length": content_length,
        "Cache-Control": "public, max-age=3600",
    }
    if "Content-Range" in resp.headers:
        out_headers["Content-Range"] = resp.headers["Content-Range"]

    return StreamingResponse(_stream(), status_code=resp.status_code, headers=out_headers)
