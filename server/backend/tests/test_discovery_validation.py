"""Tests for discovery input validation."""

import pytest
from httpx import AsyncClient

from .conftest import register_and_login


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
