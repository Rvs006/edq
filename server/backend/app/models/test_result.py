"""Test Result model — per-test verdicts with findings."""

from sqlalchemy import Column, String, DateTime, Text, JSON, ForeignKey, Enum as SAEnum, Float
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import enum
import uuid

from app.models.database import Base


class TestVerdict(str, enum.Enum):
    PASS = "pass"
    FAIL = "fail"
    ADVISORY = "advisory"
    INFO = "info"
    NA = "na"
    ERROR = "error"
    PENDING = "pending"
    RUNNING = "running"
    SKIPPED_SAFE_MODE = "skipped_safe_mode"


class TestTier(str, enum.Enum):
    AUTOMATIC = "automatic"
    GUIDED_MANUAL = "guided_manual"
    NESSUS_IMPORT = "nessus_import"


class TestResult(Base):
    __tablename__ = "test_results"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    test_run_id = Column(String(36), ForeignKey("test_runs.id"), nullable=False, index=True)
    test_id = Column(String(8), nullable=False, index=True)  # e.g. "U01", "U02"
    test_name = Column(String(128), nullable=False)
    tier = Column(SAEnum(TestTier), nullable=False)
    tool = Column(String(64), nullable=True)  # nmap, sslyze, ssh-audit, etc.
    verdict = Column(SAEnum(TestVerdict), default=TestVerdict.PENDING)
    is_essential = Column(String(3), default="no")  # "yes" or "no"
    comment = Column(Text, nullable=True)  # Auto-generated or manual comment
    comment_override = Column(Text, nullable=True)  # Engineer override
    engineer_notes = Column(Text, nullable=True)  # Free-text notes from engineer
    raw_output = Column(Text, nullable=True)  # Raw tool output
    parsed_data = Column(JSON, nullable=True)  # Structured parsed results
    findings = Column(JSON, nullable=True)  # Detailed findings array
    override_reason = Column(Text, nullable=True)
    # Stored as String (not SAEnum) because the override endpoint writes
    # verdict.value (a string) here — see test_results.py override_result().
    override_verdict = Column(String(32), nullable=True)
    overridden_by_user_id = Column(String(36), nullable=True)
    overridden_by_username = Column(String(64), nullable=True)
    overridden_at = Column(DateTime, nullable=True)
    evidence_files = Column(JSON, nullable=True)  # Attachment IDs
    compliance_map = Column(JSON, nullable=True)  # ["ISO 27001 A.x.y", "SOC2 CCx.x"]
    duration_seconds = Column(Float, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    test_run = relationship("TestRun", back_populates="results")

    @property
    def is_overridden(self) -> bool:
        return bool(self.overridden_at or self.override_reason or self.override_verdict)
