"""Network Scan model — subnet-wide device discovery and batch testing."""

from sqlalchemy import Column, String, DateTime, JSON, ForeignKey, Enum as SAEnum
from datetime import datetime, timezone
import enum
import uuid

from app.models.database import Base
from app.models.enum_utils import enum_values
from app.utils.datetime import utcnow_naive


class NetworkScanStatus(str, enum.Enum):
    PENDING = "pending"
    DISCOVERING = "discovering"
    SCANNING = "scanning"
    COMPLETE = "complete"
    ERROR = "error"


class NetworkScan(Base):
    __tablename__ = "network_scans"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    cidr = Column(String(43), nullable=False)
    connection_scenario = Column(String(32), default="test_lab")
    selected_test_ids = Column(JSON, nullable=True)
    status = Column(
        SAEnum(NetworkScanStatus, values_callable=enum_values),
        default=NetworkScanStatus.PENDING,
    )
    devices_found = Column(JSON, nullable=True)
    run_ids = Column(JSON, nullable=True)
    error_message = Column(String(512), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow_naive)
    completed_at = Column(DateTime, nullable=True)
