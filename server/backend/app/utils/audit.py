"""Audit logging helper for CRUD and security operations.

Writes audit events to BOTH the database AND a dedicated structured log stream.
The log stream (edq.audit) can be forwarded to syslog, ELK, Splunk, or any
log aggregator via standard Python logging handlers or Docker log drivers.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.user import User

logger = logging.getLogger("edq.audit")


def _extract_ip(request: Optional[Request]) -> Optional[str]:
    if not request:
        return None
    from app.middleware.rate_limit import get_client_ip
    return get_client_ip(request)


def _emit_audit_log(
    action: str,
    resource_type: str,
    *,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """Emit a structured audit log entry to the edq.audit logger.

    This produces a JSON line that can be ingested by any log aggregator
    (ELK, Splunk, CloudWatch, syslog) independently of the database.
    """
    record = {
        "event": "audit",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "user_id": user_id,
        "username": username,
        "ip_address": ip_address,
        "user_agent": user_agent,
    }
    if details:
        record["details"] = details
    logger.info(json.dumps(record, default=str))


async def log_action(
    db: AsyncSession,
    user: User,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: Optional[dict] = None,
    request: Optional[Request] = None,
) -> None:
    """Create an audit log entry for a CRUD operation (DB + log stream)."""
    ip = _extract_ip(request)
    username = user.username if hasattr(user, "username") else None

    entry = AuditLog(
        user_id=user.id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip,
    )
    db.add(entry)

    _emit_audit_log(
        action, resource_type,
        user_id=user.id, username=username,
        resource_id=resource_id, details=details,
        ip_address=ip,
    )


async def log_security_event(
    db: AsyncSession,
    action: str,
    *,
    user_id: Optional[str] = None,
    details: Optional[dict] = None,
    request: Optional[Request] = None,
) -> None:
    """Create an audit log entry for a security event (DB + log stream).

    Unlike log_action, this does not require a User ORM object — useful for
    failed logins where the user may not exist.
    """
    ip = _extract_ip(request)
    ua = request.headers.get("User-Agent", "")[:512] if request else None

    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type="auth",
        details=details,
        ip_address=ip,
        user_agent=ua,
    )
    db.add(entry)

    _emit_audit_log(
        action, "auth",
        user_id=user_id, details=details,
        ip_address=ip, user_agent=ua,
    )
