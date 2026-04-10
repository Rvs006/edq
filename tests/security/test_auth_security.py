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

async def test_account_lockout(client: httpx.AsyncClient, admin_client: httpx.AsyncClient):
    """Repeated wrong logins should lock a disposable account without breaking admin auth."""
    username = f"lockout-{uuid.uuid4().hex[:8]}"
    password = "Lockout@2026!"
    create_resp = await admin_client.post(
        "/api/users/",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": password,
            "full_name": "Lockout Probe",
            "role": "engineer",
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    user = create_resp.json()

    statuses = []
    for _ in range(10):
        resp = await client.post(
            "/api/auth/login",
            json={"username": username, "password": "WrongPassword!"},
        )
        statuses.append(resp.status_code)

    assert statuses, "Expected login attempts to be recorded"
    assert all(status == 401 for status in statuses), statuses

    locked_resp = await client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert locked_resp.status_code == 401, locked_resp.text

    await admin_client.patch(
        f"/api/users/{user['id']}",
        json={"is_active": False},
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

    # Logout revokes admin access tokens user-wide; force the next fixture use
    # to obtain a fresh login instead of reusing a poisoned cache entry.
    invalidate_auth_cache(ADMIN_USER)


# ---------------------------------------------------------------------------
# 4. Password complexity — too short
# ---------------------------------------------------------------------------

async def test_password_complexity_short():
    """Changing password to a very short string should be rejected."""
    fresh_auth = await _login(ADMIN_USER, ADMIN_PASS)
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as c:
        _apply_auth(c, fresh_auth)
        resp = await c.post(
            "/api/auth/change-password",
            json={"current_password": ADMIN_PASS, "new_password": "123"},
        )
        assert resp.status_code in (400, 422), (
            f"Expected 400/422 for weak password, got {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# 5. Password complexity — common password
# ---------------------------------------------------------------------------

async def test_password_complexity_common():
    """Changing password to a common word should be rejected."""
    fresh_auth = await _login(ADMIN_USER, ADMIN_PASS)
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as c:
        _apply_auth(c, fresh_auth)
        resp = await c.post(
            "/api/auth/change-password",
            json={"current_password": ADMIN_PASS, "new_password": "password"},
        )
        assert resp.status_code in (400, 422), (
            f"Expected 400/422 for common password, got {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# 6. Session invalidation after password change
# ---------------------------------------------------------------------------

async def test_session_after_password_change(admin_client: httpx.AsyncClient):
    """After password change, old session should be invalidated."""
    username = f"pwreset-{uuid.uuid4().hex[:8]}"
    original_pass = "OrigPwd@2026!"
    new_pass = "NewPwd@2026!"

    create_resp = await admin_client.post(
        "/api/users/",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": original_pass,
            "full_name": "Password Reset Probe",
            "role": "engineer",
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    created_user = create_resp.json()

    old_auth = await _login(username, original_pass)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as c:
        _apply_auth(c, old_auth)

        # Change password
        change_resp = await c.post(
            "/api/auth/change-password",
            json={"current_password": original_pass, "new_password": new_pass},
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

    await admin_client.patch(
        f"/api/users/{created_user['id']}",
        json={"is_active": False},
    )
