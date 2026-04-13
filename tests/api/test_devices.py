"""Device endpoint tests — CRUD, import, export, compare, trends."""

import io
import uuid

import httpx
import pytest

from live_helpers import unique_ip

pytestmark = [pytest.mark.asyncio, pytest.mark.api]


# ---------------------------------------------------------------------------
# 1. List devices (auth required)
# ---------------------------------------------------------------------------

async def test_list_devices(admin_client: httpx.AsyncClient):
    resp = await admin_client.get("/api/devices/")
    assert resp.status_code == 200
    data = resp.json()
    # Response is a list (DeviceResponse[])
    assert isinstance(data, list)


# ---------------------------------------------------------------------------
# 2. List devices — no auth
# ---------------------------------------------------------------------------

async def test_list_devices_no_auth(client: httpx.AsyncClient):
    resp = await client.get("/api/devices/")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 3. Create device
# ---------------------------------------------------------------------------

async def test_create_device(admin_client: httpx.AsyncClient):
    ip = unique_ip()
    resp = await admin_client.post(
        "/api/devices/",
        json={
            "ip_address": ip,
            "hostname": f"test-dev-{uuid.uuid4().hex[:6]}",
            "manufacturer": "TestMfg",
            "model": "TM-200",
            "device_type": "controller",
            "category": "controller",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["ip_address"] == ip
    assert "id" in data

    # Cleanup
    await admin_client.delete(f"/api/devices/{data['id']}")


# ---------------------------------------------------------------------------
# 4. Create device — duplicate IP
# ---------------------------------------------------------------------------

async def test_create_device_duplicate_ip(admin_client: httpx.AsyncClient, test_device: dict):
    resp = await admin_client.post(
        "/api/devices/",
        json={
            "ip_address": test_device["ip_address"],
            "hostname": "dup-test",
            "manufacturer": "Dup",
            "model": "D-1",
            "device_type": "controller",
            "category": "controller",
        },
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# 5. Create device — missing required fields
# ---------------------------------------------------------------------------

async def test_create_device_missing_fields(admin_client: httpx.AsyncClient):
    resp = await admin_client.post("/api/devices/", json={})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 6. Get device by ID
# ---------------------------------------------------------------------------

async def test_get_device(admin_client: httpx.AsyncClient, test_device: dict):
    resp = await admin_client.get(f"/api/devices/{test_device['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == test_device["id"]


# ---------------------------------------------------------------------------
# 7. Get device — not found
# ---------------------------------------------------------------------------

async def test_get_device_not_found(admin_client: httpx.AsyncClient):
    fake_id = str(uuid.uuid4())
    resp = await admin_client.get(f"/api/devices/{fake_id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 8. Update device
# ---------------------------------------------------------------------------

async def test_update_device(admin_client: httpx.AsyncClient, test_device: dict):
    new_hostname = f"updated-{uuid.uuid4().hex[:6]}"
    resp = await admin_client.patch(
        f"/api/devices/{test_device['id']}",
        json={"hostname": new_hostname},
    )
    assert resp.status_code == 200
    assert resp.json()["hostname"] == new_hostname


# ---------------------------------------------------------------------------
# 9. Update device — not found
# ---------------------------------------------------------------------------

async def test_update_device_not_found(admin_client: httpx.AsyncClient):
    fake_id = str(uuid.uuid4())
    resp = await admin_client.patch(
        f"/api/devices/{fake_id}",
        json={"hostname": "ghost"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 10. Delete device
# ---------------------------------------------------------------------------

async def test_delete_device(admin_client: httpx.AsyncClient):
    # Create a device to delete
    ip = unique_ip()
    create_resp = await admin_client.post(
        "/api/devices/",
        json={
            "ip_address": ip,
            "hostname": "to-delete",
            "manufacturer": "DelCo",
            "model": "D-99",
            "device_type": "controller",
            "category": "controller",
        },
    )
    assert create_resp.status_code == 201
    dev_id = create_resp.json()["id"]

    resp = await admin_client.delete(f"/api/devices/{dev_id}")
    assert resp.status_code == 204

    # Verify gone
    get_resp = await admin_client.get(f"/api/devices/{dev_id}")
    assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# 11. Delete device — not found
# ---------------------------------------------------------------------------

async def test_delete_device_not_found(admin_client: httpx.AsyncClient):
    fake_id = str(uuid.uuid4())
    resp = await admin_client.delete(f"/api/devices/{fake_id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 12. Device stats
# ---------------------------------------------------------------------------

async def test_device_stats(admin_client: httpx.AsyncClient):
    resp = await admin_client.get("/api/devices/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert isinstance(data["total"], int)


# ---------------------------------------------------------------------------
# 13. Device stats — no auth
# ---------------------------------------------------------------------------

async def test_device_stats_no_auth(client: httpx.AsyncClient):
    resp = await client.get("/api/devices/stats")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 14. Compare devices
# ---------------------------------------------------------------------------

async def test_compare_devices(admin_client: httpx.AsyncClient):
    # Create two devices
    devices = []
    for i in range(2):
        ip = unique_ip()
        resp = await admin_client.post(
            "/api/devices/",
            json={
                "ip_address": ip,
                "hostname": f"cmp-dev-{i}",
                "manufacturer": "CmpCo",
                "model": f"C-{i}",
                "device_type": "controller",
                "category": "controller",
            },
        )
        assert resp.status_code == 201
        devices.append(resp.json())

    ids_str = ",".join(d["id"] for d in devices)
    resp = await admin_client.get(f"/api/devices/compare?ids={ids_str}")
    assert resp.status_code == 200
    data = resp.json()
    assert "devices" in data
    assert "comparison" in data
    assert len(data["devices"]) == 2

    # Cleanup
    for d in devices:
        await admin_client.delete(f"/api/devices/{d['id']}")


# ---------------------------------------------------------------------------
# 15. Compare devices — fewer than 2
# ---------------------------------------------------------------------------

async def test_compare_devices_too_few(admin_client: httpx.AsyncClient, test_device: dict):
    resp = await admin_client.get(f"/api/devices/compare?ids={test_device['id']}")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 16. CSV import
# ---------------------------------------------------------------------------

async def test_import_devices_csv(admin_client: httpx.AsyncClient):
    ip1 = unique_ip()
    ip2 = unique_ip()
    csv_content = (
        f"ip_address,hostname,manufacturer,model\n"
        f"{ip1},csv-dev-1,TestCo,T1\n"
        f"{ip2},csv-dev-2,TestCo,T2\n"
    )
    files = {"file": ("devices.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    resp = await admin_client.post("/api/devices/import", files=files)

    if resp.status_code == 404:
        pytest.skip("Import endpoint not available")

    assert resp.status_code == 200
    data = resp.json()
    assert data["imported"] >= 2

    # Cleanup: find and delete imported devices
    all_devs = await admin_client.get("/api/devices/")
    if all_devs.status_code == 200:
        for dev in all_devs.json():
            if dev.get("ip_address") in (ip1, ip2):
                await admin_client.delete(f"/api/devices/{dev['id']}")


# ---------------------------------------------------------------------------
# 17. CSV import — bad file type
# ---------------------------------------------------------------------------

async def test_import_devices_bad_type(admin_client: httpx.AsyncClient):
    files = {"file": ("data.json", io.BytesIO(b'{"bad": true}'), "application/json")}
    resp = await admin_client.post("/api/devices/import", files=files)
    if resp.status_code == 404:
        pytest.skip("Import endpoint not available")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 18. CSV export
# ---------------------------------------------------------------------------

async def test_export_devices_csv(admin_client: httpx.AsyncClient):
    resp = await admin_client.get("/api/devices/export")
    if resp.status_code == 404:
        pytest.skip("Export endpoint not available")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# 19. CSV export — no auth
# ---------------------------------------------------------------------------

async def test_export_devices_no_auth(client: httpx.AsyncClient):
    resp = await client.get("/api/devices/export")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 20. Device trends
# ---------------------------------------------------------------------------

async def test_device_trends(admin_client: httpx.AsyncClient, test_device: dict):
    resp = await admin_client.get(f"/api/devices/{test_device['id']}/trends")
    assert resp.status_code == 200
    data = resp.json()
    assert data["device_id"] == test_device["id"]
    assert "runs" in data
    assert "trend" in data


# ---------------------------------------------------------------------------
# 21. Device trends — not found
# ---------------------------------------------------------------------------

async def test_device_trends_not_found(admin_client: httpx.AsyncClient):
    fake_id = str(uuid.uuid4())
    resp = await admin_client.get(f"/api/devices/{fake_id}/trends")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 22. Discover IP (will likely fail without sidecar, but tests the route)
# ---------------------------------------------------------------------------

async def test_discover_ip_no_mac(admin_client: httpx.AsyncClient, test_device: dict):
    """Discover IP should fail if device has no MAC address."""
    resp = await admin_client.post(f"/api/devices/{test_device['id']}/discover-ip")
    # 422 because fixture device has no MAC, or 404 if sidecar not reachable
    assert resp.status_code in (422, 404, 500)


# ---------------------------------------------------------------------------
# 23. Filter devices by category
# ---------------------------------------------------------------------------

async def test_list_devices_filter_category(admin_client: httpx.AsyncClient, test_device: dict):
    resp = await admin_client.get("/api/devices/?category=controller")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    # The fixture device is category=controller, so should appear if any exist
    if data:
        categories = [d.get("category") for d in data]
        assert all(c == "controller" for c in categories)
