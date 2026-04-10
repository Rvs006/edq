"""Authorized Network model — admin-managed scan scope for network scanning."""

from sqlalchemy import Column, String, DateTime, Boolean, Text
from datetime import datetime, timezone
import uuid

from app.models.database import Base
from app.utils.datetime import utcnow_naive


class AuthorizedNetwork(Base):
    __tablename__ = "authorized_networks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    cidr = Column(String(43), nullable=False, unique=True, index=True)
    label = Column(String(128), nullable=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(String(36), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow_naive)
    updated_at = Column(DateTime, nullable=False, default=utcnow_naive, onupdate=utcnow_naive)
