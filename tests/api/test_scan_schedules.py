"""Integration tests for /api/scan-schedules/ endpoints."""

import uuid

import httpx
import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.api]

BASE = "/api/scan-schedules/"


async def _get_ids(admin_client: httpx.AsyncClient):
    """Get a device_id and template_id for schedule creation."""
    dev_resp = await admin_client.get("/api/devices/")
    devs = dev_resp.json()
    items = devs if isinstance(devs, list) else devs.get("items", [])
    if not items:
        return None, None
    device_id = items[0]["id"]

    tmpl_resp = await admin_client.get("/api/test-templates/")
    tmpls = tmpl_resp.json()
    if not tmpls:
        return device_id, None
    template_id = tmpls[0]["id"]
    return device_id, template_id


async def test_list_schedules(admin_client: httpx.AsyncClient):
    """GET /api/scan-schedules/ returns 200 with a list."""
    resp = await admin_client.get(BASE)
    assert resp.status_code == 200
    body = resp.json()
    items = body if isinstance(body, list) else body.get("items", body.get("schedules", []))
    assert isinstance(items, list)


async def test_create_schedule(admin_client: httpx.AsyncClient):
    """POST /api/scan-schedules/ returns 201 with the new schedule."""
    device_id, template_id = await _get_ids(admin_client)
    if not device_id or not template_id:
        pytest.skip("No device or template available for schedule creation")

    payload = {
        "device_id": device_id,
        "template_id": template_id,
        "frequency": "weekly",
    }
    resp = await admin_client.post(BASE, json=payload)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "id" in data

    # Cleanup
    await admin_client.delete(f"{BASE}{data['id']}")


async def test_toggle_schedule(admin_client: httpx.AsyncClient):
    """PATCH /api/scan-schedules/{id} to disable a schedule returns 200."""
    device_id, template_id = await _get_ids(admin_client)
    if not device_id or not template_id:
        pytest.skip("No device or template available")

    create_resp = await admin_client.post(
        BASE,
        json={
            "device_id": device_id,
            "template_id": template_id,
            "frequency": "daily",
        },
    )
    if create_resp.status_code not in (200, 201):
        pytest.skip(f"Cannot create schedule: {create_resp.status_code}")

    schedule_id = create_resp.json()["id"]
    patch_resp = await admin_client.patch(
        f"{BASE}{schedule_id}",
        json={"is_active": False},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_active"] is False

    # Cleanup
    await admin_client.delete(f"{BASE}{schedule_id}")
