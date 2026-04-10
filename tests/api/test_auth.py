"""Authentication endpoint tests — login, logout, refresh, me, change-password."""

import uuid

import httpx
import pytest

from tests.auth_cache import invalidate_auth_cache
from tests.helpers import BASE_URL, ADMIN_USER, ADMIN_PASS, _login, _apply_auth

pytestmark = [pytest.mark.asyncio, pytest.mark.api]


# ---------------------------------------------------------------------------
# 1. Login — valid credentials
# ---------------------------------------------------------------------------

async def test_login_valid(client: httpx.AsyncClient):
    resp = await client.post(
        "/api/auth/login",
        json={"username": ADMIN_USER, "password": ADMIN_PASS},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "user" in data
    assert data["user"]["role"] == "admin"
    assert data["user"]["username"] == ADMIN_USER
    # Session cookie should be set
    assert "edq_session" in resp.cookies or data.get("csrf_token")


# ---------------------------------------------------------------------------
# 2. Login — wrong password
# ---------------------------------------------------------------------------

async def test_login_wrong_password(client: httpx.AsyncClient):
    resp = await client.post(
        "/api/auth/login",
        json={"username": ADMIN_USER, "password": "WrongPassword!"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 3. Login — empty fields
# ---------------------------------------------------------------------------

async def test_login_empty_fields(client: httpx.AsyncClient):
    resp = await client.post("/api/auth/login", json={})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 4. Login — empty username
# ---------------------------------------------------------------------------

async def test_login_empty_username(client: httpx.AsyncClient):
    resp = await client.post(
        "/api/auth/login",
        json={"username": "", "password": ADMIN_PASS},
    )
    assert resp.status_code in (401, 422)


# ---------------------------------------------------------------------------
# 5. Login — nonexistent user
# ---------------------------------------------------------------------------

async def test_login_nonexistent_user(client: httpx.AsyncClient):
    resp = await client.post(
        "/api/auth/login",
        json={"username": f"no_such_user_{uuid.uuid4().hex[:8]}", "password": "Whatever1!"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 6. Logout — then /me should fail
# ---------------------------------------------------------------------------

async def test_logout(client: httpx.AsyncClient):
    # Login to get fresh cookies
    auth = await _login(ADMIN_USER, ADMIN_PASS)

    # Build a new client with those cookies for logout
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as c:
        _apply_auth(c, auth)

        # Logout
        resp = await c.post("/api/auth/logout")
        assert resp.status_code == 200

        # JWT tokens are stateless — the server does not track invalidated
        # tokens, so the old session cookie remains valid until expiry.
        # The logout endpoint clears cookies client-side but cannot revoke
        # a stateless JWT.  Accept 200 (token still valid) as correct.
        me_resp = await c.get("/api/auth/me")
        # With JWT blacklist, logout now revokes the token → expect 401
        assert me_resp.status_code == 401


# ---------------------------------------------------------------------------
# 7. Refresh token
# ---------------------------------------------------------------------------

async def test_refresh_token(client: httpx.AsyncClient):
    auth = await _login(ADMIN_USER, ADMIN_PASS)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as c:
        c.cookies.set("edq_session", auth["session_cookie"])
        if auth.get("refresh_cookie"):
            c.cookies.set("edq_refresh", auth["refresh_cookie"])
        c.headers["X-CSRF-Token"] = auth["csrf_token"]

        resp = await c.post("/api/auth/refresh")
        assert resp.status_code == 200
        data = resp.json()
        assert "csrf_token" in data or "message" in data


# ---------------------------------------------------------------------------
# 8. Get current user
# ---------------------------------------------------------------------------

async def test_get_current_user(admin_client: httpx.AsyncClient):
    resp = await admin_client.get("/api/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert "username" in data
    assert "role" in data


# ---------------------------------------------------------------------------
# 9. Update profile
# ---------------------------------------------------------------------------

async def test_update_profile(admin_client: httpx.AsyncClient):
    new_name = f"Admin Updated {uuid.uuid4().hex[:4]}"
    resp = await admin_client.patch(
        "/api/auth/me",
        json={"full_name": new_name},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("full_name") == new_name


# ---------------------------------------------------------------------------
# 10. Change password — valid (use a temp user, not admin)
# ---------------------------------------------------------------------------

async def test_change_password_valid():
    from tests.helpers import ENGINEER_USER, ENGINEER_PASS
    new_pass = "NewEng@2026!"

    # Login as engineer and change password
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as c:
        auth = await _login(ENGINEER_USER, ENGINEER_PASS)
        _apply_auth(c, auth)

        resp = await c.post(
            "/api/auth/change-password",
            json={"current_password": ENGINEER_PASS, "new_password": new_pass},
        )
        assert resp.status_code == 200

    # Verify login with new password works
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as c:
        login_resp = await c.post(
            "/api/auth/login",
            json={"username": ENGINEER_USER, "password": new_pass},
        )
        assert login_resp.status_code == 200

    # Change back (cleanup)
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as c:
        auth = await _login(ENGINEER_USER, new_pass)
        _apply_auth(c, auth)
        await c.post(
            "/api/auth/change-password",
            json={"current_password": new_pass, "new_password": ENGINEER_PASS},
        )

    # Password change revokes tokens — clear the cache so subsequent tests re-login
    invalidate_auth_cache(ENGINEER_USER)


# ---------------------------------------------------------------------------
# 11. Change password — wrong old password
# ---------------------------------------------------------------------------

async def test_change_password_wrong_old():
    # Use a fresh login to avoid token revocation cascades
    from tests.helpers import ENGINEER_USER, ENGINEER_PASS
    auth = await _login(ENGINEER_USER, ENGINEER_PASS)
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as c:
        _apply_auth(c, auth)
        resp = await c.post(
            "/api/auth/change-password",
            json={"current_password": "TotallyWrong!", "new_password": "DoesNotMatter1!"},
        )
    assert resp.status_code in (400, 401)


# ---------------------------------------------------------------------------
# 12. Change password — weak new password
# ---------------------------------------------------------------------------

async def test_change_password_weak():
    # Use a fresh login to avoid token revocation cascades
    from tests.helpers import ENGINEER_USER, ENGINEER_PASS
    auth = await _login(ENGINEER_USER, ENGINEER_PASS)
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as c:
        _apply_auth(c, auth)
        resp = await c.post(
            "/api/auth/change-password",
            json={"current_password": ENGINEER_PASS, "new_password": "123"},
        )
    assert resp.status_code in (400, 422)
