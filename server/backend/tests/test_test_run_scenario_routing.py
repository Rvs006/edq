"""Scenario routing tests for test run creation."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.test_run import TestRun as RunModel
from app.models.test_run import TestRunStatus as RunStatus
from .conftest import register_and_login


async def _create_device(db: AsyncSession) -> str:
    device = Device(ip_address=f"10.0.1.{int(uuid.uuid4().hex[:2], 16) % 200 + 10}", category="controller", status="discovered")
    db.add(device)
    await db.flush()
    await db.refresh(device)
    return device.id


async def _create_template(db: AsyncSession) -> str:
    from app.models.test_template import TestTemplate

    template = TestTemplate(
        name=f"scenario-routing-{uuid.uuid4().hex[:6]}",
        test_ids=["U01", "U03", "U04", "U05", "U09", "U20", "U26", "U28", "U29", "U34"],
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
    assert results["U05"]["tier"] == "guided_manual"
    assert results["U09"]["tier"] == "automatic"
    assert results["U20"]["tier"] == "guided_manual"
    assert results["U26"]["tier"] == "guided_manual"
    assert results["U28"]["tier"] == "automatic"
    assert results["U29"]["tier"] == "guided_manual"
    assert "U34" not in results


@pytest.mark.asyncio
async def test_lab_scenario_keeps_dhcp_and_ntp_synchronisation_automatic(
    client: AsyncClient,
    db_session: AsyncSession,
):
    headers = await register_and_login(client, suffix="scenarioLabNtp")
    device_id = await _create_device(db_session)
    template_id = await _create_template(db_session)
    await db_session.commit()

    run_resp = await client.post(
        "/api/v1/test-runs/",
        json={
            "device_id": device_id,
            "template_id": template_id,
            "connection_scenario": "test_lab",
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

    assert results["U26"]["tier"] == "automatic"
    assert results["U03"]["tier"] == "guided_manual"
    assert results["U04"]["tier"] == "automatic"
    assert results["U05"]["tier"] == "guided_manual"
    assert results["U09"]["tier"] == "automatic"
    assert results["U20"]["tier"] == "guided_manual"
    assert results["U28"]["tier"] == "automatic"
    assert results["U29"]["tier"] == "automatic"
    assert "U34" not in results


@pytest.mark.asyncio
async def test_select_network_interface_requires_waiting_status(
    client: AsyncClient,
    db_session: AsyncSession,
):
    headers = await register_and_login(client, suffix="selectIfacePending")
    device_id = await _create_device(db_session)
    template_id = await _create_template(db_session)
    await db_session.commit()

    run_resp = await client.post(
        "/api/v1/test-runs/",
        json={
            "device_id": device_id,
            "template_id": template_id,
            "connection_scenario": "direct",
        },
        headers=headers,
    )
    assert run_resp.status_code == 201, run_resp.text
    run_id = run_resp.json()["id"]

    iface_resp = await client.post(
        f"/api/v1/test-runs/{run_id}/network-interface",
        json={"interface": "Ethernet 2", "label": "Bench NIC"},
        headers=headers,
    )

    assert iface_resp.status_code == 400, iface_resp.text
    assert "Cannot select network interface" in iface_resp.json()["detail"]


@pytest.mark.asyncio
async def test_select_network_interface_stores_run_metadata(
    client: AsyncClient,
    db_session: AsyncSession,
):
    headers = await register_and_login(client, suffix="selectIface")
    device_id = await _create_device(db_session)
    template_id = await _create_template(db_session)
    await db_session.commit()

    run_resp = await client.post(
        "/api/v1/test-runs/",
        json={
            "device_id": device_id,
            "template_id": template_id,
            "connection_scenario": "direct",
        },
        headers=headers,
    )
    assert run_resp.status_code == 201, run_resp.text
    run_id = run_resp.json()["id"]

    run = await db_session.get(RunModel, run_id)
    assert run is not None
    run.status = RunStatus.SELECTING_INTERFACE
    run.run_metadata = {
        "interface_selection": {
            "required": True,
            "test_id": "U03",
            "reason": "Select the Ethernet interface connected to the device.",
        }
    }
    await db_session.commit()

    iface_resp = await client.post(
        f"/api/v1/test-runs/{run_id}/network-interface",
        json={"interface": "Ethernet 2", "label": "Bench NIC"},
        headers=headers,
    )

    assert iface_resp.status_code == 200, iface_resp.text
    metadata = iface_resp.json()["run_metadata"]
    assert metadata["network_interface"] == {"name": "Ethernet 2", "label": "Bench NIC"}
    assert "interface_selection" not in metadata
    assert iface_resp.json()["status"] == "running"


@pytest.mark.asyncio
async def test_cancel_clears_pending_interface_selection_metadata(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_kill_target(_target: str) -> dict[str, int]:
        return {"killed": 0}

    monkeypatch.setattr("app.services.tools_client.tools_client.kill_target", fake_kill_target)

    headers = await register_and_login(client, suffix="cancelIface")
    device_id = await _create_device(db_session)
    template_id = await _create_template(db_session)
    await db_session.commit()

    run_resp = await client.post(
        "/api/v1/test-runs/",
        json={
            "device_id": device_id,
            "template_id": template_id,
            "connection_scenario": "direct",
        },
        headers=headers,
    )
    assert run_resp.status_code == 201, run_resp.text
    run_id = run_resp.json()["id"]

    run = await db_session.get(RunModel, run_id)
    assert run is not None
    run.status = RunStatus.SELECTING_INTERFACE
    run.run_metadata = {
        "current_test": {"test_id": "U03", "status": "running"},
        "interface_selection": {
            "required": True,
            "test_id": "U03",
            "reason": "Select the Ethernet interface connected to the device.",
        },
    }
    await db_session.commit()

    cancel_resp = await client.post(
        f"/api/v1/test-runs/{run_id}/cancel",
        headers=headers,
    )

    assert cancel_resp.status_code == 200, cancel_resp.text

    detail_resp = await client.get(f"/api/v1/test-runs/{run_id}", headers=headers)
    assert detail_resp.status_code == 200, detail_resp.text
    body = detail_resp.json()
    assert body["status"] == "cancelled"
    assert "current_test" not in body["run_metadata"]
    assert "interface_selection" not in body["run_metadata"]
