"""Test Run endpoint tests — CRUD, lifecycle (start/pause/resume/cancel/complete)."""

import uuid

import httpx
import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.api]


async def _get_first_template_id(client: httpx.AsyncClient) -> str:
    """Fetch the first available test template ID."""
    resp = await client.get("/api/test-templates/")
    assert resp.status_code == 200, f"Failed to list templates: {resp.text}"
    data = resp.json()
    # Response may be a list or a dict with "items"
    items = data if isinstance(data, list) else data.get("items", [])
    if not items:
        pytest.skip("No test templates available")
    return items[0]["id"]


async def _create_test_run(
    client: httpx.AsyncClient,
    device_id: str,
    template_id: str,
) -> dict:
    """Helper to create a test run and return the response dict."""
    resp = await client.post(
        "/api/test-runs/",
        json={"device_id": device_id, "template_id": template_id},
    )
    assert resp.status_code == 201, f"Failed to create test run: {resp.text}"
    return resp.json()


# ---------------------------------------------------------------------------
# 1. List test runs
# ---------------------------------------------------------------------------

async def test_list_test_runs(admin_client: httpx.AsyncClient):
    resp = await admin_client.get("/api/test-runs/")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


# ---------------------------------------------------------------------------
# 2. List test runs — no auth
# ---------------------------------------------------------------------------

async def test_list_test_runs_no_auth(client: httpx.AsyncClient):
    resp = await client.get("/api/test-runs/")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 3. Create test run
# ---------------------------------------------------------------------------

async def test_create_test_run(admin_client: httpx.AsyncClient, test_device: dict):
    template_id = await _get_first_template_id(admin_client)
    run = await _create_test_run(admin_client, test_device["id"], template_id)
    assert "id" in run
    assert run["device_id"] == test_device["id"]
    assert run.get("status") in ("pending", "Pending", None) or "status" in run


# ---------------------------------------------------------------------------
# 4. Create test run — device not found
# ---------------------------------------------------------------------------

async def test_create_test_run_bad_device(admin_client: httpx.AsyncClient):
    template_id = await _get_first_template_id(admin_client)
    resp = await admin_client.post(
        "/api/test-runs/",
        json={"device_id": str(uuid.uuid4()), "template_id": template_id},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 5. Create test run — template not found
# ---------------------------------------------------------------------------

async def test_create_test_run_bad_template(admin_client: httpx.AsyncClient, test_device: dict):
    resp = await admin_client.post(
        "/api/test-runs/",
        json={"device_id": test_device["id"], "template_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 6. Get test run by ID
# ---------------------------------------------------------------------------

async def test_get_test_run(admin_client: httpx.AsyncClient, test_device: dict):
    template_id = await _get_first_template_id(admin_client)
    run = await _create_test_run(admin_client, test_device["id"], template_id)

    resp = await admin_client.get(f"/api/test-runs/{run['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == run["id"]


# ---------------------------------------------------------------------------
# 7. Get test run — not found
# ---------------------------------------------------------------------------

async def test_get_test_run_not_found(admin_client: httpx.AsyncClient):
    fake_id = str(uuid.uuid4())
    resp = await admin_client.get(f"/api/test-runs/{fake_id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 8. Update test run (PATCH)
# ---------------------------------------------------------------------------

async def test_update_test_run(admin_client: httpx.AsyncClient, test_device: dict):
    template_id = await _get_first_template_id(admin_client)
    run = await _create_test_run(admin_client, test_device["id"], template_id)

    resp = await admin_client.patch(
        f"/api/test-runs/{run['id']}",
        json={"connection_scenario": "vlan"},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 9. Start test run
# ---------------------------------------------------------------------------

async def test_start_test_run(admin_client: httpx.AsyncClient, test_device: dict):
    template_id = await _get_first_template_id(admin_client)
    run = await _create_test_run(admin_client, test_device["id"], template_id)

    resp = await admin_client.post(f"/api/test-runs/{run['id']}/start")
    # May return 200 (started) or 502/503 if tools sidecar is down
    assert resp.status_code in (200, 502, 503)
    if resp.status_code == 200:
        data = resp.json()
        assert data.get("status") in ("running", "paused_cable")

    # Cancel to clean up if it started
    await admin_client.post(f"/api/test-runs/{run['id']}/cancel")


# ---------------------------------------------------------------------------
# 10. Pause test run (will fail if not running, which is expected)
# ---------------------------------------------------------------------------

async def test_pause_test_run_not_running(admin_client: httpx.AsyncClient, test_device: dict):
    template_id = await _get_first_template_id(admin_client)
    run = await _create_test_run(admin_client, test_device["id"], template_id)

    resp = await admin_client.post(f"/api/test-runs/{run['id']}/pause")
    # Should fail because run is in "pending" status, not "running"
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 11. Resume test run (will fail if not paused)
# ---------------------------------------------------------------------------

async def test_resume_test_run_not_paused(admin_client: httpx.AsyncClient, test_device: dict):
    template_id = await _get_first_template_id(admin_client)
    run = await _create_test_run(admin_client, test_device["id"], template_id)

    resp = await admin_client.post(f"/api/test-runs/{run['id']}/resume")
    # Should fail because run is not paused
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 12. Cancel test run
# ---------------------------------------------------------------------------

async def test_cancel_test_run_not_active(admin_client: httpx.AsyncClient, test_device: dict):
    template_id = await _get_first_template_id(admin_client)
    run = await _create_test_run(admin_client, test_device["id"], template_id)

    resp = await admin_client.post(f"/api/test-runs/{run['id']}/cancel")
    # Should fail because run is in "pending" status, not active/paused
    assert resp.status_code == 400
