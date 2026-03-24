"""Audit Log model — compliance tracking."""

from sqlalchemy import Column, String, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from app.models.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    action = Column(String(64), nullable=False, index=True)  # e.g. "device.create", "test_run.start"
    resource_type = Column(String(64), nullable=False)  # e.g. "device", "test_run"
    resource_id = Column(String(36), nullable=True)
    details = Column(JSON, nullable=True)  # Action-specific data
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(512), nullable=True)
    compliance_refs = Column(JSON, nullable=True)  # ["ISO 27001 A.x.y", "SOC2 CCx.x"]
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="audit_logs")
