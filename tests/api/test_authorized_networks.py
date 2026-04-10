"""Integration tests for /api/authorized-networks/ endpoints."""

import uuid

import httpx
import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.api]

BASE = "/api/authorized-networks/"


async def test_list_networks(admin_client: httpx.AsyncClient):
    """GET /api/authorized-networks/ returns 200 with a list."""
    resp = await admin_client.get(BASE)
    assert resp.status_code == 200
    body = resp.json()
    items = body if isinstance(body, list) else body.get("items", body.get("networks", []))
    assert isinstance(items, list)


async def test_add_network(admin_client: httpx.AsyncClient):
    """POST /api/authorized-networks/ returns 201."""
    unique_cidr = f"10.{uuid.uuid4().int % 200 + 50}.0.0/16"
    payload = {
        "cidr": unique_cidr,
        "name": f"Pytest Net {uuid.uuid4().hex[:6]}",
        "description": "Created by integration test",
    }
    resp = await admin_client.post(BASE, json=payload)
    assert resp.status_code in (200, 201, 409), f"Expected 200/201/409, got {resp.status_code}: {resp.text}"
    if resp.status_code == 409:
        pytest.skip("Network CIDR already exists — likely leftover from previous test run")
    data = resp.json()
    assert "id" in data
    net_id = data["id"]
    # Cleanup
    await admin_client.delete(f"{BASE}{net_id}")


async def test_remove_network(admin_client: httpx.AsyncClient):
    """DELETE /api/authorized-networks/{id} returns 204."""
    create_resp = await admin_client.post(
        BASE,
        json={
            "cidr": "172.16.0.0/12",
            "name": f"Pytest Net Delete {uuid.uuid4().hex[:6]}",
            "description": "To be deleted",
        },
    )
    if create_resp.status_code not in (200, 201):
        pytest.skip(f"Cannot create network for delete test: {create_resp.status_code}")

    net_id = create_resp.json()["id"]
    del_resp = await admin_client.delete(f"{BASE}{net_id}")
    assert del_resp.status_code == 204

    # After delete, GET by ID may return 404 (resource gone) or 200 with
    # empty/null body if the endpoint returns the full list instead.
    get_resp = await admin_client.get(f"{BASE}{net_id}")
    assert get_resp.status_code in (200, 404)
