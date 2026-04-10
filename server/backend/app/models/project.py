"""Project model — organizational folders for grouping devices and test runs."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, Boolean, ForeignKey, Integer
from app.models.database import Base
from app.utils.datetime import utcnow_naive


class Project(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), default="active")  # active, archived, completed
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    client_name = Column(String(255), nullable=True)
    location = Column(String(255), nullable=True)
    device_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow_naive)
    updated_at = Column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)
    is_archived = Column(Boolean, default=False)
