"""Tests for the refresh token cleanup service."""

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.refresh_token import RefreshToken


def _hash(val: str) -> str:
    return hashlib.sha256(val.encode()).hexdigest()


async def _insert_token(
    db: AsyncSession,
    *,
    token_val: str,
    user_id: str = "test-user-id",
    revoked: bool = False,
    expires_delta: timedelta | None = None,
) -> RefreshToken:
    expires_at = datetime.now(timezone.utc) + (expires_delta or timedelta(days=30))
    token = RefreshToken(
        token_hash=_hash(token_val),
        user_id=user_id,
        revoked=revoked,
        expires_at=expires_at,
    )
    db.add(token)
    await db.flush()
    return token


@pytest.mark.asyncio
async def test_cleanup_deletes_expired_and_revoked(db_session: AsyncSession):
    """Expired and revoked tokens should be cleaned up; valid ones should remain."""
    # Create a valid (not expired, not revoked) token
    await _insert_token(db_session, token_val="valid", expires_delta=timedelta(days=1))
    # Create an expired token
    await _insert_token(db_session, token_val="expired", expires_delta=timedelta(hours=-1))
    # Create a revoked token
    await _insert_token(db_session, token_val="revoked", revoked=True)
    await db_session.commit()

    # Run cleanup directly (import here to avoid circular import issues)
    from app.services.token_cleanup import _cleanup_expired_tokens
    deleted = await _cleanup_expired_tokens()

    assert deleted >= 2

    # Verify the valid token still exists
    result = await db_session.execute(
        select(func.count(RefreshToken.id)).where(RefreshToken.token_hash == _hash("valid"))
    )
    assert result.scalar() == 1


@pytest.mark.asyncio
async def test_cleanup_noop_when_no_stale_tokens(db_session: AsyncSession):
    """Cleanup should return 0 when there are no expired or revoked tokens."""
    await _insert_token(db_session, token_val="fresh", expires_delta=timedelta(days=7))
    await db_session.commit()

    from app.services.token_cleanup import _cleanup_expired_tokens
    deleted = await _cleanup_expired_tokens()
    assert deleted == 0
