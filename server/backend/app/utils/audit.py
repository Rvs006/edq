"""Audit logging helper for CRUD operations."""

import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Request

from app.models.audit_log import AuditLog
from app.models.user import User

logger = logging.getLogger("edq.audit")


async def log_action(
    db: AsyncSession,
    user: User,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: Optional[dict] = None,
    request: Optional[Request] = None,
) -> None:
    """Create an audit log entry for a CRUD operation."""
    ip_address = None
    if request:
        ip_address = request.headers.get(
            "X-Forwarded-For",
            request.client.host if request.client else None,
        )

    entry = AuditLog(
        user_id=user.id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
    )
    db.add(entry)
    logger.info(
        "Audit: user=%s action=%s resource=%s/%s",
        user.username if hasattr(user, "username") else user.id,
        action,
        resource_type,
        resource_id or "N/A",
    )
