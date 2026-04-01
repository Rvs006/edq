"""Test Run model — individual test execution records."""

from sqlalchemy import Column, String, DateTime, Text, JSON, Integer, ForeignKey, Enum as SAEnum, Float
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import enum
import uuid

from app.models.database import Base


class TestRunStatus(str, enum.Enum):
    PENDING = "pending"
    SELECTING_INTERFACE = "selecting_interface"
    SYNCING = "syncing"
    RUNNING = "running"
    PAUSED_MANUAL = "paused_manual"
    PAUSED_CABLE = "paused_cable"
    AWAITING_MANUAL = "awaiting_manual"
    AWAITING_REVIEW = "awaiting_review"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"  # Legacy alias retained for safe reads during migration


LEGACY_TEST_RUN_STATUS_ALIASES = {
    TestRunStatus.PAUSED.value: TestRunStatus.PAUSED_MANUAL.value,
    "complete": TestRunStatus.COMPLETED.value,
    "error": TestRunStatus.FAILED.value,
}

CANONICAL_TEST_RUN_STATUSES = (
    TestRunStatus.PENDING.value,
    TestRunStatus.SELECTING_INTERFACE.value,
    TestRunStatus.SYNCING.value,
    TestRunStatus.RUNNING.value,
    TestRunStatus.PAUSED_MANUAL.value,
    TestRunStatus.PAUSED_CABLE.value,
    TestRunStatus.AWAITING_MANUAL.value,
    TestRunStatus.AWAITING_REVIEW.value,
    TestRunStatus.COMPLETED.value,
    TestRunStatus.FAILED.value,
    TestRunStatus.CANCELLED.value,
)


def normalize_test_run_status(status: "TestRunStatus | str | None") -> str:
    """Return the canonical public-facing status string for a run."""
    if status is None:
        return TestRunStatus.PENDING.value
    raw = status.value if isinstance(status, TestRunStatus) else str(status)
    return LEGACY_TEST_RUN_STATUS_ALIASES.get(raw, raw)


def is_paused_test_run_status(status: "TestRunStatus | str | None") -> bool:
    """Return True when a run is paused for any supported reason."""
    return normalize_test_run_status(status) in {
        TestRunStatus.PAUSED_MANUAL.value,
        TestRunStatus.PAUSED_CABLE.value,
    }


class TestRunVerdict(str, enum.Enum):
    PASS = "pass"
    QUALIFIED_PASS = "qualified_pass"
    FAIL = "fail"
    INCOMPLETE = "incomplete"


class TestRun(Base):
    __tablename__ = "test_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id = Column(String(36), ForeignKey("devices.id"), nullable=False, index=True)
    template_id = Column(String(36), ForeignKey("test_templates.id"), nullable=False)
    engineer_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    agent_id = Column(String(36), ForeignKey("agents.id"), nullable=True)
    connection_scenario = Column(String(32), nullable=False, default="direct")  # direct, test_lab, site_network
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
