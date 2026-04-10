"""Agent model — registered test agents with credentials."""

from sqlalchemy import Column, String, DateTime, JSON, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from app.models.database import Base
from app.utils.datetime import utcnow_naive


class Agent(Base):
    __tablename__ = "agents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(128), nullable=False)
    hostname = Column(String(255), nullable=True)
    api_key_hash = Column(String(256), nullable=False)
    api_key_prefix = Column(String(8), nullable=False)  # First 8 chars for identification
    platform = Column(String(32), nullable=True)  # windows, macos, linux
    agent_version = Column(String(32), nullable=True)
    ip_address = Column(String(45), nullable=True)
    status = Column(String(32), default="offline")  # online, offline, busy, error
    last_heartbeat = Column(DateTime, nullable=True)
    capabilities = Column(JSON, nullable=True)  # {nmap, sslyze, testssl, ssh_audit, nikto, hydra}
    current_task = Column(String(36), nullable=True)  # Current test_run_id
    is_active = Column(Boolean, default=True)
    registered_by = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=utcnow_naive)
    updated_at = Column(DateTime, nullable=False, default=utcnow_naive, onupdate=utcnow_naive)

    # Relationships
    devices = relationship("Device", back_populates="agent")
    test_runs = relationship("TestRun", back_populates="agent")
