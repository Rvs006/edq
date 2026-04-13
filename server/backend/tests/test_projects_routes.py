"""Project route regression tests."""

import uuid

import pytest
from httpx import AsyncClient

from .conftest import register_and_login


@pytest.mark.asyncio
async def test_created_project_is_immediately_visible(client: AsyncClient):
    headers = await register_and_login(client, "projvisible", role="admin")
    create_resp = await client.post(
        "/api/projects/",
        json={
            "name": f"project-{uuid.uuid4().hex[:6]}",
            "client_name": "FixtureCorp",
            "location": "Lab A",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    project_id = create_resp.json()["id"]

    get_resp = await client.get(f"/api/projects/{project_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == project_id
