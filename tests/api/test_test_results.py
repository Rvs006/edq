"""Test Result endpoint tests — list, get, update verdict, reviewer override."""

import uuid

import httpx
import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.api]


async def _get_first_template_id(client: httpx.AsyncClient) -> str:
    """Fetch the first available test template ID."""
    resp = await client.get("/api/test-templates/")
    assert resp.status_code == 200
    data = resp.json()
    items = data if isinstance(data, list) else data.get("items", [])
    if not items:
        pytest.skip("No test templates available")
    return items[0]["id"]


async def _create_run_and_get_result(
    client: httpx.AsyncClient,
    device_id: str,
) -> tuple[str, str]:
    """Create a test run and return (run_id, first_result_id)."""
    template_id = await _get_first_template_id(client)
    run_resp = await client.post(
        "/api/test-runs/",
        json={"device_id": device_id, "template_id": template_id},
    )
    assert run_resp.status_code == 201
    run_id = run_resp.json()["id"]

    # List results for this run
    results_resp = await client.get(f"/api/test-results/?test_run_id={run_id}")
    assert results_resp.status_code == 200
    results = results_resp.json()
    if not results:
        pytest.skip("No test results generated for this template")
    return run_id, results[0]["id"]


# ---------------------------------------------------------------------------
# 1. List test results for a run
# ---------------------------------------------------------------------------

async def test_list_results_for_run(admin_client: httpx.AsyncClient, test_device: dict):
    run_id, _ = await _create_run_and_get_result(admin_client, test_device["id"])

    resp = await admin_client.get(f"/api/test-results/?test_run_id={run_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert all(r["test_run_id"] == run_id for r in data)


# ---------------------------------------------------------------------------
# 2. Get single test result
# ---------------------------------------------------------------------------

async def test_get_result(admin_client: httpx.AsyncClient, test_device: dict):
    _, result_id = await _create_run_and_get_result(admin_client, test_device["id"])

    resp = await admin_client.get(f"/api/test-results/{result_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == result_id


# ---------------------------------------------------------------------------
# 3. Get result — not found
# ---------------------------------------------------------------------------

async def test_get_result_not_found(admin_client: httpx.AsyncClient):
    fake_id = str(uuid.uuid4())
    resp = await admin_client.get(f"/api/test-results/{fake_id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 4. Update test result (engineer notes)
# ---------------------------------------------------------------------------

async def test_update_result_engineer_notes(admin_client: httpx.AsyncClient, test_device: dict):
    _, result_id = await _create_run_and_get_result(admin_client, test_device["id"])

    resp = await admin_client.patch(
        f"/api/test-results/{result_id}",
        json={"engineer_notes": "Checked manually, looks good."},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("engineer_notes") == "Checked manually, looks good."


# ---------------------------------------------------------------------------
# 5. Override test result (reviewer/admin only)
# ---------------------------------------------------------------------------

async def test_override_result(admin_client: httpx.AsyncClient, test_device: dict):
    _, result_id = await _create_run_and_get_result(admin_client, test_device["id"])

    resp = await admin_client.post(
        f"/api/test-results/{result_id}/override",
        json={
            "verdict": "pass",
            "override_reason": "Verified manually by admin during integration test.",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("override_verdict") == "pass" or data.get("verdict") == "pass"
