"""Batch scan aggregate status tests."""

import asyncio

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.device import Device
from app.models.network_scan import NetworkScan, NetworkScanStatus
from app.models.test_run import TestRun as RunModel, TestRunStatus as RunStatus
from app.models.test_template import TestTemplate as TemplateModel
from app.models.user import User
from app.routes.network_scan import (
    _monitor_batch,
    _monitor_tasks,
    _release_batch_scan_start,
    _reserve_batch_scan_start,
    _starting_scan_ids,
)
from .conftest import register_and_login


async def _get_user_id(db: AsyncSession, username: str) -> str:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one().id


async def _create_device(db: AsyncSession, ip_address: str) -> str:
    device = Device(ip_address=ip_address, category="unknown", status="discovered")
    db.add(device)
    await db.flush()
    await db.refresh(device)
    return device.id


async def _create_template(db: AsyncSession) -> str:
    template = TemplateModel(name="batch-status-template", test_ids=["U01"], version="1.0")
    db.add(template)
    await db.flush()
    await db.refresh(template)
    return template.id


async def _create_run(
    db: AsyncSession,
    *,
    engineer_id: str,
    device_id: str,
    template_id: str,
    status: RunStatus,
) -> str:
    run = RunModel(
        device_id=device_id,
        template_id=template_id,
        engineer_id=engineer_id,
        connection_scenario="test_lab",
        total_tests=1,
        status=status,
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)
    return run.id


async def _create_scan(db: AsyncSession, *, created_by: str, run_ids: list[str]) -> str:
    scan = NetworkScan(
        cidr="192.168.10.0/24",
        connection_scenario="test_lab",
        status=NetworkScanStatus.SCANNING,
        created_by=created_by,
        run_ids=run_ids,
    )
    db.add(scan)
    await db.flush()
    await db.refresh(scan)
    return scan.id


@pytest.mark.asyncio
async def test_monitor_batch_marks_manual_and_review_runs_complete(
    client: AsyncClient,
    db_session: AsyncSession,
    db_engine,
    monkeypatch: pytest.MonkeyPatch,
):
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("app.models.database.async_session", session_factory)
    await register_and_login(client, suffix="batchSettle", role="admin")
    user_id = await _get_user_id(db_session, "batchSettleuser")
    template_id = await _create_template(db_session)
    device_a = await _create_device(db_session, "10.10.0.11")
    device_b = await _create_device(db_session, "10.10.0.12")
    run_ids = [
        await _create_run(
            db_session,
            engineer_id=user_id,
            device_id=device_a,
            template_id=template_id,
            status=RunStatus.AWAITING_MANUAL,
        ),
        await _create_run(
            db_session,
            engineer_id=user_id,
            device_id=device_b,
            template_id=template_id,
            status=RunStatus.AWAITING_REVIEW,
        ),
    ]
    scan_id = await _create_scan(db_session, created_by=user_id, run_ids=run_ids)
    await db_session.commit()

    await _monitor_batch(scan_id, run_ids, [])

    db_session.expire_all()
    saved_scan = await db_session.get(NetworkScan, scan_id)
    assert saved_scan is not None
    assert saved_scan.status == NetworkScanStatus.COMPLETE
    assert saved_scan.completed_at is not None


@pytest.mark.asyncio
async def test_monitor_batch_keeps_scan_pending_when_any_run_is_active(
    client: AsyncClient,
    db_session: AsyncSession,
    db_engine,
    monkeypatch: pytest.MonkeyPatch,
):
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("app.models.database.async_session", session_factory)
    await register_and_login(client, suffix="batchPending", role="admin")
    user_id = await _get_user_id(db_session, "batchPendinguser")
    template_id = await _create_template(db_session)
    device_a = await _create_device(db_session, "10.10.1.11")
    device_b = await _create_device(db_session, "10.10.1.12")
    run_ids = [
        await _create_run(
            db_session,
            engineer_id=user_id,
            device_id=device_a,
            template_id=template_id,
            status=RunStatus.COMPLETED,
        ),
        await _create_run(
            db_session,
            engineer_id=user_id,
            device_id=device_b,
            template_id=template_id,
            status=RunStatus.RUNNING,
        ),
    ]
    scan_id = await _create_scan(db_session, created_by=user_id, run_ids=run_ids)
    await db_session.commit()

    await _monitor_batch(scan_id, run_ids, [])

    db_session.expire_all()
    saved_scan = await db_session.get(NetworkScan, scan_id)
    assert saved_scan is not None
    assert saved_scan.status == NetworkScanStatus.PENDING
    assert saved_scan.completed_at is None


@pytest.mark.asyncio
async def test_reserve_batch_scan_start_rejects_duplicate_start_while_starting():
    scan_id = "scan-starting"
    assert _reserve_batch_scan_start(scan_id) is True
    try:
        assert _reserve_batch_scan_start(scan_id) is False
        assert scan_id in _starting_scan_ids
    finally:
        _release_batch_scan_start(scan_id)


@pytest.mark.asyncio
async def test_reserve_batch_scan_start_rejects_duplicate_start_while_monitor_active():
    scan_id = "scan-active-monitor"
    task = asyncio.create_task(asyncio.sleep(0.1))
    _monitor_tasks[scan_id] = task
    try:
        assert _reserve_batch_scan_start(scan_id) is False
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        _monitor_tasks.pop(scan_id, None)
