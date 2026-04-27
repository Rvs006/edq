"""Regression coverage for test-run aggregate payloads."""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.test_run import (
    TestRun as RunModel,
    TestRunStatus as RunStatus,
    TestRunVerdict as RunVerdict,
)
from app.models.test_template import TestTemplate as TemplateModel
from app.models.user import User
from .conftest import register_and_login


@pytest.mark.asyncio
async def test_test_run_stats_return_public_status_and_verdict_values(
    client: AsyncClient,
    db_session: AsyncSession,
):
    headers = await register_and_login(client, suffix="statsEnums")
    user_result = await db_session.execute(select(User).where(User.username == "statsEnumsuser"))
    engineer_id = user_result.scalar_one().id

    device = Device(ip_address="10.1.2.3", category="unknown", status="discovered")
    template = TemplateModel(name="stats-template", test_ids=["U01"], version="1.0")
    db_session.add_all([device, template])
    await db_session.flush()

    db_session.add(RunModel(
        device_id=device.id,
        template_id=template.id,
        engineer_id=engineer_id,
        connection_scenario="direct",
        total_tests=1,
        completed_tests=1,
        status=RunStatus.AWAITING_MANUAL,
        overall_verdict=RunVerdict.PASS,
        created_at=datetime.now(timezone.utc),
    ))
    await db_session.commit()

    resp = await client.get("/api/test-runs/stats", headers=headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["by_status"]["awaiting_manual"] == 1
    assert body["by_verdict"]["pass"] == 1
    assert not any(key.startswith("TestRunStatus.") for key in body["by_status"])
    assert not any(key.startswith("TestRunVerdict.") for key in body["by_verdict"])
