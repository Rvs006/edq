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
from app.services.test_selection import get_default_test_ids

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
            "test_ids": ["U03", "U01", "U03", "U02", "U01"],
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
    assert runs[0].total_tests == 3

    db_session.expire_all()
    saved_scan = await db_session.get(NetworkScan, scan_id)
    assert saved_scan is not None
    assert saved_scan.selected_test_ids == ["U03", "U01", "U02"]


@pytest.mark.asyncio
async def test_start_batch_returns_error_when_all_selected_ips_are_unreachable(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    headers = await register_and_login(client, suffix="ghostbatchall", role="admin")
    user_result = await db_session.execute(select(User).where(User.username == "ghostbatchalluser"))
    user_id = user_result.scalar_one().id

    template = TemplateModel(name="ghost-all-template", test_ids=["U01"], version="1.0", is_default=True)
    db_session.add(template)
    scan = NetworkScan(
        cidr="192.168.78.0/24",
        connection_scenario="test_lab",
        status=NetworkScanStatus.PENDING,
        created_by=user_id,
        devices_found=[{"ip": "192.168.78.10"}],
    )
    db_session.add(scan)
    await db_session.commit()
    scan_id = scan.id

    async def fake_probe(_ip, *args, **kwargs):
        return (False, "icmp_only_untrusted")

    def fail_launch(_run_id, test_plan_id=None):
        raise AssertionError("No test run should be launched when all selected IPs are unreachable")

    monkeypatch.setattr("app.routes.network_scan.probe_device_connectivity", fake_probe)
    monkeypatch.setattr("app.routes.network_scan.launch_test_run", fail_launch)

    resp = await client.post(
        "/api/v1/network-scan/start",
        json={
            "scan_id": scan_id,
            "device_ips": ["192.168.78.10"],
            "test_ids": ["U01"],
            "connection_scenario": "test_lab",
        },
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "error"
    assert body["run_ids"] == []
    assert body["skipped_unreachable"] == ["192.168.78.10"]
    assert "No selected devices were reachable" in body["error_message"]


@pytest.mark.asyncio
async def test_start_batch_rejects_explicit_empty_test_selection(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    headers = await register_and_login(client, suffix="batchempty", role="admin")
    user_result = await db_session.execute(select(User).where(User.username == "batchemptyuser"))
    user_id = user_result.scalar_one().id

    template = TemplateModel(name="empty-fallback-template", test_ids=["U01"], version="1.0", is_default=True)
    db_session.add(template)
    scan = NetworkScan(
        cidr="192.168.79.0/24",
        connection_scenario="test_lab",
        status=NetworkScanStatus.PENDING,
        created_by=user_id,
        devices_found=[{"ip": "192.168.79.10"}],
    )
    db_session.add(scan)
    await db_session.commit()
    scan_id = scan.id

    def fail_launch(_run_id, test_plan_id=None):
        raise AssertionError("No test run should launch for an empty explicit selection")

    monkeypatch.setattr("app.routes.network_scan.launch_test_run", fail_launch)

    resp = await client.post(
        "/api/v1/network-scan/start",
        json={
            "scan_id": scan_id,
            "device_ips": ["192.168.79.10"],
            "test_ids": [],
            "connection_scenario": "test_lab",
        },
        headers=headers,
    )

    assert resp.status_code == 422
    assert "Select at least one active test" in resp.text


@pytest.mark.asyncio
async def test_start_batch_without_selection_uses_full_default_template(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    headers = await register_and_login(client, suffix="batchdefault49", role="admin")
    user_result = await db_session.execute(select(User).where(User.username == "batchdefault49user"))
    user_id = user_result.scalar_one().id
    default_ids = get_default_test_ids()

    template = TemplateModel(name="default-full-suite-template", test_ids=default_ids, version="1.0", is_default=True)
    db_session.add(template)
    scan = NetworkScan(
        cidr="192.168.80.0/24",
        connection_scenario="test_lab",
        status=NetworkScanStatus.PENDING,
        created_by=user_id,
        devices_found=[{"ip": "192.168.80.10"}],
    )
    db_session.add(scan)
    await db_session.commit()
    scan_id = scan.id

    async def fake_probe(_ip, *args, **kwargs):
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
            "device_ips": ["192.168.80.10"],
            "connection_scenario": "test_lab",
        },
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    run_result = await db_session.execute(
        select(RunModel).where(RunModel.id.in_(body["run_ids"] or []))
    )
    runs = run_result.scalars().all()
    assert len(default_ids) == 49
    assert len(runs) == 1
    assert runs[0].total_tests == 49

    db_session.expire_all()
    saved_scan = await db_session.get(NetworkScan, scan_id)
    assert saved_scan is not None
    assert saved_scan.selected_test_ids == default_ids
