import httpx
import ssl
from fastapi import HTTPException, status
from app.config import settings
import logging

logger = logging.getLogger("uvicorn.error")

def get_telegram_api_base() -> str:
    base = settings.TELEGRAM_BASE_URL.rstrip('/')
    return f"{base}/bot{settings.TELEGRAM_BOT_TOKEN}"

def get_telegram_file_base() -> str:
    base = settings.TELEGRAM_BASE_URL.rstrip('/')
    return f"{base}/file/bot{settings.TELEGRAM_BOT_TOKEN}"

def _get_client(timeout: float = 300.0) -> httpx.AsyncClient:
    """Create httpx client with extended timeouts for media transfers."""
    transport = httpx.AsyncHTTPTransport(retries=2, verify=True)
    return httpx.AsyncClient(
        transport=transport,
        headers={"User-Agent": "VideoLibraryBackend/1.0"},
        timeout=httpx.Timeout(timeout, connect=60.0),
        follow_redirects=True
    )

async def upload_video_to_telegram(file_bytes: bytes, filename: str, title: str):
    """
    Sends video bytes to the configured Private Telegram Channel using the Bot API.
    Returns metadata dict: {file_id, message_id, channel_id, file_size, duration}
    """
    max_bytes = 50 * 1024 * 1024  # 50MB Telegram Bot API limit
    if len(file_bytes) > max_bytes:
        file_mb = round(len(file_bytes) / (1024 * 1024), 1)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Telegram Bot API restricts file uploads to 50 MB maximum. Selected file is {file_mb} MB. Please select a video under 50 MB."
        )

    api_base = get_telegram_api_base()
    url = f"{api_base}/sendVideo"
    
    data = {
        "chat_id": settings.TELEGRAM_CHANNEL_ID,
        "caption": f"🎬 {title}\n\nUploaded via Video Library Website",
        "supports_streaming": "true"
    }
    
    files = {
        "video": (filename, file_bytes, "video/mp4")
    }
    
    async with _get_client(timeout=600.0) as client:
        try:
            logger.info(f"Uploading '{title}' ({len(file_bytes)} bytes) to Telegram via {settings.TELEGRAM_BASE_URL}...")
            response = await client.post(url, data=data, files=files)
            res_json = response.json()
            
            if not response.is_success or not res_json.get("ok"):
                logger.error(f"Telegram sendVideo failed: {res_json}")
                # Fallback to sendDocument if sendVideo fails
                doc_url = f"{api_base}/sendDocument"
                doc_files = {"document": (filename, file_bytes, "application/octet-stream")}
                doc_response = await client.post(doc_url, data={"chat_id": settings.TELEGRAM_CHANNEL_ID, "caption": title}, files=doc_files)
                doc_json = doc_response.json()
                
                if not doc_response.is_success or not doc_json.get("ok"):
                    err_msg = doc_json.get('description', 'Unknown Telegram Error')
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=f"Telegram API Upload Error: {err_msg}"
                    )
                res_json = doc_json

            result = res_json["result"]
            message_id = result["message_id"]
            chat_id = str(result["chat"]["id"])
            
            # Extract video or document file_id
            if "video" in result:
                file_id = result["video"]["file_id"]
                file_size = result["video"].get("file_size", len(file_bytes))
                duration = result["video"].get("duration", 0)
            elif "document" in result:
                file_id = result["document"]["file_id"]
                file_size = result["document"].get("file_size", len(file_bytes))
                duration = 0
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Telegram response did not contain valid video or document payload"
                )

            logger.info(f"Telegram upload successful! file_id={file_id[:20]}..., message_id={message_id}")
            return {
                "telegram_file_id": file_id,
                "telegram_message_id": message_id,
                "channel_id": chat_id,
                "file_size": file_size,
                "duration": duration
            }

        except httpx.RequestError as exc:
            logger.error(f"HTTP error uploading to Telegram: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Network error connecting to Telegram Bot API: {str(exc)}"
            )

async def delete_video_from_telegram(message_id: int) -> bool:
    """
    Deletes the video post from the Telegram Channel.
    """
    url = f"{get_telegram_api_base()}/deleteMessage"
    data = {
        "chat_id": settings.TELEGRAM_CHANNEL_ID,
        "message_id": message_id
    }
    async with _get_client(timeout=30.0) as client:
        try:
            res = await client.post(url, data=data)
            return res.is_success and res.json().get("ok", False)
        except Exception as e:
            logger.warning(f"Could not delete message {message_id} from Telegram: {e}")
            return False

async def get_telegram_file_download_url(telegram_file_id: str) -> str:
    """
    Resolves telegram_file_id into a temporary direct download path using Telegram getFile endpoint.
    """
    url = f"{get_telegram_api_base()}/getFile"
    params = {"file_id": telegram_file_id}
    
    async with _get_client(timeout=30.0) as client:
        res = await client.get(url, params=params)
        res_json = res.json()
        
        if not res.is_success or not res_json.get("ok"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Telegram Media File not found: {res_json.get('description', 'Unknown error')}"
            )
        
        file_path = res_json["result"]["file_path"]
        return f"{get_telegram_file_base()}/{file_path}"
