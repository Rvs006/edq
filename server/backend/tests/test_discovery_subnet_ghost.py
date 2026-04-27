"""Regression test: subnet discovery must drop ghost hosts via probe gate."""

import pytest
from httpx import AsyncClient

from .conftest import register_and_login

TWO_HOST_STDOUT = (
    "Nmap scan report for 10.50.50.10\n"
    "Host is up (0.00052s latency).\n"
    "MAC Address: AA:BB:CC:DD:EE:01 (Vendor A)\n"
    "\n"
    "Nmap scan report for 10.50.50.20\n"
    "Host is up (0.00060s latency).\n"
    "MAC Address: AA:BB:CC:DD:EE:02 (Vendor B)\n"
)


@pytest.mark.asyncio
async def test_subnet_discovery_skips_ghost_hosts(client: AsyncClient, monkeypatch):
    """nmap -sn reports 2 hosts; probe says only one is real -> skip the ghost."""
    headers = await register_and_login(client, suffix="subghost", role="admin")

    async def fake_nmap(target, args=None, timeout=120):
        return {"stdout": TWO_HOST_STDOUT}

    async def fake_probe(ip):
        if ip == "10.50.50.10":
            return (True, "tcp:80")
        return (False, "icmp_only_untrusted")

    monkeypatch.setattr("app.routes.discovery.tools_client.nmap", fake_nmap)
    monkeypatch.setattr("app.routes.discovery.probe_device_connectivity", fake_probe)

    resp = await client.post(
        "/api/discovery/scan",
        json={"subnet": "10.50.50.0/24"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["devices_found"] == 1
    assert body["unreachable_skipped"] == 1
    assert len(body["devices"]) == 1
    assert body["devices"][0]["ip_address"] == "10.50.50.10"
