"""Sync Queue model — offline sync queue for agent data."""

from sqlalchemy import Column, String, DateTime, Text, JSON, Integer
from datetime import datetime, timezone
import uuid

from app.models.database import Base


class SyncQueue(Base):
    __tablename__ = "sync_queue"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(String(36), nullable=False, index=True)
    operation = Column(String(32), nullable=False)  # create, update, delete
    resource_type = Column(String(64), nullable=False)
    resource_id = Column(String(36), nullable=False)
    payload = Column(JSON, nullable=False)
    priority = Column(Integer, default=0)
    status = Column(String(16), default="pending")  # pending, processing, completed, failed
    retry_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    processed_at = Column(DateTime, nullable=True)
