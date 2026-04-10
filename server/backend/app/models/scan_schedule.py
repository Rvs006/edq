"""Scan Schedule model — recurring device re-scan definitions."""

from sqlalchemy import Column, String, DateTime, Integer, Boolean, ForeignKey, JSON, Enum as SAEnum
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import enum
import uuid

from app.models.database import Base
from app.models.enum_utils import enum_values
from app.utils.datetime import utcnow_naive


class ScheduleFrequency(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class ScanSchedule(Base):
    __tablename__ = "scan_schedules"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id = Column(String(36), ForeignKey("devices.id"), nullable=False, index=True)
    template_id = Column(String(36), ForeignKey("test_templates.id"), nullable=False)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    frequency = Column(
        SAEnum(ScheduleFrequency, values_callable=enum_values),
        nullable=False,
    )
    is_active = Column(Boolean, default=True, nullable=False)
    last_run_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=False)
    run_count = Column(Integer, default=0, nullable=False)
    max_runs = Column(Integer, nullable=True)  # None = unlimited
    diff_summary = Column(JSON, nullable=True)  # Last diff between consecutive scans
    created_at = Column(DateTime, nullable=False, default=utcnow_naive)
    updated_at = Column(DateTime, nullable=False, default=utcnow_naive, onupdate=utcnow_naive)

    # Relationships
    device = relationship("Device", backref="scan_schedules")
    template = relationship("TestTemplate")
    creator = relationship("User")
