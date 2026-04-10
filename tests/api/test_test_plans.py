"""Integration tests for /api/test-plans/ endpoints."""

import uuid

import httpx
import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.api]

BASE = "/api/test-plans/"


async def test_list_plans(admin_client: httpx.AsyncClient):
    """GET /api/test-plans/ returns 200 with a list."""
    resp = await admin_client.get(BASE)
    assert resp.status_code == 200
    body = resp.json()
    items = body if isinstance(body, list) else body.get("items", body.get("plans", []))
    assert isinstance(items, list)


async def test_create_plan(admin_client: httpx.AsyncClient):
    """POST /api/test-plans/ returns 201 with the new plan."""
    payload = {
        "name": f"Pytest Plan {uuid.uuid4().hex[:6]}",
        "description": "Integration test plan",
        "test_configs": [
            {"test_id": "port-scan", "enabled": True},
            {"test_id": "default-creds", "enabled": True},
        ],
    }
    resp = await admin_client.post(BASE, json=payload)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "id" in data

    # Cleanup
    await admin_client.delete(f"{BASE}{data['id']}")


async def test_update_plan(admin_client: httpx.AsyncClient):
    """PUT /api/test-plans/{id} returns 200."""
    create_resp = await admin_client.post(
        BASE,
        json={
            "name": f"Pytest Update Plan {uuid.uuid4().hex[:6]}",
            "description": "To be updated",
            "test_configs": [{"test_id": "port-scan", "enabled": True}],
        },
    )
    if create_resp.status_code not in (200, 201):
        pytest.skip(f"Cannot create plan: {create_resp.status_code}")

    plan_id = create_resp.json()["id"]
    update_resp = await admin_client.put(
        f"{BASE}{plan_id}",
        json={
            "name": f"Updated Plan {uuid.uuid4().hex[:6]}",
            "description": "Updated by test",
            "test_configs": [
                {"test_id": "port-scan", "enabled": True},
                {"test_id": "default-creds", "enabled": False},
            ],
        },
    )
    assert update_resp.status_code == 200

    # Cleanup
    await admin_client.delete(f"{BASE}{plan_id}")
