"""Report Config model — template cell mappings for Excel/Word generation."""

from sqlalchemy import Column, String, DateTime, Text, JSON, Boolean, ForeignKey
from datetime import datetime, timezone
import uuid

from app.models.database import Base


class ReportConfig(Base):
    __tablename__ = "report_configs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    client_name = Column(String(256), nullable=True)
    logo_path = Column(String(512), nullable=True)
    template_file = Column(String(512), nullable=True)  # Path to Excel/Word template
    template_url = Column(String(1024), nullable=True)  # S3 URL
    report_type = Column(String(16), nullable=False, default="excel")  # excel, word, pdf
    cell_mappings = Column(JSON, nullable=True)  # Sheet → row/col → test_id mapping
    branding = Column(JSON, nullable=True)  # {logo_url, company_name, colors}
    compliance_standards = Column(JSON, nullable=True)  # ["ISO 27001", "Cyber Essentials", ...]
    branding_colours = Column(JSON, nullable=True)  # {"primary": "#1F4E79", "accent": "#f59e0b"}
    is_active = Column(Boolean, default=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
