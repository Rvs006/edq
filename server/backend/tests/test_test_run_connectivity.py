"""Connectivity gating tests for test-run start and resume flows."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from types import SimpleNamespace

from app.models.device import AddressingMode, Device
from app.models.test_run import TestRun as RunModel, TestRunStatus as RunStatus
from app.models.test_template import TestTemplate as TemplateModel
from app.models.user import User
from app.services.test_run_connectivity import ensure_device_execution_readiness
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
    template = TemplateModel(name="connectivity-template", test_ids=["U01"], version="1.0")
    db.add(template)
    await db.flush()
    await db.refresh(template)
    return template.id


async def _create_run(
    db: AsyncSession,
    engineer_id: str,
    status: RunStatus = RunStatus.PENDING,
) -> str:
    device_id = await _create_device(db)
    template_id = await _create_template(db)
    run = RunModel(
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
async def test_start_run_flags_paused_when_device_is_unreachable(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    headers = await register_and_login(client, suffix="startCable", role="admin")
    user_id = await _get_user_id(db_session, "startCableuser")
    run_id = await _create_run(db_session, user_id, status=RunStatus.PENDING)
    await db_session.commit()

    launched: list[str] = []

    async def fake_probe(_ip: str, _ports=None, **_kwargs):
        return (False, None)

    def fake_launch(run_id: str, test_plan_id: str | None = None):
        launched.append(run_id)
        return object()

    monkeypatch.setattr("app.services.test_run_connectivity.probe_device_connectivity", fake_probe)
    monkeypatch.setattr("app.routes.test_runs.launch_test_run", fake_launch)

    resp = await client.post(f"/api/test-runs/{run_id}/start", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == RunStatus.PAUSED_CABLE.value
    assert body["connectivity"]["reason"] == "unreachable"
    assert body["connectivity"]["can_execute"] is False
    assert launched == [run_id]

    db_session.expire_all()
    saved_run = await db_session.get(RunModel, run_id)
    assert saved_run is not None
    assert saved_run.status == RunStatus.PAUSED_CABLE


@pytest.mark.asyncio
async def test_start_run_rejects_unauthorized_engineer_target(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    headers = await register_and_login(client, suffix="startUnauthorized")
    user_id = await _get_user_id(db_session, "startUnauthorizeduser")
    run_id = await _create_run(db_session, user_id, status=RunStatus.PENDING)
    await db_session.commit()

    async def fake_readiness(_db, _device, logger=None):
        return SimpleNamespace(missing_ip=False, dhcp_missing_ip=False)

    def fail_launch(_run_id: str, test_plan_id: str | None = None):
        raise AssertionError("Unauthorized target must not launch")

    monkeypatch.setattr("app.routes.test_runs.ensure_device_execution_readiness", fake_readiness)
    monkeypatch.setattr("app.routes.test_runs.launch_test_run", fail_launch)

    resp = await client.post(f"/api/test-runs/{run_id}/start", headers=headers)

    assert resp.status_code == 403
    assert "not authorized" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_run_deduplicates_template_test_ids_preserving_order(
    client: AsyncClient,
    db_session: AsyncSession,
):
    headers = await register_and_login(client, suffix="createRunDedup")
    user_id = await _get_user_id(db_session, "createRunDedupuser")
    device_id = await _create_device(db_session)
    template = TemplateModel(
        name="dedupe-connectivity-template",
        test_ids=["U03", "U01", "U03", "U02", "U01"],
        version="1.0",
    )
    db_session.add(template)
    await db_session.flush()
    await db_session.refresh(template)
    await db_session.commit()

    resp = await client.post(
        "/api/test-runs/",
        json={
            "device_id": device_id,
            "template_id": template.id,
            "connection_scenario": "direct",
        },
        headers=headers,
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["engineer_id"] == user_id
    assert resp.json()["total_tests"] == 3

    result = await db_session.execute(
        select(RunModel).where(RunModel.id == resp.json()["id"])
    )
    run = result.scalar_one()
    assert run.total_tests == 3


@pytest.mark.asyncio
async def test_resume_paused_cable_run_requires_device_reachability(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    headers = await register_and_login(client, suffix="resumeCable")
    user_id = await _get_user_id(db_session, "resumeCableuser")
    run_id = await _create_run(db_session, user_id, status=RunStatus.PAUSED_CABLE)
    await db_session.commit()

    async def fake_probe(_ip: str, _ports=None, **_kwargs):
        return (False, None)

    class DummyHandler:
        def update_target(
            self,
            ip: str,
            probe_ports: list[int] | None = None,
            known_service_ports: list[int] | None = None,
        ) -> None:
            return None

        async def resume(self) -> None:
            raise AssertionError("resume() should not be called while the device is still unreachable")

    monkeypatch.setattr("app.services.test_run_connectivity.probe_device_connectivity", fake_probe)
    monkeypatch.setattr("app.routes.test_runs.get_cable_handler", lambda _run_id: DummyHandler())
    monkeypatch.setattr("app.routes.test_runs.is_run_executing", lambda _run_id: True)

    resp = await client.post(f"/api/test-runs/{run_id}/resume", headers=headers)

    assert resp.status_code == 409
    assert "still unreachable" in resp.json()["detail"]

    db_session.expire_all()
    saved_run = await db_session.get(RunModel, run_id)
    assert saved_run is not None
    assert saved_run.status == RunStatus.PAUSED_CABLE


@pytest.mark.asyncio
async def test_resume_paused_cable_run_succeeds_when_device_is_reachable(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    headers = await register_and_login(client, suffix="resumeOnline")
    user_id = await _get_user_id(db_session, "resumeOnlineuser")
    run_id = await _create_run(db_session, user_id, status=RunStatus.PAUSED_CABLE)
    await db_session.commit()

    async def fake_probe(_ip: str, _ports=None, **_kwargs):
        return (True, "tcp:443")

    launched: list[str] = []

    def fake_launch(run_id: str, test_plan_id: str | None = None):
        launched.append(run_id)
        return object()

    monkeypatch.setattr("app.services.test_run_connectivity.probe_device_connectivity", fake_probe)
    monkeypatch.setattr("app.routes.test_runs.get_cable_handler", lambda _run_id: None)
    monkeypatch.setattr("app.routes.test_runs.is_run_executing", lambda _run_id: False)
    monkeypatch.setattr("app.routes.test_runs.launch_test_run", fake_launch)

    resp = await client.post(f"/api/test-runs/{run_id}/resume", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["status"] == RunStatus.RUNNING.value
    assert launched == [run_id]

    db_session.expire_all()
    saved_run = await db_session.get(RunModel, run_id)
    assert saved_run is not None
    assert saved_run.status == RunStatus.RUNNING


@pytest.mark.asyncio
async def test_resume_paused_cable_run_uses_live_handler_fast_path(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    headers = await register_and_login(client, suffix="resumeLiveHandler")
    user_id = await _get_user_id(db_session, "resumeLiveHandleruser")
    run_id = await _create_run(db_session, user_id, status=RunStatus.PAUSED_CABLE)
    await db_session.commit()

    class DummyHandler:
        def __init__(self):
            self.resume_calls = 0
            self.updated_targets: list[tuple[str, list[int] | None]] = []

        def update_target(
            self,
            ip: str,
            probe_ports: list[int] | None = None,
            known_service_ports: list[int] | None = None,
        ) -> None:
            self.updated_targets.append((ip, probe_ports, known_service_ports))

        async def resume(self) -> None:
            self.resume_calls += 1

    handler = DummyHandler()
    launched: list[str] = []

    async def fake_probe(_ip: str, _ports=None, **_kwargs):
        return (True, "tcp:443")

    def fake_launch(run_id: str, test_plan_id: str | None = None):
        launched.append(run_id)
        return object()

    monkeypatch.setattr("app.services.test_run_connectivity.probe_device_connectivity", fake_probe)
    monkeypatch.setattr("app.routes.test_runs.get_cable_handler", lambda _run_id: handler)
    monkeypatch.setattr("app.routes.test_runs.is_run_executing", lambda _run_id: True)
    monkeypatch.setattr("app.routes.test_runs.launch_test_run", fake_launch)

    resp = await client.post(f"/api/test-runs/{run_id}/resume", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["status"] == RunStatus.RUNNING.value
    assert launched == []
    assert handler.resume_calls == 1
    assert handler.updated_targets
    assert handler.updated_targets[0][2] == []


@pytest.mark.asyncio
async def test_ensure_device_execution_readiness_refreshes_dhcp_stale_ip(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    device = Device(
        ip_address="192.168.1.20",
        mac_address="BC:6A:44:01:0A:96",
        addressing_mode=AddressingMode.DHCP,
        open_ports=[{"port": 443}],
        category="unknown",
        status="discovered",
    )
    db_session.add(device)
    await db_session.flush()
    await db_session.refresh(device)

    probe_calls: list[str] = []

    async def fake_probe(ip: str, _ports=None, **_kwargs):
        probe_calls.append(ip)
        if ip == "192.168.1.20":
            return (False, None)
        if ip == "192.168.1.44":
            return (True, "tcp:443")
        raise AssertionError(f"Unexpected IP probe: {ip}")

    async def fake_discover_ip(_db, mac_address: str):
        from app.services.device_ip_discovery import DeviceIpDiscoveryResult

        assert mac_address == "BC:6A:44:01:0A:96"
        return DeviceIpDiscoveryResult(
            discovered_ip="192.168.1.44",
            vendor="Commend International GmbH",
            scanned_subnets=["192.168.1.0/24"],
            successful_scans=1,
        )

    monkeypatch.setattr("app.services.test_run_connectivity.probe_device_connectivity", fake_probe)
    monkeypatch.setattr("app.services.test_run_connectivity.discover_ip_for_mac", fake_discover_ip)

    readiness = await ensure_device_execution_readiness(db_session, device)

    assert readiness.can_execute is True
    assert readiness.reason == "ready"
    assert probe_calls == ["192.168.1.20", "192.168.1.44"]
    assert device.ip_address == "192.168.1.44"


@pytest.mark.asyncio
async def test_ensure_device_execution_readiness_accepts_icmp_only_during_runs(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    device = Device(
        ip_address="192.168.4.64",
        category="unknown",
        status="discovered",
    )
    db_session.add(device)
    await db_session.flush()
    await db_session.refresh(device)

    async def fake_probe(ip: str, _ports=None, **kwargs):
        assert ip == "192.168.4.64"
        assert kwargs.get("trust_icmp_only") is True
        return (True, "icmp")

    monkeypatch.setattr("app.services.test_run_connectivity.probe_device_connectivity", fake_probe)

    readiness = await ensure_device_execution_readiness(db_session, device)

    assert readiness.can_execute is True
    assert readiness.reason == "ready"
    assert readiness.has_tcp_service is False
    assert readiness.known_probe_ports == []


@pytest.mark.asyncio
async def test_ensure_device_execution_readiness_requires_tcp_for_known_service_ports(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    device = Device(
        ip_address="192.168.4.64",
        open_ports=[{"port": 443}],
        category="unknown",
        status="discovered",
    )
    db_session.add(device)
    await db_session.flush()
    await db_session.refresh(device)

    async def fake_probe(ip: str, _ports=None, **kwargs):
        assert ip == "192.168.4.64"
        assert kwargs.get("trust_icmp_only") is True
        return (True, "tcp_refused:443")

    monkeypatch.setattr("app.services.test_run_connectivity.probe_device_connectivity", fake_probe)

    readiness = await ensure_device_execution_readiness(db_session, device)

    assert readiness.can_execute is False
    assert readiness.reason == "service_unreachable"
    assert readiness.reachable is True
    assert readiness.has_tcp_service is False
    assert readiness.known_probe_ports == [443]


@pytest.mark.asyncio
async def test_start_run_discovers_ip_for_dhcp_device_before_launch(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    headers = await register_and_login(client, suffix="startDhcp", role="admin")
    user_id = await _get_user_id(db_session, "startDhcpuser")
    device = Device(
        ip_address=None,
        mac_address="BC:6A:44:01:0A:96",
        addressing_mode=AddressingMode.DHCP,
        category="unknown",
        status="discovered",
    )
    db_session.add(device)
    await db_session.flush()
    await db_session.refresh(device)
    template_id = await _create_template(db_session)
    run = RunModel(
        device_id=device.id,
        template_id=template_id,
        engineer_id=user_id,
        connection_scenario="direct",
        total_tests=1,
        status=RunStatus.PENDING,
    )
    db_session.add(run)
    await db_session.flush()
    await db_session.refresh(run)
    await db_session.commit()

    launched: list[str] = []

    async def fake_discover_ip(_db, mac_address: str):
        from app.services.device_ip_discovery import DeviceIpDiscoveryResult
        assert mac_address == "BC:6A:44:01:0A:96"
        return DeviceIpDiscoveryResult(
            discovered_ip="192.168.4.66",
            vendor="Commend International GmbH",
            scanned_subnets=["192.168.4.0/24"],
            successful_scans=1,
        )

    async def fake_probe(_ip: str, _ports=None, **_kwargs):
        return (True, "tcp:443")

    def fake_launch(run_id: str, test_plan_id: str | None = None):
        launched.append(run_id)
        return object()

    monkeypatch.setattr("app.services.test_run_connectivity.discover_ip_for_mac", fake_discover_ip)
    monkeypatch.setattr("app.services.test_run_connectivity.probe_device_connectivity", fake_probe)
    monkeypatch.setattr("app.routes.test_runs.launch_test_run", fake_launch)

    resp = await client.post(f"/api/test-runs/{run.id}/start", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["status"] == "running"
    assert launched == [run.id]

    device_id = device.id
    db_session.expire_all()
    saved_device = await db_session.get(Device, device_id)
    assert saved_device is not None
    assert saved_device.ip_address == "192.168.4.66"
    assert saved_device.manufacturer == "Commend International GmbH"


@pytest.mark.asyncio
async def test_start_run_discovers_ip_from_neighbor_cache_for_dhcp_device(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    headers = await register_and_login(client, suffix="startDhcpNeighbor", role="admin")
    user_id = await _get_user_id(db_session, "startDhcpNeighboruser")
    device = Device(
        ip_address=None,
        mac_address="12:4C:56:CE:BE:DC",
        addressing_mode=AddressingMode.DHCP,
        category="unknown",
        status="discovered",
    )
    db_session.add(device)
    await db_session.flush()
    await db_session.refresh(device)
    template_id = await _create_template(db_session)
    run = RunModel(
        device_id=device.id,
        template_id=template_id,
        engineer_id=user_id,
        connection_scenario="direct",
        total_tests=1,
        status=RunStatus.PENDING,
    )
    db_session.add(run)
    await db_session.flush()
    await db_session.refresh(run)
    await db_session.commit()

    launched: list[str] = []

    async def fake_detect_networks():
        return {
            "interfaces": [
                {
                    "cidr": "172.19.0.0/24",
                    "sample_hosts": ["172.19.0.1"],
                    "reachable": True,
                }
            ],
            "host_ip": "172.19.0.1",
            "in_docker": True,
            "scan_recommendation": None,
            "debug": {},
        }

    async def fake_nmap(target: str, args=None, timeout: int = 300):
        raise AssertionError(f"nmap should not run when neighbor cache already resolves {target}")

    async def fake_neighbors(subnet: str | None = None):
        assert subnet == "172.19.0.0/24"
        return {
            "entries": [
                {
                    "ip": "172.19.0.3",
                    "mac": "12:4C:56:CE:BE:DC",
                    "state": "REACHABLE",
                    "vendor": None,
                }
            ]
        }

    async def fake_probe(_ip: str, _ports=None, **_kwargs):
        return (True, "tcp:443")

    def fake_launch(run_id: str, test_plan_id: str | None = None):
        launched.append(run_id)
        return object()

    monkeypatch.setattr("app.services.device_ip_discovery.tools_client.detect_networks", fake_detect_networks)
    monkeypatch.setattr("app.services.device_ip_discovery.tools_client.nmap", fake_nmap)
    monkeypatch.setattr("app.services.device_ip_discovery.tools_client.neighbors", fake_neighbors)
    monkeypatch.setattr("app.services.test_run_connectivity.probe_device_connectivity", fake_probe)
    monkeypatch.setattr("app.routes.test_runs.launch_test_run", fake_launch)

    resp = await client.post(f"/api/test-runs/{run.id}/start", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["status"] == "running"
    assert launched == [run.id]

    device_id = device.id
    db_session.expire_all()
    saved_device = await db_session.get(Device, device_id)
    assert saved_device is not None
    assert saved_device.ip_address == "172.19.0.3"
