"""Device Profile model — manufacturer/model templates with safe-mode policies."""

from sqlalchemy import Column, String, DateTime, Text, JSON, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from app.models.database import Base


class DeviceProfile(Base):
    __tablename__ = "device_profiles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(128), nullable=False, unique=True)
    manufacturer = Column(String(128), nullable=False, index=True)
    model_pattern = Column(String(128), nullable=True)  # Glob pattern e.g. "FW-*"
    category = Column(String(32), nullable=False, default="unknown")
    description = Column(Text, nullable=True)
    default_whitelist_id = Column(String(36), ForeignKey("protocol_whitelists.id"), nullable=True)
    additional_tests = Column(JSON, nullable=True)  # Extra test IDs for this device type
    safe_mode = Column(JSON, nullable=True)  # {max_scan_rate, skip_aggressive_scripts, parallel_probes}
    fingerprint_rules = Column(JSON, nullable=True)  # Rules for auto-matching devices
    auto_generated = Column(Boolean, default=False)  # True if created by auto-learn
    is_active = Column(Boolean, default=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    devices = relationship("Device", back_populates="profile")
    whitelist = relationship("ProtocolWhitelist", back_populates="profiles")
