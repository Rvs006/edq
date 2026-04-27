"""Regression tests for test-result authorization and reviewer overrides."""

import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.test_result import (
    TestResult as ResultModel,
    TestTier as ResultTier,
    TestVerdict as ResultVerdict,
)
from app.models.test_run import TestRun as RunModel, TestRunStatus as RunStatus
from app.models.test_template import TestTemplate as TemplateModel
from app.models.user import User
from .conftest import register_and_login


async def _create_device(db: AsyncSession) -> str:
    device = Device(ip_address="10.0.0.55", category="unknown", status="discovered")
    db.add(device)
    await db.flush()
    await db.refresh(device)
    return device.id


async def _create_template(db: AsyncSession) -> str:
    template = TemplateModel(name="results-template", test_ids=["U01"], version="1.0")
    db.add(template)
    await db.flush()
    await db.refresh(template)
    return template.id


async def _get_user_id(db: AsyncSession, username: str) -> str:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one().id


async def _create_run_with_result(db: AsyncSession, engineer_id: str) -> tuple[str, str]:
    device_id = await _create_device(db)
    template_id = await _create_template(db)
    run = RunModel(
        device_id=device_id,
        template_id=template_id,
        engineer_id=engineer_id,
        connection_scenario="direct",
        total_tests=1,
        status=RunStatus.PENDING,
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)

    result = ResultModel(
        test_run_id=run.id,
        test_id="U01",
        test_name="Ping",
        tier=ResultTier.AUTOMATIC,
        tool="ping",
        verdict=ResultVerdict.PENDING,
        is_essential="yes",
        created_at=datetime.now(timezone.utc),
    )
    db.add(result)
    await db.flush()
    await db.refresh(result)
    return run.id, result.id


@pytest.mark.asyncio
async def test_engineer_cannot_access_other_engineer_results(
    client: AsyncClient,
    db_session: AsyncSession,
):
    await register_and_login(client, suffix="resultsOwner")
    owner_id = await _get_user_id(db_session, "resultsOwneruser")
    run_id, result_id = await _create_run_with_result(db_session, owner_id)
    await db_session.commit()

    attacker_headers = await register_and_login(client, suffix="resultsAttacker")

    scoped_list = await client.get(f"/api/test-results/?test_run_id={run_id}", headers=attacker_headers)
    assert scoped_list.status_code == 403

    unscoped_list = await client.get("/api/test-results/", headers=attacker_headers)
    assert unscoped_list.status_code == 200
    assert all(item["test_run_id"] != run_id for item in unscoped_list.json())

    get_resp = await client.get(f"/api/test-results/{result_id}", headers=attacker_headers)
    assert get_resp.status_code == 403

    patch_resp = await client.patch(
        f"/api/test-results/{result_id}",
        json={"comment": "malicious edit"},
        headers=attacker_headers,
    )
    assert patch_resp.status_code == 403


@pytest.mark.asyncio
async def test_batch_result_endpoint_not_writable(client: AsyncClient):
    headers = await register_and_login(client, suffix="resultsBatch")
    resp = await client.post("/api/test-results/batch", json=[], headers=headers)
    assert resp.status_code in {404, 405}


