"""Integration tests for admin-only endpoints: /api/users/, /api/audit-logs/."""

import httpx
import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.api]


async def test_list_users_as_admin(admin_client: httpx.AsyncClient):
    """GET /api/users/ as admin returns 200."""
    resp = await admin_client.get("/api/users/")
    assert resp.status_code == 200
    body = resp.json()
    items = body if isinstance(body, list) else body.get("items", body.get("users", []))
    assert isinstance(items, list)
    assert len(items) >= 1  # At least the admin user


async def test_list_users_as_engineer(engineer_client: httpx.AsyncClient):
    """GET /api/users/ as engineer returns 403."""
    resp = await engineer_client.get("/api/users/")
    assert resp.status_code == 403


async def test_list_users_as_reviewer(reviewer_client: httpx.AsyncClient):
    """GET /api/users/ as reviewer returns 403."""
    resp = await reviewer_client.get("/api/users/")
    assert resp.status_code == 403


async def test_change_user_role(
    admin_client: httpx.AsyncClient,
    engineer_client: httpx.AsyncClient,
):
    """PATCH /api/users/{id} as admin can change a user's role."""
    users_resp = await admin_client.get("/api/users/")
    assert users_resp.status_code == 200
    body = users_resp.json()
    users = body if isinstance(body, list) else body.get("items", body.get("users", []))

    # Find any engineer user (the fixture creates one with a random name)
    engineer = next(
        (u for u in users if u.get("role") == "engineer"),
        None,
    )
    if not engineer:
        pytest.skip("No engineer user found in user list")

    user_id = engineer["id"]

    # Change role to reviewer
    resp = await admin_client.patch(
        f"/api/users/{user_id}",
        json={"role": "reviewer"},
    )
    assert resp.status_code == 200
    assert resp.json().get("role") == "reviewer"

    # Restore to engineer
    restore_resp = await admin_client.patch(
        f"/api/users/{user_id}",
        json={"role": "engineer"},
    )
    assert restore_resp.status_code == 200


async def test_audit_log(admin_client: httpx.AsyncClient):
    """GET /api/audit-logs/ as admin returns 200."""
    resp = await admin_client.get("/api/audit-logs/")
    assert resp.status_code == 200
    body = resp.json()
    items = body if isinstance(body, list) else body.get("items", body.get("logs", []))
    assert isinstance(items, list)


async def test_audit_log_as_engineer(engineer_client: httpx.AsyncClient):
    """GET /api/audit-logs/ as engineer returns 403."""
    resp = await engineer_client.get("/api/audit-logs/")
    assert resp.status_code == 403


async def test_audit_log_export(admin_client: httpx.AsyncClient):
    """GET /api/audit-logs/export as admin returns 200."""
    resp = await admin_client.get("/api/audit-logs/export")
    assert resp.status_code == 200


async def test_audit_compliance(admin_client: httpx.AsyncClient):
    """GET /api/audit-logs/compliance-summary as admin returns 200."""
    resp = await admin_client.get("/api/audit-logs/compliance-summary")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, dict)
