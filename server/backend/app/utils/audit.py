"""Audit logging helper for CRUD and security operations."""

import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Request

from app.models.audit_log import AuditLog
from app.models.user import User

logger = logging.getLogger("edq.audit")


def _extract_ip(request: Optional[Request]) -> Optional[str]:
    if not request:
        return None
    return request.headers.get(
        "X-Forwarded-For",
        request.client.host if request.client else None,
    )


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
    entry = AuditLog(
        user_id=user.id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=_extract_ip(request),
    )
    db.add(entry)
    logger.info(
        "Audit: user=%s action=%s resource=%s/%s",
        user.username if hasattr(user, "username") else user.id,
        action,
        resource_type,
        resource_id or "N/A",
    )


async def log_security_event(
    db: AsyncSession,
    action: str,
    *,
    user_id: Optional[str] = None,
    details: Optional[dict] = None,
    request: Optional[Request] = None,
) -> None:
    """Create an audit log entry for a security event (login, logout, etc.).

    Unlike log_action, this does not require a User ORM object — useful for
    failed logins where the user may not exist.
    """
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type="auth",
        details=details,
        ip_address=_extract_ip(request),
        user_agent=request.headers.get("User-Agent", "")[:512] if request else None,
    )
    db.add(entry)
    logger.info("Security: action=%s user=%s", action, user_id or "anonymous")
