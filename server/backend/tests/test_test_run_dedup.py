"""Regression tests for deduplicated test IDs in run creation paths."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.network_scan import NetworkScan, NetworkScanStatus
from app.models.test_result import TestResult as ResultModel
from app.models.test_run import TestRun as RunModel
from app.models.test_template import TestTemplate as TemplateModel
from app.models.user import User

from .conftest import register_and_login


async def _get_user_id(db: AsyncSession, username: str) -> str:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one().id


@pytest.mark.asyncio
async def test_create_test_run_deduplicates_template_test_ids(
    client: AsyncClient,
    db_session: AsyncSession,
):
    headers = await register_and_login(client, suffix="runDedup", role="admin")
    user_id = await _get_user_id(db_session, "runDedupuser")

    device = Device(ip_address="10.0.2.10", category="unknown", status="discovered")
    db_session.add(device)
    await db_session.flush()
    await db_session.refresh(device)

    template = TemplateModel(
        name="run-dedup-template",
        test_ids='["U01", "U02", "U01", "U03", "U02"]',
        version="1.0",
        created_by=user_id,
    )
    db_session.add(template)
    await db_session.commit()

    resp = await client.post("/api/test-runs/", json={
        "device_id": device.id,
        "template_id": template.id,
        "connection_scenario": "direct",
    }, headers=headers)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["total_tests"] == 3

    run_id = body["id"]
    result_rows = await db_session.execute(
        select(ResultModel.test_id)
        .where(ResultModel.test_run_id == run_id)
        .order_by(ResultModel.created_at)
    )
    assert result_rows.scalars().all() == ["U01", "U02", "U03"]


@pytest.mark.asyncio
async def test_start_batch_deduplicates_requested_test_ids(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    headers = await register_and_login(client, suffix="batchDedup", role="admin")
    user_id = await _get_user_id(db_session, "batchDedupuser")

    template = TemplateModel(name="batch-dedup-template", test_ids=["U09"], version="1.0", is_default=True)
    db_session.add(template)
    scan = NetworkScan(
        cidr="192.168.88.0/24",
        connection_scenario="test_lab",
        status=NetworkScanStatus.PENDING,
        created_by=user_id,
        devices_found=[{"ip": "192.168.88.11"}],
    )
    db_session.add(scan)
    await db_session.commit()

    async def fake_probe(ip, *args, **kwargs):
        return (True, "tcp:443")

    def fake_launch(run_id, test_plan_id=None):
        return None

    monkeypatch.setattr("app.routes.network_scan.probe_device_connectivity", fake_probe)
    monkeypatch.setattr("app.routes.network_scan.launch_test_run", fake_launch)

    resp = await client.post(
        "/api/v1/network-scan/start",
        json={
            "scan_id": scan.id,
            "device_ips": ["192.168.88.11"],
            "test_ids": ["U01", "U02", "U01", "U03", "U02"],
            "connection_scenario": "test_lab",
        },
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["selected_test_ids"] == ["U01", "U02", "U03"]

    run_id = body["run_ids"][0]
    saved_run = await db_session.get(RunModel, run_id)
    assert saved_run is not None
    assert saved_run.total_tests == 3

    result_rows = await db_session.execute(
        select(ResultModel.test_id)
        .where(ResultModel.test_run_id == run_id)
        .order_by(ResultModel.created_at)
    )
    assert result_rows.scalars().all() == ["U01", "U02", "U03"]
