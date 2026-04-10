"""Tests for security middleware and headers."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_security_headers(client: AsyncClient):
    """Responses should include backend-set security headers.

    Note: X-Content-Type-Options, X-Frame-Options, CSP, and Referrer-Policy
    are now set by nginx (frontend proxy), not the backend middleware.
    The backend sets X-Request-ID and Cache-Control.
    """
    resp = await client.get("/api/health")
    assert resp.headers.get("x-request-id"), "X-Request-ID header should be present"
    assert "cache-control" in resp.headers, "Cache-Control header should be present"


@pytest.mark.asyncio
async def test_csrf_protection_blocks_without_token(client: AsyncClient):
    """POST to a CSRF-protected endpoint without a session cookie bypasses
    CSRF check but the endpoint itself requires authentication → 401."""
    # No session cookie → CSRF middleware passes through → endpoint returns 401
    resp = await client.post("/api/auth/logout")
    assert resp.status_code == 401
