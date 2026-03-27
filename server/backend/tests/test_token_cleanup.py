"""Tests for the refresh token cleanup service."""

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
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
async def test_cleanup_deletes_expired_and_revoked(db_engine):
    """Expired and revoked tokens should be cleaned up; valid ones should remain."""
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        # Create a valid (not expired, not revoked) token
        await _insert_token(db, token_val="valid", expires_delta=timedelta(days=1))
        # Create an expired token
        await _insert_token(db, token_val="expired", expires_delta=timedelta(hours=-1))
        # Create a revoked token
        await _insert_token(db, token_val="revoked", revoked=True)
        await db.commit()

    # Run cleanup with the test session factory injected
    from app.services.token_cleanup import _cleanup_expired_tokens
    deleted = await _cleanup_expired_tokens(session_factory=session_factory)

    assert deleted >= 2

    # Verify the valid token still exists
    async with session_factory() as db:
        result = await db.execute(
            select(func.count(RefreshToken.id)).where(RefreshToken.token_hash == _hash("valid"))
        )
        assert result.scalar() == 1


@pytest.mark.asyncio
async def test_cleanup_noop_when_no_stale_tokens(db_engine):
    """Cleanup should return 0 when there are no expired or revoked tokens."""
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        await _insert_token(db, token_val="fresh", expires_delta=timedelta(days=7))
        await db.commit()

    from app.services.token_cleanup import _cleanup_expired_tokens
    deleted = await _cleanup_expired_tokens(session_factory=session_factory)
    assert deleted == 0
