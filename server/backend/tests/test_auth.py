"""Tests for authentication routes."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.user import User
from tests.conftest import register_and_login


@pytest.mark.asyncio
async def test_register_user(client: AsyncClient):
    """Register a new user and verify response."""
    resp = await client.post("/api/auth/register", json={
        "email": "test@example.com",
        "username": "testuser",
        "password": "TestPass1",
        "full_name": "Test User",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "test@example.com"
    assert data["username"] == "testuser"
    # Role should always be engineer regardless of input
    assert data["role"] == "engineer"


@pytest.mark.asyncio
async def test_register_duplicate_user(client: AsyncClient):
    """Registering the same email/username twice should fail."""
    payload = {
        "email": "dup@example.com",
        "username": "dupuser",
        "password": "TestPass1",
    }
    resp1 = await client.post("/api/auth/register", json=payload)
    assert resp1.status_code == 201

    resp2 = await client.post("/api/auth/register", json=payload)
    assert resp2.status_code == 400
    assert "already registered" in resp2.json()["detail"]


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    """Login with valid credentials should succeed."""
    reg = await client.post("/api/auth/register", json={
        "email": "login@example.com",
        "username": "loginuser",
        "password": "TestPass1",
    })
    assert reg.status_code == 201, f"Register failed: {reg.text}"

    resp = await client.post("/api/auth/login", json={
        "username": "loginuser",
        "password": "TestPass1",
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    data = resp.json()
    assert data["message"] == "Login successful"
    assert "csrf_token" in data
    # Refresh token is set as an httpOnly cookie, not in the JSON body
    assert client.cookies.get("edq_refresh")


@pytest.mark.asyncio
async def test_login_success_with_email_identifier(client: AsyncClient):
    """Login should accept the account email in the username field."""
    reg = await client.post("/api/auth/register", json={
        "email": "email-login@example.com",
        "username": "emailloginuser",
        "password": "TestPass1",
    })
    assert reg.status_code == 201, f"Register failed: {reg.text}"

    resp = await client.post("/api/auth/login", json={
        "username": "email-login@example.com",
        "password": "TestPass1",
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    assert resp.json()["message"] == "Login successful"


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient):
    """Login with wrong password should fail."""
    await client.post("/api/auth/register", json={
        "email": "bad@example.com",
        "username": "badlogin",
        "password": "TestPass1",
    })
    resp = await client.post("/api/auth/login", json={
        "username": "badlogin",
        "password": "WrongPass1",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_password_complexity_rejected(client: AsyncClient):
    """Registration with a weak password should be rejected."""
    resp = await client.post("/api/auth/register", json={
        "email": "weak@example.com",
        "username": "weakuser",
        "password": "alllowercase",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_me_unauthenticated(client: AsyncClient):
    """Accessing /me without a session cookie should fail."""
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_logout_authenticated(client: AsyncClient):
    """Logout with a valid session should succeed and revoke tokens."""
    # Register and login to get session cookies + CSRF
    await client.post("/api/auth/register", json={
        "email": "logout@example.com",
        "username": "logoutuser",
        "password": "TestPass1",
    })
    login_resp = await client.post("/api/auth/login", json={
        "username": "logoutuser",
        "password": "TestPass1",
    })
    assert login_resp.status_code == 200
    csrf = login_resp.json()["csrf_token"]

    resp = await client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    assert resp.json()["message"] == "Logged out successfully"


@pytest.mark.asyncio
async def test_logout_unauthenticated(client: AsyncClient):
    """Logout without authentication should return 401."""
    resp = await client.post("/api/auth/logout")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_single_use(client: AsyncClient):
    """A refresh token should work once and fail on second use."""
    await client.post("/api/auth/register", json={
        "email": "refresh@example.com",
        "username": "refreshuser",
        "password": "TestPass1",
    })
    login_resp = await client.post("/api/auth/login", json={
        "username": "refreshuser",
        "password": "TestPass1",
    })
    assert login_resp.status_code == 200
    refresh_token = client.cookies.get("edq_refresh")
    assert refresh_token

    # First use should succeed
    resp1 = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert resp1.status_code == 200

    # Second use of the SAME token should fail (single-use rotation)
    resp2 = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert resp2.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_rotation(client: AsyncClient):
    """After refresh, the new token should work."""
    await client.post("/api/auth/register", json={
        "email": "rotate@example.com",
        "username": "rotateuser",
        "password": "TestPass1",
    })
    login_resp = await client.post("/api/auth/login", json={
        "username": "rotateuser",
        "password": "TestPass1",
    })
    refresh_token = client.cookies.get("edq_refresh")

    # Rotate
    resp1 = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert resp1.status_code == 200
    new_token = client.cookies.get("edq_refresh")

    # New token should work
    resp2 = await client.post("/api/auth/refresh", json={"refresh_token": new_token})
    assert resp2.status_code == 200


@pytest.mark.asyncio
async def test_refresh_token_cookie_rotation(client: AsyncClient):
    """The frontend cookie-based refresh path should rotate without a JSON body."""
    await client.post("/api/auth/register", json={
        "email": "cookie-refresh@example.com",
        "username": "cookierefreshuser",
        "password": "TestPass1",
    })
    login_resp = await client.post("/api/auth/login", json={
        "username": "cookierefreshuser",
        "password": "TestPass1",
    })
    assert login_resp.status_code == 200
    original_cookie = client.cookies.get("edq_refresh")
    assert original_cookie

    refresh_resp = await client.post("/api/auth/refresh")
    assert refresh_resp.status_code == 200
    new_cookie = client.cookies.get("edq_refresh")
    assert new_cookie
    assert new_cookie != original_cookie


@pytest.mark.asyncio
async def test_refresh_token_reuse_revokes_family(client: AsyncClient):
    """Reusing a revoked refresh token should revoke ALL tokens for that user."""
    await client.post("/api/auth/register", json={
        "email": "reuse@example.com",
        "username": "reuseuser",
        "password": "TestPass1",
    })
    login_resp = await client.post("/api/auth/login", json={
        "username": "reuseuser",
        "password": "TestPass1",
    })
    old_token = client.cookies.get("edq_refresh")

    # Rotate to get a new token (old_token is now revoked)
    resp1 = await client.post("/api/auth/refresh", json={"refresh_token": old_token})
    assert resp1.status_code == 200
    new_token = client.cookies.get("edq_refresh")

    # Reuse the old (revoked) token — should trigger family revocation
    resp2 = await client.post("/api/auth/refresh", json={"refresh_token": old_token})
    assert resp2.status_code == 401

    # The new token should also be revoked now
    resp3 = await client.post("/api/auth/refresh", json={"refresh_token": new_token})
    assert resp3.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_for_inactive_user_stays_revoked(client: AsyncClient, db_session):
    """Inactive accounts should not be able to replay a rotated refresh token."""
    await client.post("/api/auth/register", json={
        "email": "inactive-refresh@example.com",
        "username": "inactiverefreshuser",
        "password": "TestPass1",
    })
    login_resp = await client.post("/api/auth/login", json={
        "username": "inactiverefreshuser",
        "password": "TestPass1",
    })
    assert login_resp.status_code == 200
    refresh_token = client.cookies.get("edq_refresh")
    assert refresh_token

    user_result = await db_session.execute(
        select(User).where(User.username == "inactiverefreshuser")
    )
    user = user_result.scalar_one()
    user.is_active = False
    await db_session.commit()

    first_refresh = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert first_refresh.status_code == 401

    second_refresh = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert second_refresh.status_code == 401


@pytest.mark.asyncio
async def test_profile_email_uniqueness_is_case_insensitive(client: AsyncClient):
    """Updating email should reject case-only duplicates."""
    first_headers = await register_and_login(client, suffix="emailcasea")
    await client.post("/api/auth/logout", headers=first_headers)
    second_headers = await register_and_login(client, suffix="emailcaseb")

    resp = await client.patch(
        "/api/auth/me",
        json={"email": "EMAILCASEA@example.com"},
        headers=second_headers,
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Email already in use"
