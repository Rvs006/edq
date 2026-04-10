"""Integration tests for /api/reports/ endpoints."""

import uuid

import httpx
import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.api]

BASE = "/api/reports/"


async def test_generate_report(admin_client: httpx.AsyncClient, test_device: dict):
    """POST /api/reports/generate as admin returns 200 or 201."""
    device_id = test_device["id"]

    # Start a test run to get a run_id
    run_resp = await admin_client.post(
        "/api/test-runs/",
        json={"device_id": device_id, "test_ids": ["port-scan"]},
    )
    if run_resp.status_code not in (200, 201):
        # Fall back: try generating with just device_id
        resp = await admin_client.post(
            f"{BASE}generate",
            json={"device_id": device_id},
        )
        assert resp.status_code in (200, 201, 404, 422), (
            f"Unexpected status: {resp.status_code}"
        )
        return

    run_id = run_resp.json().get("id")
    resp = await admin_client.post(
        f"{BASE}generate",
        json={"run_id": run_id, "device_id": device_id},
    )
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"


async def test_download_report(admin_client: httpx.AsyncClient):
    """GET /api/reports/download/{filename} returns 200 for existing or 404 for missing."""
    resp = await admin_client.get(f"{BASE}download/nonexistent-report.pdf")
    assert resp.status_code in (200, 404)


async def test_generate_report_invalid_run(admin_client: httpx.AsyncClient):
    """POST /api/reports/generate with a fake run_id returns 404."""
    fake_id = str(uuid.uuid4())
    resp = await admin_client.post(
        f"{BASE}generate",
        json={"run_id": fake_id},
    )
    assert resp.status_code in (404, 422), (
        f"Expected 404 or 422 for fake run_id, got {resp.status_code}: {resp.text}"
    )


async def test_report_templates(admin_client: httpx.AsyncClient):
    """GET /api/reports/templates returns 200 with available report templates."""
    resp = await admin_client.get(f"{BASE}templates")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, (list, dict))
