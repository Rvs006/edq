"""Test Run model — individual test execution records."""

from sqlalchemy import Column, String, DateTime, Text, JSON, Integer, ForeignKey, Enum as SAEnum, Float
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import enum
import uuid

from app.models.database import Base


class TestRunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    AWAITING_MANUAL = "awaiting_manual"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TestRunVerdict(str, enum.Enum):
    PASS = "pass"
    FAIL = "fail"
    ADVISORY = "advisory"
    INCOMPLETE = "incomplete"


class TestRun(Base):
    __tablename__ = "test_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id = Column(String(36), ForeignKey("devices.id"), nullable=False, index=True)
    template_id = Column(String(36), ForeignKey("test_templates.id"), nullable=False)
    engineer_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    agent_id = Column(String(36), ForeignKey("agents.id"), nullable=True)
    status = Column(SAEnum(TestRunStatus), default=TestRunStatus.PENDING)
    overall_verdict = Column(SAEnum(TestRunVerdict), nullable=True)
    progress_pct = Column(Float, default=0.0)
    total_tests = Column(Integer, default=0)
    completed_tests = Column(Integer, default=0)
    passed_tests = Column(Integer, default=0)
    failed_tests = Column(Integer, default=0)
    advisory_tests = Column(Integer, default=0)
    na_tests = Column(Integer, default=0)
    synopsis = Column(Text, nullable=True)  # AI-generated or manual narrative
    synopsis_status = Column(String(32), default="empty")  # empty, ai_draft, human_approved
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    run_metadata = Column("metadata", JSON, nullable=True)  # Scan configuration, agent info, etc.
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    device = relationship("Device", back_populates="test_runs")
    template = relationship("TestTemplate", back_populates="test_runs")
    engineer = relationship("User", back_populates="test_runs", foreign_keys=[engineer_id])
    agent = relationship("Agent", back_populates="test_runs")
    results = relationship("TestResult", back_populates="test_run", cascade="all, delete-orphan")
    attachments = relationship("Attachment", back_populates="test_run")
