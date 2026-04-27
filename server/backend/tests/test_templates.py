"""Tests for test template management routes."""

import pytest
from httpx import AsyncClient

from .conftest import register_and_login


@pytest.mark.asyncio
async def test_list_templates(client: AsyncClient):
    """List templates returns a list."""
    headers = await register_and_login(client, "tpllist", role="admin")
    resp = await client.get("/api/test-templates/", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_create_template(client: AsyncClient):
    """Create a template and verify response."""
    headers = await register_and_login(client, "tplcreate", role="admin")
    resp = await client.post("/api/test-templates/", json={
        "name": "Camera Security Suite",
        "description": "Standard tests for IP cameras",
        "test_ids": ["U01", "U02", "U03"],
    }, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Camera Security Suite"
    assert data["test_ids"] == ["U01", "U02", "U03"]
    assert "id" in data


@pytest.mark.asyncio
async def test_create_template_deduplicates_test_ids_preserving_order(client: AsyncClient):
    headers = await register_and_login(client, "tpldedupecreate", role="admin")
    resp = await client.post("/api/test-templates/", json={
        "name": "Deduped Template",
        "test_ids": ["U03", "U01", "U03", "U02", "U01"],
    }, headers=headers)

    assert resp.status_code == 201
    assert resp.json()["test_ids"] == ["U03", "U01", "U02"]


@pytest.mark.asyncio
async def test_create_template_rejects_deprecated_or_unknown_test_ids(client: AsyncClient):
    headers = await register_and_login(client, "tplrejectdeprecated", role="admin")
    resp = await client.post("/api/test-templates/", json={
        "name": "Invalid Template",
        "test_ids": ["U01", "U36", "UX99"],
    }, headers=headers)

    assert resp.status_code == 422
    assert "U36" in resp.text
    assert "UX99" in resp.text


@pytest.mark.asyncio
async def test_get_template(client: AsyncClient):
    """Get a single template by ID."""
    headers = await register_and_login(client, "tplget", role="admin")
    create_resp = await client.post("/api/test-templates/", json={
        "name": "Get Test Template",
        "test_ids": ["U01"],
    }, headers=headers)
    template_id = create_resp.json()["id"]

    resp = await client.get(f"/api/test-templates/{template_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == template_id


@pytest.mark.asyncio
async def test_get_template_not_found(client: AsyncClient):
    """Getting a non-existent template returns 404."""
    headers = await register_and_login(client, "tplnotfound", role="admin")
    resp = await client.get("/api/test-templates/nonexistent-id", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_template(client: AsyncClient):
    """Update template fields."""
    headers = await register_and_login(client, "tplupdate", role="admin")
    create_resp = await client.post("/api/test-templates/", json={
        "name": "Before Update",
        "test_ids": ["U01"],
    }, headers=headers)
    template_id = create_resp.json()["id"]

    resp = await client.patch(f"/api/test-templates/{template_id}", json={
        "name": "After Update",
        "test_ids": ["U01", "U02", "U03", "U04"],
    }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "After Update"
    assert len(resp.json()["test_ids"]) == 4


@pytest.mark.asyncio
async def test_update_template_deduplicates_test_ids_preserving_order(client: AsyncClient):
    headers = await register_and_login(client, "tpldedupeupdate", role="admin")
    create_resp = await client.post("/api/test-templates/", json={
        "name": "Before Dedupe Update",
        "test_ids": ["U01"],
    }, headers=headers)
    template_id = create_resp.json()["id"]

    resp = await client.patch(f"/api/test-templates/{template_id}", json={
        "test_ids": ["U04", "U02", "U04", "U01", "U02"],
    }, headers=headers)

    assert resp.status_code == 200
    assert resp.json()["test_ids"] == ["U04", "U02", "U01"]


@pytest.mark.asyncio
async def test_delete_template(client: AsyncClient):
    """Soft-delete a template (sets is_active=False)."""
    headers = await register_and_login(client, "tpldelete", role="admin")
    create_resp = await client.post("/api/test-templates/", json={
        "name": "To Delete",
        "test_ids": ["U01"],
    }, headers=headers)
    template_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/test-templates/{template_id}", headers=headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_get_test_library(client: AsyncClient):
    """The test library endpoint returns universal tests."""
    headers = await register_and_login(client, "tpllib", role="admin")
    resp = await client.get("/api/test-templates/library", headers=headers)
    assert resp.status_code == 200
    library = resp.json()
    assert isinstance(library, list)
    assert len(library) > 0
    assert "test_id" in library[0]
    assert "name" in library[0]
    by_id = {test["test_id"]: test for test in library}
    assert by_id["U03"]["tier"] == "guided_manual"
    assert "U36" not in by_id
