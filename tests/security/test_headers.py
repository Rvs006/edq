"""Security header tests — verify response headers follow best practices."""

import httpx
import pytest

from live_helpers import BASE_URL, ADMIN_USER, ADMIN_PASS

pytestmark = [pytest.mark.asyncio, pytest.mark.security]


# ---------------------------------------------------------------------------
# 1. X-Content-Type-Options
# ---------------------------------------------------------------------------

async def test_x_content_type_options(client: httpx.AsyncClient):
    """API responses should include X-Content-Type-Options: nosniff."""
    resp = await client.get("/api/health")
    header = resp.headers.get("x-content-type-options", "")
    assert header.lower() == "nosniff", (
        f"Expected X-Content-Type-Options: nosniff, got '{header}'"
    )


# ---------------------------------------------------------------------------
# 2. X-Frame-Options
# ---------------------------------------------------------------------------

async def test_x_frame_options(client: httpx.AsyncClient):
    """Responses should include X-Frame-Options to prevent clickjacking."""
    resp = await client.get("/api/health")
    header = resp.headers.get("x-frame-options", "")
    assert header.upper() in ("DENY", "SAMEORIGIN"), (
        f"Expected X-Frame-Options DENY or SAMEORIGIN, got '{header}'"
    )


# ---------------------------------------------------------------------------
# 3. Content-Security-Policy
# ---------------------------------------------------------------------------

async def test_csp_header(client: httpx.AsyncClient):
    """Frontend responses should include a Content-Security-Policy header."""
    # Check the root URL (served by nginx/SPA)
    resp = await client.get("/")
    header = resp.headers.get("content-security-policy", "")
    if not header:
        # Also check API health as fallback
        resp2 = await client.get("/api/health")
        header = resp2.headers.get("content-security-policy", "")
    assert header, "Content-Security-Policy header not found on any response"


# ---------------------------------------------------------------------------
# 4. Referrer-Policy
# ---------------------------------------------------------------------------

async def test_referrer_policy(client: httpx.AsyncClient):
    """Responses should include a Referrer-Policy header."""
    resp = await client.get("/api/health")
    header = resp.headers.get("referrer-policy", "")
    if not header:
        resp2 = await client.get("/")
        header = resp2.headers.get("referrer-policy", "")
    assert header, "Referrer-Policy header not found on any response"


# ---------------------------------------------------------------------------
# 5. X-Request-ID
# ---------------------------------------------------------------------------

async def test_x_request_id(client: httpx.AsyncClient):
    """API responses should include a unique X-Request-ID for tracing."""
    resp = await client.get("/api/health")
    request_id = resp.headers.get("x-request-id", "")
    assert request_id, "X-Request-ID header not found on API response"

    # Second request should produce a different ID
    resp2 = await client.get("/api/health")
    request_id2 = resp2.headers.get("x-request-id", "")
    assert request_id2, "X-Request-ID missing on second request"
    assert request_id != request_id2, "X-Request-ID should be unique per request"


# ---------------------------------------------------------------------------
# 6. Cache-Control on mutations
# ---------------------------------------------------------------------------

async def test_cache_control_mutations(client: httpx.AsyncClient):
    """POST responses should include Cache-Control to prevent caching."""
    resp = await client.post(
        "/api/auth/login",
        json={"username": "nonexistent", "password": "x"},
    )
    cache_control = resp.headers.get("cache-control", "")
    assert cache_control, "Cache-Control header not found on POST response"
    # Should contain no-store or no-cache
    lower_cc = cache_control.lower()
    assert "no-store" in lower_cc or "no-cache" in lower_cc, (
        f"Expected no-store/no-cache in Cache-Control, got '{cache_control}'"
    )


# ---------------------------------------------------------------------------
# 7. HSTS header
# ---------------------------------------------------------------------------

async def test_hsts_header(client: httpx.AsyncClient):
    """Strict-Transport-Security should be present (may not be set in dev)."""
    resp = await client.get("/api/health")
    hsts = resp.headers.get("strict-transport-security", "")
    if not hsts:
        # Also try root
        resp2 = await client.get("/")
        hsts = resp2.headers.get("strict-transport-security", "")
    if not hsts:
        assert BASE_URL.startswith("http://"), "HSTS header unexpectedly missing on non-HTTP base URL"
        return
    assert "max-age" in hsts.lower(), (
        f"HSTS header missing max-age directive: '{hsts}'"
    )
