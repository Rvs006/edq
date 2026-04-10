"""Tests for protocol whitelist management routes."""

import pytest
from httpx import AsyncClient

from .conftest import register_and_login


@pytest.mark.asyncio
async def test_create_whitelist(client: AsyncClient):
    """Create a whitelist with entries."""
    headers = await register_and_login(client, "wlcreate", role="admin")
    resp = await client.post("/api/whitelists/", json={
        "name": "BMS Standard",
        "description": "Standard BMS protocols",
        "entries": [
            {"port": 80, "protocol": "tcp", "service": "HTTP", "justification": "Web UI"},
            {"port": 443, "protocol": "tcp", "service": "HTTPS", "justification": "Secure Web UI"},
        ],
    }, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "BMS Standard"
    assert len(data["entries"]) == 2
    assert "id" in data


@pytest.mark.asyncio
async def test_list_whitelists(client: AsyncClient):
    """List whitelists returns a list."""
    headers = await register_and_login(client, "wllist", role="admin")
    resp = await client.get("/api/whitelists/", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_get_whitelist(client: AsyncClient):
    """Get a single whitelist by ID."""
    headers = await register_and_login(client, "wlget", role="admin")
    create_resp = await client.post("/api/whitelists/", json={
        "name": "Get Test WL",
        "entries": [{"port": 22, "protocol": "tcp", "service": "SSH", "justification": "Admin"}],
    }, headers=headers)
    wl_id = create_resp.json()["id"]

    resp = await client.get(f"/api/whitelists/{wl_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == wl_id


@pytest.mark.asyncio
async def test_update_whitelist(client: AsyncClient):
    """Update whitelist name and entries."""
    headers = await register_and_login(client, "wlupdate", role="admin")
    create_resp = await client.post("/api/whitelists/", json={
        "name": "Original WL",
        "entries": [],
    }, headers=headers)
    wl_id = create_resp.json()["id"]

    resp = await client.put(f"/api/whitelists/{wl_id}", json={
        "name": "Updated WL",
        "entries": [{"port": 443, "protocol": "tcp", "service": "HTTPS", "justification": "Required"}],
    }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated WL"
    assert len(resp.json()["entries"]) == 1


@pytest.mark.asyncio
async def test_delete_whitelist(client: AsyncClient):
    """Delete a whitelist."""
    headers = await register_and_login(client, "wldelete", role="admin")
    create_resp = await client.post("/api/whitelists/", json={
        "name": "To Delete WL",
        "entries": [],
    }, headers=headers)
    wl_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/whitelists/{wl_id}", headers=headers)
    assert resp.status_code == 204

    # Verify it's gone
    get_resp = await client.get(f"/api/whitelists/{wl_id}", headers=headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_duplicate_whitelist(client: AsyncClient):
    """Duplicate a whitelist creates a copy."""
    headers = await register_and_login(client, "wldup", role="admin")
    create_resp = await client.post("/api/whitelists/", json={
        "name": "Original",
        "description": "The original whitelist",
        "entries": [{"port": 80, "protocol": "tcp", "service": "HTTP", "justification": "Web"}],
    }, headers=headers)
    wl_id = create_resp.json()["id"]

    resp = await client.post(f"/api/whitelists/{wl_id}/duplicate", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Original (Copy)"
    assert data["id"] != wl_id
    assert len(data["entries"]) == 1
