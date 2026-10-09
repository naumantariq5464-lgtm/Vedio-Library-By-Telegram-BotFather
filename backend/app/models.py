from sqlalchemy import Column, Integer, String, BigInteger, DateTime, func
from app.database import Base

class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    telegram_file_id = Column(String(512), nullable=False)
    telegram_message_id = Column(BigInteger, nullable=False)
    channel_id = Column(String(100), nullable=False)
    file_size = Column(BigInteger, default=0, nullable=False)
    duration = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "telegram_file_id": self.telegram_file_id,
            "telegram_message_id": self.telegram_message_id,
            "channel_id": self.channel_id,
            "file_size": self.file_size,
            "duration": self.duration,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
