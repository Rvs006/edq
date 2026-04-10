"""Device model — IP devices under test."""

from sqlalchemy import Column, String, DateTime, Text, JSON, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import enum
import uuid

from app.models.database import Base
from app.models.enum_utils import enum_values
from app.utils.datetime import utcnow_naive


class DeviceCategory(str, enum.Enum):
    CAMERA = "camera"
    CONTROLLER = "controller"
    INTERCOM = "intercom"
    ACCESS_PANEL = "access_panel"
    LIGHTING = "lighting"
    HVAC = "hvac"
    IOT_SENSOR = "iot_sensor"
    METER = "meter"
    UNKNOWN = "unknown"


class DeviceStatus(str, enum.Enum):
    DISCOVERED = "discovered"
    IDENTIFIED = "identified"
    TESTING = "testing"
    TESTED = "tested"
    QUALIFIED = "qualified"
    FAILED = "failed"


class AddressingMode(str, enum.Enum):
    STATIC = "static"
    DHCP = "dhcp"
    UNKNOWN = "unknown"


class Device(Base):
    __tablename__ = "devices"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ip_address = Column(String(45), nullable=True, index=True)
    mac_address = Column(String(17), nullable=True)
    addressing_mode = Column(
        SAEnum(AddressingMode, values_callable=enum_values),
        default=AddressingMode.STATIC,
    )
    hostname = Column(String(255), nullable=True)
    manufacturer = Column(String(128), nullable=True)
    model = Column(String(128), nullable=True)
    firmware_version = Column(String(64), nullable=True)
    serial_number = Column(String(128), nullable=True)
    location = Column(String(255), nullable=True)
    category = Column(
        SAEnum(DeviceCategory, values_callable=enum_values),
        default=DeviceCategory.UNKNOWN,
    )
    status = Column(
        SAEnum(DeviceStatus, values_callable=enum_values),
        default=DeviceStatus.DISCOVERED,
    )
    oui_vendor = Column(String(128), nullable=True)  # IEEE OUI lookup result
    os_fingerprint = Column(String(256), nullable=True)
    open_ports = Column(JSON, nullable=True)  # [{port, protocol, service, version}]
    discovery_data = Column(JSON, nullable=True)  # Full discovery fingerprint
    notes = Column(Text, nullable=True)
    profile_id = Column(String(36), ForeignKey("device_profiles.id"), nullable=True, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    discovered_by = Column(String(36), ForeignKey("agents.id"), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=utcnow_naive)
    updated_at = Column(DateTime, nullable=False, default=utcnow_naive, onupdate=utcnow_naive)

    # Relationships
    profile = relationship("DeviceProfile", back_populates="devices")
    test_runs = relationship("TestRun", back_populates="device")
    agent = relationship("Agent", back_populates="devices")
