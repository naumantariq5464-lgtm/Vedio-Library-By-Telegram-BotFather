from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings
import logging

logger = logging.getLogger("uvicorn.error")

db_url = settings.DATABASE_URL

# Configure engine kwargs according to DB dialect (Neon PostgreSQL vs SQLite fallback)
engine_kwargs = {"echo": False}

if db_url.startswith("postgresql+asyncpg"):
    # Neon Cloud PostgreSQL requires SSL mode
    engine_kwargs["connect_args"] = {
        "ssl": "require"
    }
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20
elif db_url.startswith("sqlite+aiosqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_async_engine(db_url, **engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def init_db():
    import app.models  # Ensures Video model is registered on Base.metadata
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized successfully.")
