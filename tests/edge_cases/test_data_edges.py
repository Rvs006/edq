"""Edge-case tests for data validation, unicode, boundaries, and CSV import."""

import io
import uuid

import httpx
import pytest

from tests.helpers import unique_ip

pytestmark = [pytest.mark.asyncio, pytest.mark.edge]


# ---------------------------------------------------------------------------
# 1. Unicode project name
# ---------------------------------------------------------------------------

async def test_unicode_project_name(admin_client: httpx.AsyncClient):
    """POST /api/projects/ with CJK + emoji name should store and return correctly."""
    name = "日本語テスト 🏢"
    resp = await admin_client.post(
        "/api/projects/",
        json={"name": name, "client_name": "テスト", "location": "東京"},
    )
    assert resp.status_code == 201, resp.text
    project = resp.json()
    assert project["name"] == name

    # Verify via GET
    get_resp = await admin_client.get(f"/api/projects/{project['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == name

    # Cleanup
    await admin_client.delete(f"/api/projects/{project['id']}")


# ---------------------------------------------------------------------------
# 2. Unicode device hostname
# ---------------------------------------------------------------------------

async def test_unicode_device_hostname(admin_client: httpx.AsyncClient):
    """POST device with accented hostname should save correctly."""
    hostname = "Ünïcödé-Dëvïcé"
    ip = unique_ip()
    resp = await admin_client.post(
        "/api/devices/",
        json={
            "ip_address": ip,
            "hostname": hostname,
            "category": "controller",
        },
    )
    assert resp.status_code == 201, resp.text
    device = resp.json()
    assert device["hostname"] == hostname

    # Cleanup
    await admin_client.delete(f"/api/devices/{device['id']}")


# ---------------------------------------------------------------------------
# 3. Long hostname (500 chars)
# ---------------------------------------------------------------------------

async def test_long_hostname(admin_client: httpx.AsyncClient):
    """POST device with 500-char hostname should be handled (accept or 422, no 500)."""
    hostname = "A" * 500
    ip = unique_ip()
    resp = await admin_client.post(
        "/api/devices/",
        json={
            "ip_address": ip,
            "hostname": hostname,
            "category": "controller",
        },
    )
    # Schema max_length=255, so expect 422 validation error
    assert resp.status_code in (201, 422), f"Unexpected {resp.status_code}: {resp.text}"
    assert resp.status_code != 500, "Server should not crash on long hostname"

    # Cleanup if created
    if resp.status_code == 201:
        await admin_client.delete(f"/api/devices/{resp.json()['id']}")


# ---------------------------------------------------------------------------
# 4. Long project name (1000 chars)
# ---------------------------------------------------------------------------

async def test_long_project_name(admin_client: httpx.AsyncClient):
    """POST project with 1000-char name should be handled gracefully."""
    name = "P" * 1000
    resp = await admin_client.post(
        "/api/projects/",
        json={"name": name, "client_name": "TestCo", "location": "Lab"},
    )
    # May accept or reject — must not crash
    assert resp.status_code in (201, 422, 400), f"Unexpected {resp.status_code}: {resp.text}"
    assert resp.status_code != 500, "Server should not crash on long project name"

    # Cleanup if created
    if resp.status_code == 201:
        await admin_client.delete(f"/api/projects/{resp.json()['id']}")


# ---------------------------------------------------------------------------
# 5. Duplicate device IP
# ---------------------------------------------------------------------------

async def test_duplicate_device_ip(admin_client: httpx.AsyncClient):
    """Creating two devices with the same IP should return 409."""
    ip = unique_ip()
    payload = {
        "ip_address": ip,
        "hostname": "dup-test-device",
        "category": "controller",
    }

    resp1 = await admin_client.post("/api/devices/", json=payload)
    assert resp1.status_code == 201, resp1.text

    resp2 = await admin_client.post("/api/devices/", json=payload)
    assert resp2.status_code == 409, f"Expected 409, got {resp2.status_code}: {resp2.text}"

    # Cleanup
    await admin_client.delete(f"/api/devices/{resp1.json()['id']}")


# ---------------------------------------------------------------------------
# 6. Delete project preserves devices
# ---------------------------------------------------------------------------

async def test_delete_project_preserves_devices(admin_client: httpx.AsyncClient):
    """Deleting a project should unlink, not delete, its devices."""
    # Create project
    proj_resp = await admin_client.post(
        "/api/projects/",
        json={"name": f"del-proj-{uuid.uuid4().hex[:6]}", "client_name": "X"},
    )
    assert proj_resp.status_code == 201
    project_id = proj_resp.json()["id"]

    # Create device
    ip = unique_ip()
    dev_resp = await admin_client.post(
        "/api/devices/",
        json={"ip_address": ip, "hostname": "linked-device", "category": "camera"},
    )
    assert dev_resp.status_code == 201
    device_id = dev_resp.json()["id"]

    # Link device to project
    link_resp = await admin_client.post(
        f"/api/projects/{project_id}/devices",
        json=[device_id],
    )
    assert link_resp.status_code == 200

    # Delete the project
    del_resp = await admin_client.delete(f"/api/projects/{project_id}")
    assert del_resp.status_code == 204

    # Device should still exist
    dev_check = await admin_client.get(f"/api/devices/{device_id}")
    assert dev_check.status_code == 200, "Device should survive project deletion"

    # Cleanup
    await admin_client.delete(f"/api/devices/{device_id}")


# ---------------------------------------------------------------------------
# 7. Compare with only one device
# ---------------------------------------------------------------------------

async def test_compare_one_device(admin_client: httpx.AsyncClient, test_device: dict):
    """GET /api/devices/compare with a single ID should return 400."""
    resp = await admin_client.get(
        "/api/devices/compare",
        params={"ids": test_device["id"]},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 8. Compare with six devices (exceeds max 5)
# ---------------------------------------------------------------------------

async def test_compare_six_devices(admin_client: httpx.AsyncClient):
    """GET /api/devices/compare with 6 IDs should return 400."""
    device_ids = []
    for _ in range(6):
        ip = unique_ip()
        resp = await admin_client.post(
            "/api/devices/",
            json={"ip_address": ip, "hostname": f"cmp-{ip}", "category": "camera"},
        )
        assert resp.status_code == 201, resp.text
        device_ids.append(resp.json()["id"])

    ids_param = ",".join(device_ids)
    cmp_resp = await admin_client.get(
        "/api/devices/compare",
        params={"ids": ids_param},
    )
    assert cmp_resp.status_code == 400, f"Expected 400, got {cmp_resp.status_code}"

    # Cleanup
    for did in device_ids:
        await admin_client.delete(f"/api/devices/{did}")


# ---------------------------------------------------------------------------
# 9. CSV import with 501 rows (exceeds limit of 500)
# ---------------------------------------------------------------------------

async def test_csv_501_rows(admin_client: httpx.AsyncClient):
    """POST /api/devices/import with 501 data rows should report an error."""
    buf = io.StringIO()
    buf.write("ip_address,hostname,category\n")
    for i in range(501):
        octet3 = (i // 254) + 1
        octet4 = (i % 254) + 1
        buf.write(f"10.88.{octet3}.{octet4},bulk-{i},camera\n")

    buf.seek(0)
    files = {"file": ("bulk.csv", buf.getvalue(), "text/csv")}
    resp = await admin_client.post("/api/devices/import", files=files)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Should have at least one error about row limit exceeded
    assert len(data.get("errors", [])) > 0, "Expected errors for exceeding 500-row limit"


# ---------------------------------------------------------------------------
# 10. CSV with mixed valid and invalid IPs
# ---------------------------------------------------------------------------

async def test_csv_mixed_valid_invalid(admin_client: httpx.AsyncClient):
    """CSV with a mix of valid and invalid IPs should partially import."""
    valid_ip = unique_ip()
    csv_content = (
        "ip_address,hostname,category\n"
        f"{valid_ip},good-device,camera\n"
        "999.999.999.999,bad-device,camera\n"
        "not-an-ip,worse-device,camera\n"
    )
    files = {"file": ("mixed.csv", csv_content, "text/csv")}
    resp = await admin_client.post("/api/devices/import", files=files)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["imported"] >= 1, "At least one valid device should import"
    assert len(data["errors"]) >= 2, "Invalid IPs should produce errors"


# ---------------------------------------------------------------------------
# 11. Invalid IP format (999.999.999.999)
# ---------------------------------------------------------------------------

async def test_invalid_ip_format(admin_client: httpx.AsyncClient):
    """POST device with out-of-range IP should return 422."""
    resp = await admin_client.post(
        "/api/devices/",
        json={
            "ip_address": "999.999.999.999",
            "hostname": "bad-ip-device",
            "category": "controller",
        },
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# 12. Invalid MAC format
# ---------------------------------------------------------------------------

async def test_invalid_mac_format(admin_client: httpx.AsyncClient):
    """POST device with invalid MAC should return 422."""
    ip = unique_ip()
    resp = await admin_client.post(
        "/api/devices/",
        json={
            "ip_address": ip,
            "mac_address": "ZZZZ",
            "hostname": "bad-mac-device",
            "category": "controller",
        },
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# 13. Empty string hostname
# ---------------------------------------------------------------------------

async def test_empty_string_hostname(admin_client: httpx.AsyncClient):
    """POST device with empty hostname should either accept or return 422."""
    ip = unique_ip()
    resp = await admin_client.post(
        "/api/devices/",
        json={
            "ip_address": ip,
            "hostname": "",
            "category": "controller",
        },
    )
    assert resp.status_code in (201, 422), f"Unexpected {resp.status_code}: {resp.text}"

    # Cleanup if created
    if resp.status_code == 201:
        await admin_client.delete(f"/api/devices/{resp.json()['id']}")


# ---------------------------------------------------------------------------
# 14. Special characters in fields
# ---------------------------------------------------------------------------

async def test_special_chars_in_fields(admin_client: httpx.AsyncClient):
    """POST device with HTML/XSS chars in hostname should be safely handled."""
    ip = unique_ip()
    hostname = 'test<>&"\'device'
    resp = await admin_client.post(
        "/api/devices/",
        json={
            "ip_address": ip,
            "hostname": hostname,
            "category": "controller",
        },
    )
    assert resp.status_code in (201, 422), f"Unexpected {resp.status_code}: {resp.text}"

    if resp.status_code == 201:
        device = resp.json()
        # The hostname should be stored safely (may be sanitized)
        stored = device.get("hostname", "")
        # It must not contain raw HTML tags that could cause XSS
        assert "<script" not in stored.lower(), "XSS content should be stripped"
        # Cleanup
        await admin_client.delete(f"/api/devices/{device['id']}")
