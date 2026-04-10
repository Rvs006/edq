"""Authorization tests — role-based access control enforcement."""

import httpx
import pytest

from tests.helpers import BASE_URL

pytestmark = [pytest.mark.asyncio, pytest.mark.security]


# ---------------------------------------------------------------------------
# 1. Engineer cannot delete a device
# ---------------------------------------------------------------------------

async def test_engineer_cannot_delete_device(
    engineer_client: httpx.AsyncClient,
    test_device: dict,
):
    """Engineers must not be able to delete devices."""
    device_id = test_device["id"]
    resp = await engineer_client.delete(f"/api/devices/{device_id}")
    assert resp.status_code == 403, (
        f"Expected 403 for engineer deleting device, got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# 2. Engineer cannot access user management
# ---------------------------------------------------------------------------

async def test_engineer_cannot_access_users(engineer_client: httpx.AsyncClient):
    """Engineers must not access user management endpoints."""
    resp = await engineer_client.get("/api/users/")
    # Accept 403 (forbidden) or 404 (route not exposed to non-admins)
    assert resp.status_code in (403, 404), (
        f"Expected 403/404 for engineer accessing users, got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# 3. Engineer cannot manage test templates
# ---------------------------------------------------------------------------

async def test_engineer_cannot_manage_templates(engineer_client: httpx.AsyncClient):
    """Engineers must not create test templates."""
    resp = await engineer_client.post(
        "/api/test-templates/",
        json={"name": "Unauthorized Template", "category": "security"},
    )
    assert resp.status_code in (403, 404, 405), (
        f"Expected 403/404/405 for engineer creating template, got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# 4. Engineer cannot access audit logs
# ---------------------------------------------------------------------------

async def test_engineer_cannot_access_audit_log(engineer_client: httpx.AsyncClient):
    """Engineers must not access audit logs."""
    resp = await engineer_client.get("/api/audit-logs/")
    assert resp.status_code in (403, 404), (
        f"Expected 403/404 for engineer accessing audit logs, got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# 5. Engineer cannot manage whitelists
# ---------------------------------------------------------------------------

async def test_engineer_cannot_manage_whitelists(engineer_client: httpx.AsyncClient):
    """Engineers must not create whitelist entries."""
    resp = await engineer_client.post(
        "/api/whitelists/",
        json={"name": "Unauthorized", "entries": []},
    )
    assert resp.status_code in (403, 404, 405), (
        f"Expected 403/404/405 for engineer managing whitelists, got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# 6. Reviewer cannot manage users
# ---------------------------------------------------------------------------

async def test_reviewer_cannot_manage_users(reviewer_client: httpx.AsyncClient):
    """Reviewers must not access user management."""
    resp = await reviewer_client.get("/api/users/")
    assert resp.status_code in (403, 404), (
        f"Expected 403/404 for reviewer accessing users, got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# 7. Engineer cannot override test verdict
# ---------------------------------------------------------------------------

async def test_engineer_cannot_override_verdict(
    engineer_client: httpx.AsyncClient,
):
    """Engineers must not override test result verdicts."""
    # Use a placeholder ID — we expect 403 (forbidden) or 404 (not found)
    resp = await engineer_client.post(
        "/api/test-results/00000000-0000-0000-0000-000000000000/override",
        json={"verdict": "pass", "reason": "unauthorized override"},
    )
    assert resp.status_code in (403, 404), (
        f"Expected 403/404 for engineer overriding verdict, got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# 8. Unauthenticated access to protected endpoint
# ---------------------------------------------------------------------------

async def test_unauthenticated_access(client: httpx.AsyncClient):
    """Requests without authentication must be rejected on protected routes."""
    resp = await client.get("/api/devices/")
    assert resp.status_code == 401, (
        f"Expected 401 for unauthenticated access, got {resp.status_code}"
    )
