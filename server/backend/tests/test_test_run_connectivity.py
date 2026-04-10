"""Connectivity gating tests for test-run start and resume flows."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.test_run import TestRun, TestRunStatus
from app.models.test_template import TestTemplate
from app.models.user import User
from .conftest import register_and_login


async def _get_user_id(db: AsyncSession, username: str) -> str:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one().id


async def _create_device(db: AsyncSession, ip_address: str = "10.0.0.77") -> str:
    device = Device(ip_address=ip_address, category="unknown", status="discovered")
    db.add(device)
    await db.flush()
    await db.refresh(device)
    return device.id


async def _create_template(db: AsyncSession) -> str:
    template = TestTemplate(name="connectivity-template", test_ids=["U01"], version="1.0")
    db.add(template)
    await db.flush()
    await db.refresh(template)
    return template.id


async def _create_run(
    db: AsyncSession,
    engineer_id: str,
    status: TestRunStatus = TestRunStatus.PENDING,
) -> str:
    device_id = await _create_device(db)
    template_id = await _create_template(db)
    run = TestRun(
        device_id=device_id,
        template_id=template_id,
        engineer_id=engineer_id,
        connection_scenario="direct",
        total_tests=1,
        status=status,
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)
    return run.id


@pytest.mark.asyncio
async def test_start_run_pauses_when_device_is_unreachable(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    headers = await register_and_login(client, suffix="startCable")
    user_id = await _get_user_id(db_session, "startCableuser")
    run_id = await _create_run(db_session, user_id, status=TestRunStatus.PENDING)
    await db_session.commit()

    launched: list[str] = []

    async def fake_probe(_ip: str, _ports=None):
        return (False, None)

    def fake_launch(run_id: str, test_plan_id: str | None = None):
        launched.append(run_id)
        return object()

    monkeypatch.setattr("app.routes.test_runs.probe_device_connectivity", fake_probe)
    monkeypatch.setattr("app.routes.test_runs.launch_test_run", fake_launch)

    resp = await client.post(f"/api/test-runs/{run_id}/start", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["status"] == TestRunStatus.PAUSED_CABLE.value
    assert launched == [run_id]

    db_session.expire_all()
    saved_run = await db_session.get(TestRun, run_id)
    assert saved_run is not None
    assert saved_run.status == TestRunStatus.PAUSED_CABLE


@pytest.mark.asyncio
async def test_resume_paused_cable_run_requires_device_reachability(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    headers = await register_and_login(client, suffix="resumeCable")
    user_id = await _get_user_id(db_session, "resumeCableuser")
    run_id = await _create_run(db_session, user_id, status=TestRunStatus.PAUSED_CABLE)
    await db_session.commit()

    async def fake_probe(_ip: str, _ports=None):
        return (False, None)

    monkeypatch.setattr("app.routes.test_runs.probe_device_connectivity", fake_probe)

    resp = await client.post(f"/api/test-runs/{run_id}/resume", headers=headers)

    assert resp.status_code == 409
    assert "still unreachable" in resp.json()["detail"]

    db_session.expire_all()
    saved_run = await db_session.get(TestRun, run_id)
    assert saved_run is not None
    assert saved_run.status == TestRunStatus.PAUSED_CABLE


@pytest.mark.asyncio
async def test_resume_paused_cable_run_succeeds_when_device_is_reachable(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    headers = await register_and_login(client, suffix="resumeOnline")
    user_id = await _get_user_id(db_session, "resumeOnlineuser")
    run_id = await _create_run(db_session, user_id, status=TestRunStatus.PAUSED_CABLE)
    await db_session.commit()

    async def fake_probe(_ip: str, _ports=None):
        return (True, "tcp:443")

    monkeypatch.setattr("app.routes.test_runs.probe_device_connectivity", fake_probe)

    resp = await client.post(f"/api/test-runs/{run_id}/resume", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["status"] == TestRunStatus.RUNNING.value

    db_session.expire_all()
    saved_run = await db_session.get(TestRun, run_id)
    assert saved_run is not None
    assert saved_run.status == TestRunStatus.RUNNING
