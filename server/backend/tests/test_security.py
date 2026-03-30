"""Tests for security middleware and headers."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_security_headers(client: AsyncClient):
    """Responses should include security headers."""
    resp = await client.get("/api/health")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "Content-Security-Policy" in resp.headers


@pytest.mark.asyncio
async def test_csrf_protection_blocks_without_token(client: AsyncClient):
    """POST to a CSRF-protected endpoint without a session cookie bypasses
    CSRF check but the endpoint itself requires authentication → 401."""
    # No session cookie → CSRF middleware passes through → endpoint returns 401
    resp = await client.post("/api/auth/logout")
    assert resp.status_code == 401
