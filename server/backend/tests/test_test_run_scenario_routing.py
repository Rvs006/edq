"""Scenario routing tests for test run creation."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.test_template import TestTemplate
from .conftest import register_and_login


async def _create_device(db: AsyncSession) -> str:
    device = Device(ip_address=f"10.0.1.{int(uuid.uuid4().hex[:2], 16) % 200 + 10}", category="controller", status="discovered")
    db.add(device)
    await db.flush()
    await db.refresh(device)
    return device.id


async def _create_template(db: AsyncSession) -> str:
    template = TestTemplate(
        name=f"scenario-routing-{uuid.uuid4().hex[:6]}",
        test_ids=["U01", "U03", "U04", "U26", "U29"],
        version="1.0",
    )
    db.add(template)
    await db.flush()
    await db.refresh(template)
    return template.id


@pytest.mark.asyncio
async def test_create_run_reclassifies_scenario_sensitive_tests_to_manual(
    client: AsyncClient,
    db_session: AsyncSession,
):
    headers = await register_and_login(client, suffix="scenarioRoute")
    device_id = await _create_device(db_session)
    template_id = await _create_template(db_session)
    await db_session.commit()

    run_resp = await client.post(
        "/api/v1/test-runs/",
        json={
            "device_id": device_id,
            "template_id": template_id,
            "connection_scenario": "site_network",
        },
        headers=headers,
    )
    assert run_resp.status_code == 201, run_resp.text
    run_id = run_resp.json()["id"]

    results_resp = await client.get(
        "/api/v1/test-results/",
        params={"test_run_id": run_id},
        headers=headers,
    )
    assert results_resp.status_code == 200, results_resp.text
    results = {item["test_id"]: item for item in results_resp.json()}

    assert results["U01"]["tier"] == "automatic"
    assert results["U03"]["tier"] == "guided_manual"
    assert results["U04"]["tier"] == "guided_manual"
    assert results["U26"]["tier"] == "guided_manual"
    assert results["U29"]["tier"] == "guided_manual"
