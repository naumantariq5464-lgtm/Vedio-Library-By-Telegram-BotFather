from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import Video
from app.schemas import VideoResponse, MessageResponse
from app.auth import get_current_admin
from app.telegram import upload_video_to_telegram, delete_video_from_telegram
import logging

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/admin", tags=["Admin Operations"])

@router.post("/videos", response_model=VideoResponse, status_code=status.HTTP_201_CREATED)
async def upload_video(
    title: str = Form(...),
    file: UploadFile = File(...),
    current_admin: str = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    title = title.strip()
    if not title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Video title cannot be empty."
        )

    filename = file.filename or "video.mp4"
    file_bytes = await file.read()
    
    if not file_bytes or len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty."
        )

    logger.info(f"Admin '{current_admin}' uploading video '{title}' ({len(file_bytes)} bytes)...")

    # Step 1: Upload media file to Private Telegram Channel
    telegram_res = await upload_video_to_telegram(file_bytes, filename, title)

    # Step 2: Store Metadata in PostgreSQL Database
    try:
        new_video = Video(
            title=title,
            telegram_file_id=telegram_res["telegram_file_id"],
            telegram_message_id=telegram_res["telegram_message_id"],
            channel_id=telegram_res["channel_id"],
            file_size=telegram_res["file_size"],
            duration=telegram_res["duration"]
        )
        db.add(new_video)
        await db.commit()
        await db.refresh(new_video)
        logger.info(f"Successfully published video '{title}' with DB ID {new_video.id}")

        # Cache video on local disk for instant streaming / Gemini AI processing
        try:
            from pathlib import Path
            cache_dir = Path("cache")
            cache_dir.mkdir(exist_ok=True)
            with open(cache_dir / f"video_{new_video.id}.mp4", "wb") as f:
                f.write(file_bytes)
            logger.info(f"Video {new_video.id} cached to disk.")
        except Exception as ce:
            logger.warning(f"Could not cache video to disk: {ce}")

        return new_video
    except Exception as e:
        await db.rollback()
        logger.error(f"Database insertion error after Telegram upload: {e}")
        # Rollback: attempt cleanup on Telegram
        await delete_video_from_telegram(telegram_res["telegram_message_id"])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database record creation failed: {str(e)}"
        )

@router.delete("/videos/{video_id}", response_model=MessageResponse)
async def delete_video(
    video_id: int,
    current_admin: str = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Video).where(Video.id == video_id)
    result = await db.execute(stmt)
    video = result.scalar_one_or_none()

    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video with ID {video_id} not found."
        )

    # Delete message post in Telegram Channel
    await delete_video_from_telegram(video.telegram_message_id)

    # Delete record from database
    await db.delete(video)
    await db.commit()

    logger.info(f"Admin '{current_admin}' deleted video ID {video_id}")
    return MessageResponse(message=f"Video '{video.title}' (ID: {video_id}) deleted successfully.")
