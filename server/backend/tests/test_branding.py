"""Tests for branding settings routes."""

import pytest
from httpx import AsyncClient


async def _register_and_login(client: AsyncClient, role: str = "admin") -> dict:
    """Helper: register a user and login, returning auth headers."""
    await client.post("/api/auth/register", json={
        "email": f"branding-{role}@example.com",
        "username": f"branding_{role}",
        "password": "TestPass1",
        "full_name": f"Branding {role.title()}",
    })
    resp = await client.post("/api/auth/login", json={
        "username": f"branding_{role}",
        "password": "TestPass1",
    })
    data = resp.json()
    csrf_token = data.get("csrf_token", "")
    # Extract cookies from login response
    cookies = dict(client.cookies)
    return {"X-CSRF-Token": csrf_token}


@pytest.mark.asyncio
async def test_get_branding_unauthenticated(client: AsyncClient):
    """GET /api/settings/branding without auth should fail."""
    resp = await client.get("/api/settings/branding")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_branding_returns_defaults(client: AsyncClient):
    """GET /api/settings/branding should return defaults for new install."""
    # Register and login
    await client.post("/api/auth/register", json={
        "email": "brand@example.com",
        "username": "branduser",
        "password": "TestPass1",
    })
    login = await client.post("/api/auth/login", json={
        "username": "branduser",
        "password": "TestPass1",
    })
    assert login.status_code == 200

    resp = await client.get("/api/settings/branding")
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["company_name"] == "Electracom"
    assert data["primary_color"] == "#2563eb"


@pytest.mark.asyncio
async def test_update_branding_requires_auth(client: AsyncClient):
    """PUT /api/settings/branding without auth should fail."""
    resp = await client.put("/api/settings/branding", json={
        "company_name": "Test Corp",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_upload_logo_requires_auth(client: AsyncClient):
    """POST /api/settings/branding/logo without auth should fail."""
    resp = await client.post("/api/settings/branding/logo")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_logo_requires_auth(client: AsyncClient):
    """GET /api/settings/branding/logo without auth should fail."""
    resp = await client.get("/api/settings/branding/logo")
    assert resp.status_code == 401
