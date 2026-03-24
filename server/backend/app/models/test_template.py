"""Test Template model — reusable test suites with protocol whitelists."""

from sqlalchemy import Column, String, DateTime, Text, JSON, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from app.models.database import Base


class TestTemplate(Base):
    __tablename__ = "test_templates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    version = Column(String(16), default="1.0")
    test_ids = Column(JSON, nullable=False)  # Array of test IDs to include e.g. ["U01","U02",...]
    whitelist_id = Column(String(36), ForeignKey("protocol_whitelists.id"), nullable=True)
    cell_mappings = Column(JSON, nullable=True)  # Excel cell mapping configuration
    report_config = Column(JSON, nullable=True)  # Report generation settings
    branding = Column(JSON, nullable=True)  # Logo, company name, colors
    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    whitelist = relationship("ProtocolWhitelist")
    test_runs = relationship("TestRun", back_populates="template")
