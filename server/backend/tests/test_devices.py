"""Tests for device management routes."""

import io

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


@pytest.mark.asyncio
async def test_import_devices_csv_preserves_firmware_version(client: AsyncClient):
    """CSV imports should preserve firmware_version without dropping the first data row."""
    headers = await register_and_login(client, "devimportfw", role="admin")
    csv_content = (
        "ip_address,hostname,firmware_version,manufacturer,model\n"
        "192.168.55.10,fw-device,1.2.3,Axis,P3245-V\n"
        "192.168.55.11,fw-device-2,2.0.0,Axis,P3248-LV\n"
    )
    files = {"file": ("devices.csv", io.BytesIO(csv_content.encode()), "text/csv")}

    resp = await client.post("/api/devices/import", files=files, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["imported"] == 2

    listing = await client.get("/api/devices/", headers=headers)
    assert listing.status_code == 200
    imported = next(device for device in listing.json() if device["ip_address"] == "192.168.55.10")
    assert imported["firmware_version"] == "1.2.3"
    second = next(device for device in listing.json() if device["ip_address"] == "192.168.55.11")
    assert second["firmware_version"] == "2.0.0"


@pytest.mark.asyncio
async def test_discover_device_ip_uses_detected_networks(client: AsyncClient, monkeypatch):
    """DHCP IP discovery should scan detected/authorized networks, not just hard-coded defaults."""
    headers = await register_and_login(client, "devdiscoverdyn", role="admin")
    create_resp = await client.post("/api/devices/", json={
        "mac_address": "AA:BB:CC:DD:EE:FF",
        "hostname": "dhcp-device",
        "addressing_mode": "dhcp",
        "category": "camera",
    }, headers=headers)
    assert create_resp.status_code == 201
    device_id = create_resp.json()["id"]

    scanned_targets: list[str] = []

    async def fake_detect_networks():
        return {
            "interfaces": [
                {
                    "cidr": "10.42.0.0/24",
                    "sample_hosts": ["10.42.0.1"],
                    "reachable": True,
                }
            ],
            "host_ip": "10.42.0.5",
            "in_docker": False,
            "scan_recommendation": None,
            "debug": {},
        }

    async def fake_nmap(target: str, args=None, timeout: int = 300):
        scanned_targets.append(target)
        return {
            "stdout": (
                "Nmap scan report for 10.42.0.99\n"
                "Host is up (0.0010s latency).\n"
                "MAC Address: AA:BB:CC:DD:EE:FF (Example Vendor)\n"
            )
        }

    monkeypatch.setattr("app.routes.devices.tools_client.detect_networks", fake_detect_networks)
    monkeypatch.setattr("app.routes.devices.tools_client.nmap", fake_nmap)

    resp = await client.post(f"/api/devices/{device_id}/discover-ip", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ip_address"] == "10.42.0.99"
    assert scanned_targets[0] == "10.42.0.0/24"
    assert "192.168.1.0/24" not in scanned_targets


@pytest.mark.asyncio
async def test_discover_device_ip_populates_vendor_from_mac_lookup(client: AsyncClient, monkeypatch):
    headers = await register_and_login(client, "devdiscovervendor", role="admin")
    create_resp = await client.post("/api/devices/", json={
        "mac_address": "BC:6A:44:01:0A:96",
        "hostname": "commend-device",
        "addressing_mode": "dhcp",
        "category": "intercom",
    }, headers=headers)
    assert create_resp.status_code == 201
    device_id = create_resp.json()["id"]

    async def fake_detect_networks():
        return {
            "interfaces": [
                {
                    "cidr": "192.168.4.0/24",
                    "sample_hosts": ["192.168.4.1"],
                    "reachable": True,
                }
            ],
            "host_ip": "192.168.4.10",
            "in_docker": False,
            "scan_recommendation": None,
            "debug": {},
        }

    async def fake_nmap(target: str, args=None, timeout: int = 300):
        assert target == "192.168.4.0/24"
        return {
            "stdout": (
                "Nmap scan report for 192.168.4.66\n"
                "Host is up (0.0010s latency).\n"
                "MAC Address: BC:6A:44:01:0A:96\n"
            )
        }

    async def fake_mac_vendor(mac: str):
        assert mac == "BC:6A:44:01:0A:96"
        return {"vendor": "Commend International GmbH"}

    monkeypatch.setattr("app.services.device_ip_discovery.tools_client.detect_networks", fake_detect_networks)
    monkeypatch.setattr("app.services.device_ip_discovery.tools_client.nmap", fake_nmap)
    monkeypatch.setattr("app.services.mac_vendor.tools_client.mac_vendor", fake_mac_vendor)

    resp = await client.post(f"/api/devices/{device_id}/discover-ip", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ip_address"] == "192.168.4.66"
    assert resp.json()["manufacturer"] == "Commend International GmbH"
    assert resp.json()["oui_vendor"] == "Commend International GmbH"


@pytest.mark.asyncio
async def test_discover_device_ip_falls_back_to_neighbor_cache_when_nmap_has_no_mac(
    client: AsyncClient,
    monkeypatch,
):
    headers = await register_and_login(client, "devdiscoverneighbor", role="admin")
    create_resp = await client.post(
        "/api/devices/",
        json={
            "mac_address": "BA:EF:DD:5D:42:C0",
            "hostname": "docker-peer",
            "addressing_mode": "dhcp",
            "category": "intercom",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    device_id = create_resp.json()["id"]

    async def fake_detect_networks():
        return {
            "interfaces": [
                {
                    "cidr": "172.19.0.0/24",
                    "sample_hosts": ["172.19.0.1"],
                    "reachable": True,
                }
            ],
            "host_ip": "172.19.0.1",
            "in_docker": True,
            "scan_recommendation": None,
            "debug": {},
        }

    async def fake_nmap(target: str, args=None, timeout: int = 300):
        assert target == "172.19.0.0/24"
        return {
            "stdout": (
                "Nmap scan report for edq-frontend.edq_edq-frontend (172.19.0.3)\n"
                "Host is up (0.00066s latency).\n"
            )
        }

    async def fake_neighbors(subnet: str | None = None):
        assert subnet == "172.19.0.0/24"
        return {
            "entries": [
                {
                    "ip": "172.19.0.3",
                    "mac": "BA:EF:DD:5D:42:C0",
                    "state": "DELAY",
                    "vendor": None,
                }
            ]
        }

    monkeypatch.setattr("app.services.device_ip_discovery.tools_client.detect_networks", fake_detect_networks)
    monkeypatch.setattr("app.services.device_ip_discovery.tools_client.nmap", fake_nmap)
    monkeypatch.setattr("app.services.device_ip_discovery.tools_client.neighbors", fake_neighbors)

    resp = await client.post(f"/api/devices/{device_id}/discover-ip", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ip_address"] == "172.19.0.3"
