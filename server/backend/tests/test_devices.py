"""Tests for device management routes."""

import pytest
from httpx import AsyncClient

from .conftest import register_and_login


@pytest.mark.asyncio
async def test_create_device(client: AsyncClient):
    """Create a device and verify response fields."""
    headers = await register_and_login(client, "devcreate", role="admin")
    resp = await client.post("/api/devices/", json={
        "ip_address": "192.168.1.10",
        "hostname": "test-camera",
        "manufacturer": "Axis",
        "category": "camera",
    }, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["ip_address"] == "192.168.1.10"
    assert data["hostname"] == "test-camera"
    assert data["manufacturer"] == "Axis"
    assert data["category"] == "camera"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_device_with_project_and_extended_fields(client: AsyncClient):
    """Creating a device should persist project, location, and serial number."""
    headers = await register_and_login(client, "devproject", role="admin")
    project_resp = await client.post("/api/projects/", json={
        "name": "Project Alpha",
    }, headers=headers)
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    resp = await client.post("/api/devices/", json={
        "ip_address": "192.168.1.11",
        "hostname": "project-camera",
        "serial_number": "SN-12345",
        "location": "Level 2 comms room",
        "project_id": project_id,
    }, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["project_id"] == project_id
    assert data["serial_number"] == "SN-12345"
    assert data["location"] == "Level 2 comms room"


@pytest.mark.asyncio
async def test_create_device_invalid_ip(client: AsyncClient):
    """Creating a device with an invalid IP should fail validation."""
    headers = await register_and_login(client, "devinvalid", role="admin")
    resp = await client.post("/api/devices/", json={
        "ip_address": "999.999.999.999",
    }, headers=headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_device_duplicate_ip(client: AsyncClient):
    """Creating two devices with the same IP should fail."""
    headers = await register_and_login(client, "devdup", role="admin")
    payload = {"ip_address": "10.0.0.1", "hostname": "dup-test"}
    resp1 = await client.post("/api/devices/", json=payload, headers=headers)
    assert resp1.status_code == 201

    resp2 = await client.post("/api/devices/", json=payload, headers=headers)
    assert resp2.status_code == 409
    assert "already exists" in resp2.json()["detail"]


@pytest.mark.asyncio
async def test_list_devices(client: AsyncClient):
    """List devices returns created devices."""
    headers = await register_and_login(client, "devlist", role="admin")
    await client.post("/api/devices/", json={
        "ip_address": "172.16.0.1",
        "hostname": "list-test",
    }, headers=headers)
    resp = await client.get("/api/devices/", headers=headers)
    assert resp.status_code == 200
    devices = resp.json()
    assert isinstance(devices, list)
    assert len(devices) >= 1


@pytest.mark.asyncio
async def test_get_device(client: AsyncClient):
    """Get a single device by ID."""
    headers = await register_and_login(client, "devget", role="admin")
    create_resp = await client.post("/api/devices/", json={
        "ip_address": "172.16.0.2",
    }, headers=headers)
    device_id = create_resp.json()["id"]

    resp = await client.get(f"/api/devices/{device_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == device_id


@pytest.mark.asyncio
async def test_get_device_not_found(client: AsyncClient):
    """Getting a non-existent device returns 404."""
    headers = await register_and_login(client, "devnotfound", role="admin")
    resp = await client.get("/api/devices/nonexistent-id", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_device(client: AsyncClient):
    """Update device fields."""
    headers = await register_and_login(client, "devupdate", role="admin")
    create_resp = await client.post("/api/devices/", json={
        "ip_address": "172.16.0.3",
        "hostname": "before-update",
    }, headers=headers)
    device_id = create_resp.json()["id"]

    resp = await client.patch(f"/api/devices/{device_id}", json={
        "hostname": "after-update",
        "manufacturer": "Siemens",
    }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["hostname"] == "after-update"
    assert resp.json()["manufacturer"] == "Siemens"


@pytest.mark.asyncio
async def test_update_device_extended_fields(client: AsyncClient):
    """Updating serial number and location should persist to the device record."""
    headers = await register_and_login(client, "devupdateext", role="admin")
    create_resp = await client.post("/api/devices/", json={
        "ip_address": "172.16.0.33",
        "hostname": "field-device",
    }, headers=headers)
    device_id = create_resp.json()["id"]

    resp = await client.patch(f"/api/devices/{device_id}", json={
        "serial_number": "SERIAL-9000",
        "location": "Plant room",
    }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["serial_number"] == "SERIAL-9000"
    assert resp.json()["location"] == "Plant room"


@pytest.mark.asyncio
async def test_update_device_invalid_ip(client: AsyncClient):
    """Updating with invalid IP should fail validation."""
    headers = await register_and_login(client, "devupdateip", role="admin")
    create_resp = await client.post("/api/devices/", json={
        "ip_address": "172.16.0.4",
    }, headers=headers)
    device_id = create_resp.json()["id"]

    resp = await client.patch(f"/api/devices/{device_id}", json={
        "ip_address": "not-an-ip",
    }, headers=headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_device_stats(client: AsyncClient):
    """Device stats endpoint returns totals and breakdowns."""
    headers = await register_and_login(client, "devstats", role="admin")
    await client.post("/api/devices/", json={
        "ip_address": "172.16.0.5",
        "category": "camera",
    }, headers=headers)

    resp = await client.get("/api/devices/stats", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "by_status" in data
    assert "by_category" in data
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_devices_unauthenticated(client: AsyncClient):
    """Accessing devices without auth should fail."""
    resp = await client.get("/api/devices/")
    assert resp.status_code == 401
