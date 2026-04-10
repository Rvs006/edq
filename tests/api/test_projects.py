"""Project endpoint tests — CRUD, device assignment."""

import uuid

import httpx
import pytest

from tests.helpers import unique_ip

pytestmark = [pytest.mark.asyncio, pytest.mark.api]


# ---------------------------------------------------------------------------
# 1. List projects
# ---------------------------------------------------------------------------

async def test_list_projects(admin_client: httpx.AsyncClient):
    resp = await admin_client.get("/api/projects/")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)
    assert "total" in data


# ---------------------------------------------------------------------------
# 2. List projects — no auth
# ---------------------------------------------------------------------------

async def test_list_projects_no_auth(client: httpx.AsyncClient):
    resp = await client.get("/api/projects/")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 3. Create project
# ---------------------------------------------------------------------------

async def test_create_project(admin_client: httpx.AsyncClient):
    name = f"proj-{uuid.uuid4().hex[:6]}"
    resp = await admin_client.post(
        "/api/projects/",
        json={"name": name, "client_name": "TestClient", "location": "Lab A"},
    )
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["name"] == name
    assert "id" in data

    # Cleanup
    await admin_client.delete(f"/api/projects/{data['id']}")


# ---------------------------------------------------------------------------
# 4. Create project — missing name
# ---------------------------------------------------------------------------

async def test_create_project_missing_name(admin_client: httpx.AsyncClient):
    resp = await admin_client.post("/api/projects/", json={"client_name": "X"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 5. Get project by ID
# ---------------------------------------------------------------------------

async def test_get_project(admin_client: httpx.AsyncClient, test_project: dict):
    resp = await admin_client.get(f"/api/projects/{test_project['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == test_project["id"]


# ---------------------------------------------------------------------------
# 6. Get project — not found
# ---------------------------------------------------------------------------

async def test_get_project_not_found(admin_client: httpx.AsyncClient):
    fake_id = str(uuid.uuid4())
    resp = await admin_client.get(f"/api/projects/{fake_id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 7. Update project
# ---------------------------------------------------------------------------

async def test_update_project(admin_client: httpx.AsyncClient, test_project: dict):
    new_name = f"updated-proj-{uuid.uuid4().hex[:4]}"
    resp = await admin_client.patch(
        f"/api/projects/{test_project['id']}",
        json={"name": new_name},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == new_name


# ---------------------------------------------------------------------------
# 8. Delete project
# ---------------------------------------------------------------------------

async def test_delete_project(admin_client: httpx.AsyncClient):
    # Create then delete
    create_resp = await admin_client.post(
        "/api/projects/",
        json={"name": f"del-proj-{uuid.uuid4().hex[:6]}"},
    )
    assert create_resp.status_code == 201
    proj_id = create_resp.json()["id"]

    resp = await admin_client.delete(f"/api/projects/{proj_id}")
    assert resp.status_code == 204

    # Verify gone
    get_resp = await admin_client.get(f"/api/projects/{proj_id}")
    assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# 9. Add devices to project
# ---------------------------------------------------------------------------

async def test_add_devices_to_project(
    admin_client: httpx.AsyncClient,
    test_project: dict,
    test_device: dict,
):
    resp = await admin_client.post(
        f"/api/projects/{test_project['id']}/devices",
        json=[test_device["id"]],
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["updated"] >= 1


# ---------------------------------------------------------------------------
# 10. Add devices to project — project not found
# ---------------------------------------------------------------------------

async def test_add_devices_to_nonexistent_project(
    admin_client: httpx.AsyncClient,
    test_device: dict,
):
    fake_id = str(uuid.uuid4())
    resp = await admin_client.post(
        f"/api/projects/{fake_id}/devices",
        json=[test_device["id"]],
    )
    assert resp.status_code == 404
