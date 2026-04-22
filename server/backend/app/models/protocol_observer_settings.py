"""Protocol observer settings model."""

from sqlalchemy import Boolean, Column, DateTime, Integer, String, UniqueConstraint
import uuid

from app.models.database import Base
from app.utils.datetime import utcnow_naive


class ProtocolObserverSettings(Base):
    __tablename__ = "protocol_observer_settings"
    __table_args__ = (UniqueConstraint("singleton_key", name="uq_protocol_observer_settings_singleton"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    singleton_key = Column(String(1), nullable=False, default="_", unique=True)
    enabled = Column(Boolean, nullable=False, default=True)
    bind_host = Column(String(64), nullable=False, default="0.0.0.0")
    timeout_seconds = Column(Integer, nullable=False, default=20)
    dns_port = Column(Integer, nullable=False, default=53)
    ntp_port = Column(Integer, nullable=False, default=123)
    dhcp_port = Column(Integer, nullable=False, default=67)
    dhcp_offer_ip = Column(String(64), nullable=False, default="")
    dhcp_subnet_mask = Column(String(64), nullable=False, default="")
    dhcp_router_ip = Column(String(64), nullable=False, default="")
    dhcp_dns_server = Column(String(64), nullable=False, default="")
    dhcp_lease_seconds = Column(Integer, nullable=False, default=300)
    created_at = Column(DateTime, nullable=False, default=utcnow_naive)
    updated_at = Column(DateTime, nullable=False, default=utcnow_naive, onupdate=utcnow_naive)
