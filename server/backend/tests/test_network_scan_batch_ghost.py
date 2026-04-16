"""Regression: batch scan must skip IPs that fail connectivity probe."""

import asyncio

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.network_scan import NetworkScan, NetworkScanStatus
from app.models.test_run import TestRun as RunModel
from app.models.test_template import TestTemplate as TemplateModel
from app.models.user import User

from .conftest import register_and_login


@pytest.mark.asyncio
async def test_start_batch_skips_unreachable_ip(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    headers = await register_and_login(client, suffix="ghostbatch", role="admin")
    user_result = await db_session.execute(select(User).where(User.username == "ghostbatchuser"))
    user_id = user_result.scalar_one().id

    template = TemplateModel(name="ghost-template", test_ids=["U01"], version="1.0", is_default=True)
    db_session.add(template)
    scan = NetworkScan(
        cidr="192.168.77.0/24",
        connection_scenario="test_lab",
        status=NetworkScanStatus.PENDING,
        created_by=user_id,
        devices_found=[
            {"ip": "192.168.77.10"},
            {"ip": "192.168.77.11"},
        ],
    )
    db_session.add(scan)
    await db_session.commit()
    scan_id = scan.id

    ghost_ip = "192.168.77.10"
    live_ip = "192.168.77.11"

    async def fake_probe(ip, *args, **kwargs):
        if ip == ghost_ip:
            return (False, "icmp_only_untrusted")
        return (True, "tcp:80")

    def fake_launch(run_id, test_plan_id=None):
        async def _noop():
            return None
        return asyncio.create_task(_noop())

    monkeypatch.setattr("app.routes.network_scan.probe_device_connectivity", fake_probe)
    monkeypatch.setattr("app.routes.network_scan.launch_test_run", fake_launch)

    resp = await client.post(
        "/api/v1/network-scan/start",
        json={
            "scan_id": scan_id,
            "device_ips": [ghost_ip, live_ip],
            "connection_scenario": "test_lab",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["skipped_unreachable"] == [ghost_ip]

    run_result = await db_session.execute(
        select(RunModel).where(RunModel.id.in_(body["run_ids"] or []))
    )
    runs = run_result.scalars().all()
    assert len(runs) == 1
