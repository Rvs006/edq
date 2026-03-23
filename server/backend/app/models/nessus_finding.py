"""NessusFinding model — parsed Nessus vulnerability scan results."""

from sqlalchemy import Column, String, DateTime, Text, JSON, Integer, Float, ForeignKey
from datetime import datetime, timezone
import uuid

from app.models.database import Base


class NessusFinding(Base):
    __tablename__ = "nessus_findings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String(36), ForeignKey("test_runs.id"), nullable=False, index=True)
    plugin_id = Column(Integer, nullable=False)
    plugin_name = Column(String(256), nullable=False)
    severity = Column(String(16), nullable=False)
    risk_factor = Column(String(32), nullable=True)
    description = Column(Text, nullable=True)
    solution = Column(Text, nullable=True)
    port = Column(Integer, nullable=True)
    protocol = Column(String(8), nullable=True)
    plugin_output = Column(Text, nullable=True)
    cvss_score = Column(Float, nullable=True)
    cve_ids = Column(JSON, nullable=True)
    imported_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
