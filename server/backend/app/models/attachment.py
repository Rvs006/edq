"""Attachment model — evidence files, Nessus imports, screenshots."""

from sqlalchemy import Column, String, DateTime, Integer, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from app.models.database import Base


class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    test_run_id = Column(String(36), ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    test_result_id = Column(String(36), ForeignKey("test_results.id", ondelete="CASCADE"), nullable=True)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    file_url = Column(String(1024), nullable=True)  # S3 URL if uploaded
    mime_type = Column(String(128), nullable=False)
    file_size = Column(Integer, nullable=False)
    category = Column(String(32), default="evidence")  # evidence, nessus_import, screenshot, report
    uploaded_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    test_run = relationship("TestRun", back_populates="attachments")