@pytest.mark.asyncio
async def test_reviewer_can_override_and_engineer_cannot(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner_headers = await register_and_login(client, suffix="overrideOwner")
    owner_id = await _get_user_id(db_session, "overrideOwneruser")
    _, result_id = await _create_run_with_result(db_session, owner_id)
    await db_session.commit()

    engineer_resp = await client.post(
        f"/api/test-results/{result_id}/override",
        json={"verdict": "fail", "override_reason": "Nope"},
        headers=owner_headers,
    )
    assert engineer_resp.status_code == 403

    reviewer_headers = await register_and_login(client, suffix="overrideReviewer", role="reviewer")
    reviewer_resp = await client.post(
        f"/api/test-results/{result_id}/override",
        json={"verdict": "fail", "override_reason": "Manual verification failed"},
        headers=reviewer_headers,
    )
    assert reviewer_resp.status_code == 200
    body = reviewer_resp.json()
    assert body["verdict"] == "fail"
    assert body["is_overridden"] is True
    assert body["override_reason"] == "Manual verification failed"
    assert body["overridden_by_username"]


@pytest.mark.asyncio
async def test_automatic_result_scanner_fields_are_read_only_on_update_route(
    client: AsyncClient,
    db_session: AsyncSession,
):
    headers = await register_and_login(client, suffix="autoReadOnly")
    owner_id = await _get_user_id(db_session, "autoReadOnlyuser")
    _, result_id = await _create_run_with_result(db_session, owner_id)
    await db_session.commit()

    blocked_resp = await client.patch(
        f"/api/test-results/{result_id}",
        json={
            "verdict": "pass",
            "raw_output": "forged scanner output",
            "parsed_data": {"reachable": True},
        },
        headers=headers,
    )
    assert blocked_resp.status_code == 400

    notes_resp = await client.patch(
        f"/api/test-results/{result_id}",
        json={"engineer_notes": "Observed during live validation."},
        headers=headers,
    )
    assert notes_resp.status_code == 200
    assert notes_resp.json()["engineer_notes"] == "Observed during live validation."


@pytest.mark.asyncio
async def test_manual_result_update_moves_run_to_completed_when_all_manual_items_done(
    client: AsyncClient,
    db_session: AsyncSession,
):
    suffix = f"manualDone{uuid.uuid4().hex[:6]}"
    headers = await register_and_login(client, suffix=suffix)
    engineer_id = await _get_user_id(db_session, f"{suffix}user")
    device_id = await _create_device(db_session)
    template = TemplateModel(name=f"{suffix}-template", test_ids=["U20"], version="1.0")
    db_session.add(template)
    await db_session.flush()
    await db_session.refresh(template)

    run = RunModel(
        device_id=device_id,
        template_id=template.id,
        engineer_id=engineer_id,
        connection_scenario="direct",
        total_tests=1,
        completed_tests=0,
        status=RunStatus.AWAITING_MANUAL,
    )
    db_session.add(run)
    await db_session.flush()
    await db_session.refresh(run)

    result = ResultModel(
        test_run_id=run.id,
        test_id="U20",
        test_name="Network Disconnection Behaviour",
        tier=ResultTier.GUIDED_MANUAL,
        tool=None,
        verdict=ResultVerdict.PENDING,
        is_essential="no",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(result)
    await db_session.commit()

    update_resp = await client.patch(
        f"/api/test-results/{result.id}",
        json={"verdict": "pass", "engineer_notes": "Recovered after reconnect."},
        headers=headers,
    )
    assert update_resp.status_code == 200, update_resp.text

    run_id = run.id
    complete_resp = await client.post(f"/api/test-runs/{run_id}/complete", headers=headers)
    assert complete_resp.status_code == 200, complete_resp.text
    body = complete_resp.json()
    assert body["status"] == "completed"
    assert body["overall_verdict"] == "pass"
    assert body["completed_tests"] == 1
    assert body["progress_pct"] == 100.0


@pytest.mark.asyncio
async def test_partial_manual_result_keeps_run_awaiting_manual_without_final_verdict(
    client: AsyncClient,
    db_session: AsyncSession,
):
    suffix = f"manualPartial{uuid.uuid4().hex[:6]}"
    headers = await register_and_login(client, suffix=suffix)
    engineer_id = await _get_user_id(db_session, f"{suffix}user")
    device_id = await _create_device(db_session)
    template = TemplateModel(name=f"{suffix}-template", test_ids=["U20", "U21"], version="1.0")
    db_session.add(template)
    await db_session.flush()
    await db_session.refresh(template)

    run = RunModel(
        device_id=device_id,
        template_id=template.id,
        engineer_id=engineer_id,
        connection_scenario="direct",
        total_tests=2,
        completed_tests=0,
        status=RunStatus.AWAITING_MANUAL,
    )
    db_session.add(run)
    await db_session.flush()
    await db_session.refresh(run)

    first = ResultModel(
        test_run_id=run.id,
        test_id="U20",
        test_name="Network Disconnection Behaviour",
        tier=ResultTier.GUIDED_MANUAL,
        tool=None,
        verdict=ResultVerdict.PENDING,
        is_essential="no",
        created_at=datetime.now(timezone.utc),
    )
    second = ResultModel(
        test_run_id=run.id,
        test_id="U21",
        test_name="Power Cycle Behaviour",
        tier=ResultTier.GUIDED_MANUAL,
        tool=None,
        verdict=ResultVerdict.PENDING,
        is_essential="no",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add_all([first, second])
    await db_session.commit()

    update_resp = await client.patch(
        f"/api/test-results/{first.id}",
        json={"verdict": "pass", "engineer_notes": "Recovered after reconnect."},
        headers=headers,
    )

    assert update_resp.status_code == 200, update_resp.text

    await db_session.refresh(run)
    assert run.status == RunStatus.AWAITING_MANUAL
    assert run.completed_at is None
    assert run.overall_verdict is None
    assert run.completed_tests == 1
    assert run.progress_pct == 50.0
    assert run.run_metadata["readiness_summary"]["level"] == "awaiting_manual_evidence"
