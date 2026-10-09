from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class AdminLoginRequest(BaseModel):
    email: str = Field(..., example="admin@example.com")
    password: str = Field(..., example="admin123")

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class VideoResponse(BaseModel):
    id: int
    title: str
    telegram_file_id: str
    telegram_message_id: int
    channel_id: str
    file_size: int
    duration: int
    created_at: datetime

    class Config:
        from_attributes = True

class VideoPublicResponse(BaseModel):
    id: int
    title: str
    file_size: int
    duration: int
    created_at: datetime

    class Config:
        from_attributes = True

class MessageResponse(BaseModel):
    message: str
    detail: Optional[str] = None
