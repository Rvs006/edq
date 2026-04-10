"""Refresh token model — single-use tokens with DB-backed revocation."""

from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean, Index
from datetime import datetime, timezone
import uuid

from app.models.database import Base
from app.utils.datetime import utcnow_naive


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow_naive)

    __table_args__ = (
        Index("ix_refresh_tokens_user_revoked", "user_id", "revoked"),
    )
