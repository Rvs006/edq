"""Branding settings model — custom report branding configuration."""

from sqlalchemy import Column, String, DateTime, Text
from datetime import datetime, timezone
import uuid

from app.models.database import Base
from app.utils.datetime import utcnow_naive


class BrandingSettings(Base):
    __tablename__ = "branding_settings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_name = Column(String(255), nullable=True, default="Electracom")
    logo_path = Column(String(512), nullable=True)
    primary_color = Column(String(7), nullable=True, default="#2563eb")
    footer_text = Column(Text, nullable=True, default="")
    created_at = Column(DateTime, nullable=False, default=utcnow_naive)
    updated_at = Column(DateTime, nullable=False, default=utcnow_naive, onupdate=utcnow_naive)
