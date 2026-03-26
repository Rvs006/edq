"""Background task to clean up expired and revoked refresh tokens."""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, and_, or_

from app.models.database import async_session
from app.models.refresh_token import RefreshToken

logger = logging.getLogger("edq.token_cleanup")

_cleanup_task: asyncio.Task | None = None

CLEANUP_INTERVAL_SECONDS = 3600  # every hour


async def _cleanup_expired_tokens() -> int:
    """Delete revoked tokens and tokens past their expiry. Returns count deleted."""
    async with async_session() as db:
        now = datetime.now(timezone.utc)
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


async def _cleanup_loop() -> None:
    """Main cleanup loop — runs hourly."""
    logger.info("Refresh token cleanup started (interval=%ds)", CLEANUP_INTERVAL_SECONDS)
    while True:
        try:
            deleted = await _cleanup_expired_tokens()
            if deleted:
                logger.info("Cleaned up %d expired/revoked refresh tokens", deleted)
        except Exception:
            logger.exception("Error in token cleanup loop")
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
