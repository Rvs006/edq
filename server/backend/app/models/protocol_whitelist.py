"""Protocol Whitelist model — configurable allowed ports/services/versions."""

from sqlalchemy import Column, String, DateTime, Text, JSON, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from app.models.database import Base


class ProtocolWhitelist(Base):
    __tablename__ = "protocol_whitelists"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    is_default = Column(Boolean, default=False)
    entries = Column(JSON, nullable=False)  # [{port, protocol, service, required_version}]
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    profiles = relationship("DeviceProfile", back_populates="whitelist")
