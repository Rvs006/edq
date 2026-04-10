"""Background task to clean up expired tokens and old audit logs."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, and_, or_

from app.models.database import async_session
from app.models.refresh_token import RefreshToken
from app.utils.datetime import utcnow_naive

logger = logging.getLogger("edq.token_cleanup")

_cleanup_task: asyncio.Task | None = None

CLEANUP_INTERVAL_SECONDS = 3600  # every hour


async def _cleanup_expired_tokens(session_factory=None) -> int:
    """Delete revoked tokens and tokens past their expiry. Returns count deleted.

    Args:
        session_factory: Optional async session factory for dependency injection (testing).
                         Falls back to the default ``async_session`` when *None*.
    """
    factory = session_factory or async_session
    async with factory() as db:
        now = utcnow_naive()
        result = await db.execute(
            delete(RefreshToken).where(
                or_(
                    RefreshToken.revoked.is_(True),
                    RefreshToken.expires_at < now,
                )
            )
        )
        await db.commit()
        return result.rowcount  # type: ignore[return-value]


async def _cleanup_old_audit_logs(session_factory=None) -> int:
    """Delete audit log entries older than AUDIT_LOG_RETENTION_DAYS. Returns count deleted."""
    from app.config import settings
    from app.models.audit_log import AuditLog

    retention_days = settings.AUDIT_LOG_RETENTION_DAYS
    if retention_days <= 0:
        return 0

    factory = session_factory or async_session
    async with factory() as db:
        cutoff = utcnow_naive() - timedelta(days=retention_days)
        result = await db.execute(
            delete(AuditLog).where(AuditLog.created_at < cutoff)
        )
        await db.commit()
        return result.rowcount  # type: ignore[return-value]


async def _cleanup_loop() -> None:
    """Main cleanup loop — runs hourly for tokens, daily for audit logs."""
    logger.info("Cleanup started (token interval=%ds)", CLEANUP_INTERVAL_SECONDS)
    audit_counter = 0
    while True:
        try:
            deleted = await _cleanup_expired_tokens()
            if deleted:
                logger.info("Cleaned up %d expired/revoked refresh tokens", deleted)
        except Exception:
            logger.exception("Error in token cleanup")

        # Run audit log cleanup once every 24 iterations (every 24 hours)
        audit_counter += 1
        if audit_counter >= 24:
            audit_counter = 0
            try:
                deleted = await _cleanup_old_audit_logs()
                if deleted:
                    logger.info("Cleaned up %d old audit log entries", deleted)
            except Exception:
                logger.exception("Error in audit log cleanup")

        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)


def start_token_cleanup() -> None:
    """Start the background token cleanup task."""
    global _cleanup_task
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = asyncio.create_task(_cleanup_loop())
        logger.info("Token cleanup task created")


def stop_token_cleanup() -> None:
    """Stop the background token cleanup task."""
    global _cleanup_task
    if _cleanup_task and not _cleanup_task.done():
        _cleanup_task.cancel()
        logger.info("Token cleanup task cancelled")
        _cleanup_task = None
