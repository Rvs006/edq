"""Tests for authentication routes."""

import pytest
import pytest_asyncio
from httpx import AsyncClient


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
    assert "refresh_token" in data


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
async def test_logout(client: AsyncClient):
    """Logout should return success."""
    resp = await client.post("/api/auth/logout")
    assert resp.status_code == 200
    assert resp.json()["message"] == "Logged out successfully"
