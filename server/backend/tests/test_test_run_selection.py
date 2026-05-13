import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.test_result import TestResult
from app.models.test_run import TestRun as RunModel
from app.models.test_template import TestTemplate as TemplateModel
from app.models.user import User
from app.services.test_selection import get_default_test_ids

from .conftest import register_and_login


async def _create_device(db: AsyncSession, ip_address: str = "192.168.90.10") -> str:
    device = Device(ip_address=ip_address, category="unknown", status="discovered")
    db.add(device)
    await db.flush()
    await db.refresh(device)
    return device.id


@pytest.mark.asyncio
async def test_create_test_run_accepts_explicit_selected_test_ids(
    client: AsyncClient,
    db_session: AsyncSession,
):
    headers = await register_and_login(client, "runselect", role="admin")
    device_id = await _create_device(db_session)
    template = TemplateModel(
        name="Full Selection Template",
        test_ids=get_default_test_ids(),
        version="1.0",
        is_default=True,
    )
    db_session.add(template)
    await db_session.commit()

    resp = await client.post(
        "/api/test-runs/",
        json={
            "device_id": device_id,
            "template_id": template.id,
            "selected_test_ids": ["U03", "U01", "U03", "U02"],
        },
        headers=headers,
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["total_tests"] == 3

    results = await db_session.execute(
        select(TestResult.test_id).where(TestResult.test_run_id == body["id"]).order_by(TestResult.test_id)
    )
    assert {row[0] for row in results.all()} == {"U01", "U02", "U03"}


@pytest.mark.asyncio
async def test_create_test_run_rejects_empty_or_deprecated_selected_test_ids(
    client: AsyncClient,
    db_session: AsyncSession,
):
    headers = await register_and_login(client, "runselectbad", role="admin")
    device_id = await _create_device(db_session, "192.168.90.11")
    template = TemplateModel(
        name="Reject Selection Template",
        test_ids=get_default_test_ids(),
        version="1.0",
        is_default=True,
    )
    db_session.add(template)
    await db_session.commit()

    empty_resp = await client.post(
        "/api/test-runs/",
        json={
            "device_id": device_id,
            "template_id": template.id,
            "selected_test_ids": [],
        },
        headers=headers,
    )
    assert empty_resp.status_code == 422
    assert "Select at least one active test" in empty_resp.text

    deprecated_resp = await client.post(
        "/api/test-runs/",
        json={
            "device_id": device_id,
            "template_id": template.id,
            "selected_test_ids": ["U01", "U36"],
        },
        headers=headers,
    )
    assert deprecated_resp.status_code == 422
    assert "U36" in deprecated_resp.text


@pytest.mark.asyncio
async def test_list_test_runs_hides_internal_template_runs_by_default(
    client: AsyncClient,
    db_session: AsyncSession,
):
    headers = await register_and_login(client, "runinternal", role="admin")
    user_result = await db_session.execute(select(User).where(User.username == "runinternaluser"))
    user_id = user_result.scalar_one().id
    device_id = await _create_device(db_session, "192.168.90.12")
    public_template = TemplateModel(name="Public Template", test_ids=["U01"], version="1.0")
    internal_template = TemplateModel(name="Codex Smoke Template", test_ids=["U01"], version="1.0")
    db_session.add_all([public_template, internal_template])
    await db_session.flush()

    public_run = RunModel(
        device_id=device_id,
        template_id=public_template.id,
        engineer_id=user_id,
        connection_scenario="direct",
        total_tests=1,
        status="pending",
    )
    internal_run = RunModel(
        device_id=device_id,
        template_id=internal_template.id,
        engineer_id=user_id,
        connection_scenario="direct",
        total_tests=1,
        status="pending",
    )
    db_session.add_all([public_run, internal_run])
    await db_session.commit()

    list_resp = await client.get("/api/test-runs/", headers=headers)
    assert list_resp.status_code == 200
    listed_ids = {item["id"] for item in list_resp.json()}
    assert public_run.id in listed_ids
    assert internal_run.id not in listed_ids

    internal_resp = await client.get("/api/test-runs/?include_internal=true", headers=headers)
    assert internal_resp.status_code == 200
    internal_ids = {item["id"] for item in internal_resp.json()}
    assert internal_run.id in internal_ids

    hidden_detail_resp = await client.get(f"/api/test-runs/{internal_run.id}", headers=headers)
    assert hidden_detail_resp.status_code == 404

    visible_detail_resp = await client.get(
        f"/api/test-runs/{internal_run.id}?include_internal=true",
        headers=headers,
    )
    assert visible_detail_resp.status_code == 200
    assert visible_detail_resp.json()["id"] == internal_run.id


@pytest.mark.asyncio
async def test_create_test_run_rejects_internal_template_without_admin_opt_in(
    client: AsyncClient,
    db_session: AsyncSession,
):
    headers = await register_and_login(client, "runinternalcreate", role="admin")
    device_id = await _create_device(db_session, "192.168.90.13")
    internal_template = TemplateModel(name="Goal Fixture Template", test_ids=["U01"], version="1.0")
    db_session.add(internal_template)
    await db_session.commit()

    hidden_resp = await client.post(
        "/api/test-runs/",
        json={
            "device_id": device_id,
            "template_id": internal_template.id,
        },
        headers=headers,
    )
    assert hidden_resp.status_code == 404

    visible_resp = await client.post(
        "/api/test-runs/?include_internal=true",
        json={
            "device_id": device_id,
            "template_id": internal_template.id,
        },
        headers=headers,
    )
    assert visible_resp.status_code == 201, visible_resp.text
    assert visible_resp.json()["template_id"] == internal_template.id
