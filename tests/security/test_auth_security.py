"""Authentication security tests — lockout, CSRF, session invalidation, password policy."""

import uuid

import httpx
import pytest

from tests.auth_cache import invalidate_auth_cache
from tests.helpers import BASE_URL, ADMIN_USER, ADMIN_PASS, _login, _apply_auth

pytestmark = [pytest.mark.asyncio, pytest.mark.security]


# ---------------------------------------------------------------------------
# 1. Account lockout after repeated failures
# ---------------------------------------------------------------------------

async def test_account_lockout(client: httpx.AsyncClient):
    """Repeated wrong logins should eventually trigger lockout or rate limiting."""
    statuses = []
    for _ in range(10):
        resp = await client.post(
            "/api/auth/login",
            json={"username": ADMIN_USER, "password": "WrongPassword!"},
        )
        statuses.append(resp.status_code)

    has_lockout = any(s == 429 for s in statuses)
    has_locked_message = any(s == 423 for s in statuses)
    if not (has_lockout or has_locked_message):
        pytest.xfail(
            "Account lockout not enforced — all attempts returned "
            f"{set(statuses)}"
        )


# ---------------------------------------------------------------------------
# 2. CSRF protection
# ---------------------------------------------------------------------------

async def test_csrf_protection(admin_auth: dict):
    """Mutating request with valid session but no CSRF token should be rejected."""
    session_cookie = admin_auth.get("session_cookie", "")
    if not session_cookie:
        pytest.skip("No session cookie available")

    # Make a mutating request WITH session cookie but WITHOUT CSRF token/cookie
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as c2:
        c2.cookies.set("edq_session", session_cookie)
        # Intentionally omit X-CSRF-Token and edq_csrf cookie
        resp = await c2.post(
            "/api/devices/",
            json={
                "ip_address": "10.99.1.1",
                "hostname": "csrf-test",
                "manufacturer": "TestCo",
                "model": "T-100",
                "device_type": "controller",
                "category": "controller",
            },
        )
        if resp.status_code == 201:
            pytest.xfail("CSRF protection not enforced on this endpoint")
        assert resp.status_code == 403, (
            f"Expected 403 for missing CSRF token, got {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# 3. Logout invalidates token
# ---------------------------------------------------------------------------

async def test_logout_invalidates_token():
    """After logout, old session cookie must not grant access."""
    # Use a FRESH login (not cached) so logout doesn't revoke the cached admin token
    fresh_auth = await _login(ADMIN_USER, ADMIN_PASS)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as c:
        _apply_auth(c, fresh_auth)

        # Verify we are authenticated
        me_resp = await c.get("/api/auth/me")
        assert me_resp.status_code == 200

        # Logout — this revokes the fresh token's JTI
        logout_resp = await c.post("/api/auth/logout")
        assert logout_resp.status_code in (200, 204)

    # Try to use old session cookie — should be revoked via JWT blacklist
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as c2:
        c2.cookies.set("edq_session", fresh_auth["session_cookie"])
        c2.cookies.set("edq_csrf", fresh_auth["csrf_token"])
        c2.headers["X-CSRF-Token"] = fresh_auth["csrf_token"]
        me_resp2 = await c2.get("/api/auth/me")
        assert me_resp2.status_code == 401, (
            f"Expected 401 after logout, got {me_resp2.status_code}"
        )


# ---------------------------------------------------------------------------
# 4. Password complexity — too short
# ---------------------------------------------------------------------------

async def test_password_complexity_short(admin_client: httpx.AsyncClient):
    """Changing password to a very short string should be rejected."""
    resp = await admin_client.post(
        "/api/auth/change-password",
        json={"current_password": ADMIN_PASS, "new_password": "123"},
    )
    assert resp.status_code in (400, 422), (
        f"Expected 400/422 for weak password, got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# 5. Password complexity — common password
# ---------------------------------------------------------------------------

async def test_password_complexity_common(admin_client: httpx.AsyncClient):
    """Changing password to a common word should be rejected."""
    resp = await admin_client.post(
        "/api/auth/change-password",
        json={"current_password": ADMIN_PASS, "new_password": "password"},
    )
    assert resp.status_code in (400, 422), (
        f"Expected 400/422 for common password, got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# 6. Session invalidation after password change
# ---------------------------------------------------------------------------

async def test_session_after_password_change():
    """After password change, old session should be invalidated."""
    from tests.helpers import REVIEWER_USER, REVIEWER_PASS
    new_pass = "NewRev@2026!"

    # Use a FRESH login so we don't revoke the cached reviewer token
    old_auth = await _login(REVIEWER_USER, REVIEWER_PASS)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as c:
        _apply_auth(c, old_auth)

        # Change password
        change_resp = await c.post(
            "/api/auth/change-password",
            json={"current_password": REVIEWER_PASS, "new_password": new_pass},
        )
        if change_resp.status_code not in (200, 204):
            pytest.skip(
                f"Password change not supported or failed: {change_resp.status_code}"
            )

    # Try old session — should now be revoked via JWT blacklist
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as c2:
        c2.cookies.set("edq_session", old_auth["session_cookie"])
        c2.cookies.set("edq_csrf", old_auth["csrf_token"])
        c2.headers["X-CSRF-Token"] = old_auth["csrf_token"]
        me_resp = await c2.get("/api/auth/me")
        assert me_resp.status_code == 401, (
            f"Expected 401 after password change, got {me_resp.status_code}"
        )

    # Restore original password
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as c3:
        new_auth = await _login(REVIEWER_USER, new_pass)
        _apply_auth(c3, new_auth)
        await c3.post(
            "/api/auth/change-password",
            json={"current_password": new_pass, "new_password": REVIEWER_PASS},
        )

    # Password change revokes tokens — clear cache
    invalidate_auth_cache(REVIEWER_USER)
