"""UTC datetime helpers for DB-safe and API-safe timestamps."""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def utcnow_naive() -> datetime:
    """Return a naive UTC timestamp for TIMESTAMP WITHOUT TIME ZONE columns."""
    return utcnow().replace(tzinfo=None)


def ensure_utc_naive(value: datetime | None) -> datetime | None:
    """Normalize a datetime to naive UTC for database storage."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def as_utc(value: datetime | None) -> datetime | None:
    """Normalize naive or aware datetimes into an aware UTC datetime."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
