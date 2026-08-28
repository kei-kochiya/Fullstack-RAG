from database import Base
from sqlalchemy import Column, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.sql import func


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), unique=True, index=True, nullable=False)
    original_name = Column(String(255), nullable=True)
    status = Column(String(50), default="uploaded", index=True, nullable=False)
    file_size_bytes = Column(Integer, nullable=True)
    chunk_count = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)
    upload_time = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(128), index=True, nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True, nullable=False)
    latency = Column(Float, nullable=True)

    __table_args__ = (
        Index("idx_session_timestamp", "session_id", "timestamp"),
    )
