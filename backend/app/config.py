import os
from urllib.parse import urlparse, parse_qs, urlunparse
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
from pydantic import field_validator

class Settings(BaseSettings):
    # Secrets & Config loaded STRICTLY from .env file
    DATABASE_URL: str
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_CHANNEL_ID: str
    TELEGRAM_BASE_URL: str = "https://tg-proxy.n75884292.workers.dev"
    
    ADMIN_EMAIL: str
    ADMIN_PASSWORD: str
    
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"
    
    GEMINI_API_KEY: str = ""

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @field_validator("DATABASE_URL")
    def assemble_db_connection(cls, v: str) -> str:
        if not v:
            return v
            
        # Normalize driver prefix for SQLAlchemy asyncpg
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+asyncpg://", 1)
        elif v.startswith("postgresql://") and not v.startswith("postgresql+asyncpg://"):
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)

        # For asyncpg, strip libpq-specific query params like sslmode and channel_binding to avoid asyncpg TypeError
        if "postgresql+asyncpg" in v and "?" in v:
            parsed = urlparse(v)
            # Reconstruct URL without query params (asyncpg handles ssl via connect_args)
            clean_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, '', parsed.fragment))
            return clean_url

        return v

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

settings = Settings()
