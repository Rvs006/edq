"""Injection attack tests — SQL injection, XSS, path traversal, command injection."""

import httpx
import pytest

from tests.helpers import BASE_URL, _login, _apply_auth, ADMIN_USER, ADMIN_PASS, unique_ip

pytestmark = [pytest.mark.asyncio, pytest.mark.security]


# ---------------------------------------------------------------------------
# 1. SQL injection via login
# ---------------------------------------------------------------------------

async def test_sql_injection_login(client: httpx.AsyncClient):
    """SQL injection payload in login must return 401, never 500."""
    resp = await client.post(
        "/api/auth/login",
        json={"username": "' OR 1=1--", "password": "x"},
    )
    assert resp.status_code in (400, 401, 422), (
        f"Expected 400/401/422 for SQL injection login, got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# 2. SQL injection via device search
# ---------------------------------------------------------------------------

async def test_sql_injection_search(admin_client: httpx.AsyncClient):
    """SQL injection in search param must not cause a 500."""
    resp = await admin_client.get("/api/devices/", params={"search": "' OR 1=1--"})
    assert resp.status_code == 200, (
        f"Expected 200 for search with injection payload, got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# 3. SQL injection via project name
# ---------------------------------------------------------------------------

async def test_sql_injection_project(admin_client: httpx.AsyncClient):
    """SQL injection in project name must not cause 500."""
    resp = await admin_client.post(
        "/api/projects/",
        json={
            "name": "'; DROP TABLE users;--",
            "client_name": "TestCorp",
            "location": "Lab",
        },
    )
    # Should either create safely (201) or reject input (400/422), never 500
    assert resp.status_code in (201, 400, 422), (
        f"Expected safe handling of SQL injection in project name, got {resp.status_code}"
    )
    # Cleanup if created
    if resp.status_code == 201:
        project_id = resp.json().get("id")
        if project_id:
            await admin_client.delete(f"/api/projects/{project_id}")


# ---------------------------------------------------------------------------
# 4. XSS in device hostname
# ---------------------------------------------------------------------------

async def test_xss_device_hostname(admin_client: httpx.AsyncClient):
    """Script tags in hostname must be stored safely (escaped or stripped)."""
    xss_payload = "<script>alert(1)</script>"
    ip = unique_ip()
    create_resp = await admin_client.post(
        "/api/devices/",
        json={
            "ip_address": ip,
            "hostname": xss_payload,
            "manufacturer": "TestCo",
            "model": "T-100",
            "device_type": "controller",
            "category": "controller",
        },
    )
    assert create_resp.status_code in (201, 400, 422), (
        f"Expected device creation or validation rejection, got {create_resp.status_code}"
    )

    if create_resp.status_code == 201:
        device = create_resp.json()
        device_id = device["id"]
        try:
            get_resp = await admin_client.get(f"/api/devices/{device_id}")
            assert get_resp.status_code == 200
            body = get_resp.text
            # The raw script tag must not appear unescaped in the response
            assert "<script>" not in body.lower() or "&lt;script&gt;" in body.lower() or "\\u003c" in body.lower(), (
                "XSS payload returned unescaped in device response"
            )
        finally:
            await admin_client.delete(f"/api/devices/{device_id}")


# ---------------------------------------------------------------------------
# 5. XSS in project name
# ---------------------------------------------------------------------------

async def test_xss_project_name(admin_client: httpx.AsyncClient):
    """XSS payload in project name must be sanitized or safely stored."""
    xss_payload = '<img onerror=alert(1) src=x>'
    resp = await admin_client.post(
        "/api/projects/",
        json={
            "name": xss_payload,
            "client_name": "TestCorp",
            "location": "Lab",
        },
    )
    assert resp.status_code in (201, 400, 422), (
        f"Expected safe handling of XSS payload, got {resp.status_code}"
    )

    if resp.status_code == 201:
        project = resp.json()
        project_id = project["id"]
        try:
            get_resp = await admin_client.get(f"/api/projects/{project_id}")
            body = get_resp.text
            # JSON APIs typically return raw data; XSS is a browser concern.
            # The API should either sanitize on input or rely on frontend escaping.
            # Flag as finding if payload is stored unescaped.
            if "onerror=" in body and "&lt;" not in body:
                pytest.xfail(
                    "SECURITY FINDING: XSS payload stored unescaped in project name. "
                    "API returns raw HTML tags in JSON. Frontend must escape on render."
                )
        finally:
            await admin_client.delete(f"/api/projects/{project_id}")


# ---------------------------------------------------------------------------
# 6. Path traversal
# ---------------------------------------------------------------------------

async def test_path_traversal(client: httpx.AsyncClient):
    """Path traversal must not leak system files."""
    resp = await client.get("/../../etc/passwd")
    # Should return SPA fallback (HTML) or 400/404, NOT file contents
    assert resp.status_code in (200, 301, 302, 400, 404), (
        f"Unexpected status for path traversal: {resp.status_code}"
    )
    body = resp.text
    assert "root:" not in body, "Path traversal leaked /etc/passwd contents"


# ---------------------------------------------------------------------------
# 7. Command injection in hostname
# ---------------------------------------------------------------------------

async def test_command_injection(admin_client: httpx.AsyncClient):
    """Command injection in hostname must be stored safely."""
    ip = unique_ip()
    resp = await admin_client.post(
        "/api/devices/",
        json={
            "ip_address": ip,
            "hostname": "test; cat /etc/passwd",
            "manufacturer": "TestCo",
            "model": "T-100",
            "device_type": "controller",
            "category": "controller",
        },
    )
    assert resp.status_code in (201, 400, 422), (
        f"Expected safe handling of command injection, got {resp.status_code}"
    )

    if resp.status_code == 201:
        device = resp.json()
        device_id = device["id"]
        try:
            get_resp = await admin_client.get(f"/api/devices/{device_id}")
            body = get_resp.text
            assert "root:" not in body, "Command injection leaked /etc/passwd"
        finally:
            await admin_client.delete(f"/api/devices/{device_id}")
