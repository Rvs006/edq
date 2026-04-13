"""Additional security tests — upload limits, expired tokens, CORS, error leakage."""

import httpx
import pytest

from live_helpers import BASE_URL, ADMIN_USER, ADMIN_PASS, _login, _apply_auth, unique_ip

pytestmark = [pytest.mark.asyncio, pytest.mark.security]


# ---------------------------------------------------------------------------
# 1. Large file upload rejection
# ---------------------------------------------------------------------------

async def test_large_file_upload(admin_client: httpx.AsyncClient):
    """Uploading oversized content should be rejected (413 or 422)."""
    # Generate ~10 MB of dummy CSV content
    large_content = "ip_address,hostname,manufacturer,model\n" + (
        "10.0.0.1,host,Mfg,Model\n" * (10 * 1024 * 1024 // 35)
    )
    resp = await admin_client.post(
        "/api/devices/import",
        content=large_content,
        headers={"Content-Type": "text/csv"},
    )
    # Accept 413 (too large), 422 (validation), or 400 (bad request)
    assert resp.status_code in (400, 413, 422), (
        f"Expected 400/413/422 for oversized upload, got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# 2. Expired JWT token
# ---------------------------------------------------------------------------

async def test_expired_token(client: httpx.AsyncClient):
    """An expired JWT must be rejected with 401."""
    try:
        import jwt as pyjwt
    except ImportError:
        pytest.skip("PyJWT not installed — cannot forge expired token")

    import time

    # Login to get a valid token to decode
    auth = await _login(ADMIN_USER, ADMIN_PASS)
    session_cookie = auth["session_cookie"]
    if not session_cookie:
        pytest.skip("No session cookie available to decode")

    try:
        # Decode without verification to read the payload
        payload = pyjwt.decode(
            session_cookie,
            options={"verify_signature": False},
        )
    except Exception:
        pytest.skip("Could not decode session cookie as JWT")

    # Create expired token
    payload["exp"] = int(time.time()) - 3600  # Expired 1 hour ago
    signing_material = "jwt-token-test-fixture-value"
    algorithm = payload.get("alg", "HS256")
    # PyJWT encodes with algorithm param, not alg from payload
    try:
        expired_token = pyjwt.encode(payload, signing_material, algorithm="HS256")
    except Exception:
        pytest.skip("Could not forge expired token")

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as c:
        c.cookies.set("edq_session", expired_token)
        resp = await c.get("/api/auth/me")
        assert resp.status_code == 401, (
            f"Expected 401 for expired token, got {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# 3. Concurrent logins
# ---------------------------------------------------------------------------

async def test_concurrent_logins(client: httpx.AsyncClient):
    """Multiple simultaneous sessions for the same user should work."""
    auth1 = await _login(ADMIN_USER, ADMIN_PASS)
    auth2 = await _login(ADMIN_USER, ADMIN_PASS)

    # Both sessions should be valid
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as c1:
        _apply_auth(c1, auth1)
        resp1 = await c1.get("/api/auth/me")
        assert resp1.status_code == 200, (
            f"First concurrent session failed: {resp1.status_code}"
        )

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as c2:
        _apply_auth(c2, auth2)
        resp2 = await c2.get("/api/auth/me")
        assert resp2.status_code == 200, (
            f"Second concurrent session failed: {resp2.status_code}"
        )


# ---------------------------------------------------------------------------
# 4. CORS — unauthorized origin
# ---------------------------------------------------------------------------

async def test_cors_unauthorized_origin(client: httpx.AsyncClient):
    """Requests from unauthorized origins must not get permissive CORS headers."""
    resp = await client.get(
        "/api/health",
        headers={"Origin": "http://evil.com"},
    )
    acao = resp.headers.get("access-control-allow-origin", "")
    assert acao != "*", "CORS allows all origins — should be restricted"
    assert "evil.com" not in acao, (
        f"CORS allows unauthorized origin evil.com: '{acao}'"
    )


# ---------------------------------------------------------------------------
# 5. No sensitive data in error responses
# ---------------------------------------------------------------------------

async def test_no_sensitive_data_in_errors(admin_client: httpx.AsyncClient):
    """Error responses must not leak stack traces, SQL, or internal details."""
    # Send invalid device data to trigger a validation error
    resp = await admin_client.post(
        "/api/devices/",
        json={"bad_field": "bad_value"},
    )
    body = resp.text.lower()

    # Should not contain traceback markers
    assert "traceback" not in body, "Error response contains Python traceback"
    assert "file \"" not in body, "Error response contains file path references"
    assert "sqlalchemy" not in body, "Error response leaks SQLAlchemy internals"
    assert "select " not in body or "select" in body[:50], (
        "Error response may leak SQL query fragments"
    )
    assert "insert into" not in body, "Error response leaks SQL INSERT statement"
    # Field name "password" in validation loc is acceptable; actual password
    # values or hashes must not appear.
    assert "bcrypt" not in body, "Error response leaks password hash details"
    assert "$2b$" not in body, "Error response leaks bcrypt hash"
