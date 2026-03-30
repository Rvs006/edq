"""User model — Test Engineers, Reviewers, Admins."""

from sqlalchemy import Column, String, DateTime, Boolean, Integer, Enum as SAEnum
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import enum
import uuid

from app.models.database import Base


class UserRole(str, enum.Enum):
    ENGINEER = "engineer"
    REVIEWER = "reviewer"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(320), unique=True, nullable=False, index=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    full_name = Column(String(128), nullable=True)
    role = Column(SAEnum(UserRole), nullable=False, default=UserRole.ENGINEER)
    is_active = Column(Boolean, default=True, nullable=False)
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime, nullable=True)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # TOTP Two-Factor Authentication
    totp_secret = Column(String(32), nullable=True)
    totp_provisional_secret = Column(String(32), nullable=True)

    # OIDC / SSO (set when user authenticates via external identity provider)
    oidc_provider = Column(String(64), nullable=True)   # e.g. "google", "microsoft", "keycloak"
    oidc_subject = Column(String(256), nullable=True)    # unique ID from the IdP
    oidc_email = Column(String(320), nullable=True)

    # Relationships
    test_runs = relationship("TestRun", back_populates="engineer", foreign_keys="TestRun.engineer_id")
    audit_logs = relationship("AuditLog", back_populates="user")
