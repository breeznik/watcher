import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Enum
from sqlalchemy.orm import relationship
from app.database import Base


class StatusEnum(str, enum.Enum):
    unknown = "unknown"
    found = "found"
    not_found = "not_found"
    error = "error"
    heavy = "heavy"


class Watcher(Base):
    __tablename__ = "watchers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    url = Column(String(500), nullable=False)
    phrase = Column(String(255), nullable=False)
    interval_minutes = Column(Integer, nullable=False, default=5)
    emails = Column(Text, nullable=False)
    enabled = Column(Boolean, default=True)
    last_check_at = Column(DateTime, nullable=True)
    last_status = Column(Enum(StatusEnum), default=StatusEnum.unknown)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    logs = relationship("CheckLog", back_populates="watcher", cascade="all, delete-orphan")


class CheckLog(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, index=True)
    watcher_id = Column(Integer, ForeignKey("watchers.id", ondelete="CASCADE"), nullable=False)
    checked_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    status = Column(Enum(StatusEnum), nullable=False)
    error_message = Column(Text, nullable=True)
    email_sent = Column(Boolean, default=False, nullable=False)
    email_error = Column(Text, nullable=True)

    watcher = relationship("Watcher", back_populates="logs")