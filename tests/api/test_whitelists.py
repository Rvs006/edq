"""Integration tests for /api/whitelists/ endpoints."""

import uuid

import httpx
import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.api]

BASE = "/api/whitelists/"


async def test_list_whitelists(admin_client: httpx.AsyncClient):
    """GET /api/whitelists/ returns 200 with a list."""
    resp = await admin_client.get(BASE)
    assert resp.status_code == 200
    body = resp.json()
    items = body if isinstance(body, list) else body.get("items", body.get("whitelists", []))
    assert isinstance(items, list)


async def test_create_whitelist(admin_client: httpx.AsyncClient):
    """POST /api/whitelists/ returns 201 with a new whitelist."""
    payload = {
        "name": f"Pytest WL {uuid.uuid4().hex[:6]}",
        "description": "Created by integration test",
        "entries": [
            {"port": 443, "protocol": "tcp", "service": "https"},
        ],
    }
    resp = await admin_client.post(BASE, json=payload)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["name"] == payload["name"]


async def test_update_whitelist(admin_client: httpx.AsyncClient):
    """PUT /api/whitelists/{id} returns 200 with updated whitelist."""
    create_resp = await admin_client.post(
        BASE,
        json={
            "name": f"Pytest WL Update {uuid.uuid4().hex[:6]}",
            "description": "To be updated",
            "entries": [{"port": 80, "protocol": "tcp", "service": "http"}],
        },
    )
    if create_resp.status_code not in (200, 201):
        pytest.skip(f"Cannot create whitelist for update test: {create_resp.status_code}")

    wl_id = create_resp.json()["id"]
    update_resp = await admin_client.put(
        f"{BASE}{wl_id}",
        json={
            "name": create_resp.json()["name"],
            "description": "Updated by integration test",
            "entries": [
                {"port": 80, "protocol": "tcp", "service": "http"},
                {"port": 443, "protocol": "tcp", "service": "https"},
            ],
        },
    )
    assert update_resp.status_code == 200, (
        f"Expected 200, got {update_resp.status_code}: {update_resp.text}"
    )


async def test_delete_whitelist(admin_client: httpx.AsyncClient):
    """DELETE /api/whitelists/{id} returns 204."""
    create_resp = await admin_client.post(
        BASE,
        json={
            "name": f"Pytest WL Delete {uuid.uuid4().hex[:6]}",
            "description": "To be deleted",
            "entries": [{"port": 22, "protocol": "tcp", "service": "ssh"}],
        },
    )
    if create_resp.status_code not in (200, 201):
        pytest.skip(f"Cannot create whitelist for delete test: {create_resp.status_code}")

    wl_id = create_resp.json()["id"]
    del_resp = await admin_client.delete(f"{BASE}{wl_id}")
    assert del_resp.status_code == 204

    get_resp = await admin_client.get(f"{BASE}{wl_id}")
    assert get_resp.status_code == 404
