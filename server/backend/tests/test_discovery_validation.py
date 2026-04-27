"""Tests for discovery input validation."""

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select

from app.models.authorized_network import AuthorizedNetwork
from app.models.device import Device
from app.schemas.device import DeviceCreate, DeviceUpdate, DiscoveryRequest

from .conftest import register_and_login


@pytest.mark.parametrize(
    ("schema", "payload"),
    [
        (DeviceCreate, {"ip_address": "2001:db8::10"}),
        (DeviceUpdate, {"ip_address": "2001:db8::10"}),
        (DiscoveryRequest, {"ip_address": "2001:db8::10"}),
    ],
)
def test_device_ip_schemas_reject_ipv6_targets(schema, payload):
    with pytest.raises(ValidationError, match="Invalid IPv4 address"):
        schema(**payload)


@pytest.mark.asyncio
async def test_discovery_rejects_invalid_subnet(client: AsyncClient):
    """DiscoveryRequest with a malformed subnet should return 422."""
    headers = await register_and_login(client, suffix="discval")
    resp = await client.post(
        "/api/discovery/scan",
        json={"subnet": "not-a-subnet"},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_discovery_rejects_invalid_ip(client: AsyncClient):
    """DiscoveryRequest with a malformed IP should return 422."""
    headers = await register_and_login(client, suffix="discval2")
    resp = await client.post(
        "/api/discovery/scan",
        json={"ip_address": "999.999.999.999"},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_discovery_rejects_subnet_prefix_outside_scan_limits(client: AsyncClient):
    headers = await register_and_login(client, suffix="discwide")
    resp = await client.post(
        "/api/discovery/scan",
        json={"subnet": "10.0.0.0/8"},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_discovery_rejects_unauthorized_engineer_target(client: AsyncClient):
    headers = await register_and_login(client, suffix="discunauth")
    resp = await client.post(
        "/api/discovery/scan",
        json={"subnet": "10.66.0.0/24"},
        headers=headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_discovery_admin_auto_authorizes_target(
    client: AsyncClient,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    headers = await register_and_login(client, suffix="discadminauth", role="admin")

    async def fake_nmap(_target: str, _args=None, timeout: int = 300):
        return {"stdout": ""}

    monkeypatch.setattr("app.routes.discovery.tools_client.nmap", fake_nmap)

    resp = await client.post(
        "/api/discovery/scan",
        json={"subnet": "10.67.0.0/24"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    saved = await db_session.execute(
        select(AuthorizedNetwork).where(AuthorizedNetwork.cidr == "10.67.0.0/24")
    )
    assert saved.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_network_scan_rejects_invalid_device_ips(client: AsyncClient):
    """StartBatchRequest with invalid device_ips should return 422."""
    headers = await register_and_login(client, suffix="netscanval")
    resp = await client.post(
        "/api/network-scan/start",
        json={
            "scan_id": "fake-scan-id",
            "device_ips": ["not-an-ip", "192.168.1.1"],
        },
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_network_scan_rejects_invalid_cidr_octets(client: AsyncClient):
    headers = await register_and_login(client, suffix="netscancidr", role="admin")
    resp = await client.post(
        "/api/network-scan/discover",
        json={"cidr": "999.999.999.999/24", "connection_scenario": "test_lab"},
        headers=headers,
    )
    assert resp.status_code in {400, 422}


@pytest.mark.asyncio
async def test_network_scan_enriches_missing_mac_from_neighbor_cache(client: AsyncClient, monkeypatch):
    headers = await register_and_login(client, suffix="netscanneighbor", role="admin")
    nmap_calls: list[tuple[str, tuple[str, ...] | None]] = []

    async def fake_nmap(target: str, args=None, timeout: int = 300):
        nmap_calls.append((target, tuple(args) if args else None))
        if args == ["-sn", "-PR"]:
            return {
                "stdout": (
                    "Nmap scan report for edq-frontend.edq_edq-frontend (172.19.0.3)\n"
                    "Host is up (0.00066s latency).\n"
                )
            }
        return {"stdout": ""}

    async def fake_neighbors(subnet: str | None = None):
        assert subnet == "172.19.0.0/24"
        return {
            "entries": [
                {
                    "ip": "172.19.0.3",
                    "mac": "BA:EF:DD:5D:42:C0",
                    "state": "REACHABLE",
                    "vendor": None,
                }
            ]
        }

    monkeypatch.setattr("app.routes.network_scan.tools_client.nmap", fake_nmap)
    monkeypatch.setattr("app.services.device_ip_discovery.tools_client.neighbors", fake_neighbors)

    resp = await client.post(
        "/api/network-scan/discover",
        json={
            "cidr": "172.19.0.0/24",
            "connection_scenario": "test_lab",
        },
        headers=headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    assert data["devices_found"][0]["ip"] == "172.19.0.3"
    assert data["devices_found"][0]["mac"] == "BA:EF:DD:5D:42:C0"
    assert nmap_calls[0][0] == "172.19.0.0/24"


@pytest.mark.asyncio
async def test_network_scan_merges_known_device_mac_into_discovery(
    client: AsyncClient,
    db_session,
    monkeypatch,
):
    headers = await register_and_login(client, suffix="netscanknownmac", role="admin")
    device = Device(
        ip_address="192.168.4.64",
        mac_address="38:D1:35:02:47:1A",
        manufacturer="EasyIO",
        oui_vendor="EasyIO",
        category="controller",
        status="discovered",
    )
    db_session.add(device)
    await db_session.commit()

    async def fake_nmap(target: str, args=None, timeout: int = 300):
        if args == ["-sn", "-PR"]:
            return {
                "stdout": (
                    "Nmap scan report for 192.168.4.64\n"
                    "Host is up (0.002s latency).\n"
                )
            }
        return {"stdout": ""}

    async def fake_neighbors(subnet: str | None = None):
        return {"entries": []}

    async def fail_tcp_discovery(_cidr: str, candidate_ips=None):
        raise AssertionError("Single-host /32 discovery must not use Docker ghost-host TCP gating")

    monkeypatch.setattr("app.routes.network_scan.tools_client.nmap", fake_nmap)
    monkeypatch.setattr("app.services.device_ip_discovery.tools_client.neighbors", fake_neighbors)
    monkeypatch.setattr("app.routes.network_scan._discover_hosts_by_tcp", fail_tcp_discovery)

    resp = await client.post(
        "/api/network-scan/discover",
        json={
            "cidr": "192.168.4.64/32",
            "connection_scenario": "direct",
        },
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["devices_found"][0]["mac"] == "38:D1:35:02:47:1A"
    assert data["devices_found"][0]["vendor"] == "EasyIO"


@pytest.mark.asyncio
async def test_network_scan_gates_docker_ghost_hosts_with_tcp_probe(client: AsyncClient, monkeypatch):
    headers = await register_and_login(client, suffix="netscanghost", role="admin")
    nmap_calls: list[tuple[str, tuple[str, ...] | None]] = []

    async def fake_nmap(target: str, args=None, timeout: int = 300):
        nmap_calls.append((target, tuple(args) if args else None))
        if args == ["-sn", "-PR"]:
            lines = []
            for last_octet in range(1, 21):
                lines.append(f"Nmap scan report for 192.168.4.{last_octet}")
                lines.append("Host is up (0.002s latency).")
            return {"stdout": "\n".join(lines)}
        raise AssertionError("slow enrichment should be skipped for TCP-gated Docker discovery")

    async def fake_neighbors(subnet: str | None = None):
        return {"entries": []}

    async def fake_tcp_discovery(cidr: str, candidate_ips=None):
        assert cidr == "192.168.4.0/24"
        assert candidate_ips is None
        return [
            {
                "ip": "192.168.4.64",
                "mac": None,
                "vendor": None,
                "hostname": None,
                "services": ["http/80"],
                "open_ports": [{"port": 80, "service": "http", "version": ""}],
            }
        ]

    monkeypatch.setattr("app.routes.network_scan.tools_client.in_docker", True)
    monkeypatch.setattr("app.routes.network_scan.tools_client.scanner_in_docker", True)
    monkeypatch.setattr("app.routes.network_scan.tools_client.nmap", fake_nmap)
    monkeypatch.setattr("app.services.device_ip_discovery.tools_client.neighbors", fake_neighbors)
    monkeypatch.setattr("app.routes.network_scan._discover_hosts_by_tcp", fake_tcp_discovery)

    resp = await client.post(
        "/api/network-scan/discover",
        json={
            "cidr": "192.168.4.0/24",
            "connection_scenario": "direct",
        },
        headers=headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    assert [host["ip"] for host in data["devices_found"]] == ["192.168.4.64"]
    assert nmap_calls == [("192.168.4.0/24", ("-sn", "-PR"))]


@pytest.mark.asyncio
async def test_network_scan_accepts_single_host_cidr(client: AsyncClient, monkeypatch):
    headers = await register_and_login(client, suffix="netscanhost", role="admin")

    async def fake_nmap(target: str, args=None, timeout: int = 300):
        assert target == "192.168.4.64/32"
        assert args == ["-sn", "-PR"]
        return {
            "stdout": (
                "Nmap scan report for 192.168.4.64\n"
                "Host is up (0.002s latency).\n"
            )
        }

    async def fake_neighbors(subnet: str | None = None):
        return {"entries": []}

    async def fake_tcp_discovery(cidr: str, candidate_ips=None):
        assert cidr == "192.168.4.64/32"
        return [
            {
                "ip": "192.168.4.64",
                "mac": None,
                "vendor": None,
                "hostname": None,
                "services": ["http/80"],
                "open_ports": [{"port": 80, "service": "http", "version": ""}],
            }
        ]

    monkeypatch.setattr("app.routes.network_scan.tools_client.in_docker", True)
    monkeypatch.setattr("app.routes.network_scan.tools_client.scanner_in_docker", True)
    monkeypatch.setattr("app.routes.network_scan.tools_client.nmap", fake_nmap)
    monkeypatch.setattr("app.services.device_ip_discovery.tools_client.neighbors", fake_neighbors)
    monkeypatch.setattr("app.routes.network_scan._discover_hosts_by_tcp", fake_tcp_discovery)

    resp = await client.post(
        "/api/network-scan/discover",
        json={
            "cidr": "192.168.4.64/32",
            "connection_scenario": "direct",
        },
        headers=headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["devices_found"][0]["ip"] == "192.168.4.64"
