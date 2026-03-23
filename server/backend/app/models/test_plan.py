"""Test Plan model — custom test configurations with per-test toggles and tier overrides."""

from sqlalchemy import Column, String, DateTime, Text, JSON, ForeignKey
from datetime import datetime, timezone
import uuid

from app.models.database import Base


class TestPlan(Base):
    __tablename__ = "test_plans"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    base_template_id = Column(String(36), ForeignKey("test_templates.id"), nullable=True)
    test_configs = Column(JSON, nullable=False)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=True, onupdate=lambda: datetime.now(timezone.utc))
