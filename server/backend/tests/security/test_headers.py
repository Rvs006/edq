"""Tests for HTTP security headers."""

import pytest
from httpx import AsyncClient

from app.config import settings


@pytest.mark.asyncio
async def test_hsts_header(client: AsyncClient):
    """The backend should only emit HSTS when secure-cookie mode is enabled."""
    resp = await client.get("/api/health")
    hsts = resp.headers.get("strict-transport-security")

    if settings.COOKIE_SECURE:
        assert hsts is not None, (
            "Strict-Transport-Security header is missing from the response. "
            "Expected HSTS header when secure-cookie mode is enabled."
        )
        assert "max-age=" in hsts, (
            f"HSTS header present but malformed: {hsts!r}. "
            "Expected 'max-age=' directive."
        )
    else:
        assert hsts is None
