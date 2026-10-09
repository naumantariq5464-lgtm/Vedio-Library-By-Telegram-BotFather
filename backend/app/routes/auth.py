from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from app.schemas import TokenResponse
from app.auth import verify_password, create_access_token
from app.config import settings
import logging

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/api/admin", tags=["Admin Auth"])

@router.post("/login", response_model=TokenResponse)
async def admin_login(form_data: OAuth2PasswordRequestForm = Depends()):
    logger.info(f"Login attempt — username: {repr(form_data.username)}, password: {repr(form_data.password)}")
    logger.info(f"Expected email: {repr(settings.ADMIN_EMAIL)}, Expected pwd: {repr(settings.ADMIN_PASSWORD)}")
    logger.info(f"Email match: {form_data.username == settings.ADMIN_EMAIL}")
    logger.info(f"Password match: {form_data.password == settings.ADMIN_PASSWORD}")

    if form_data.username != settings.ADMIN_EMAIL:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if not verify_password(form_data.password, settings.ADMIN_PASSWORD):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    access_token = create_access_token(data={"sub": settings.ADMIN_EMAIL})
    return TokenResponse(access_token=access_token, token_type="bearer")
