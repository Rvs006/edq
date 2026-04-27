"""Regression tests for the discovery reachability gate.

Ensures POST /api/v1/discovery/scan does not return stale "found" results,
while still accepting direct-cable devices when the TCP stack answers but
Docker host discovery misses the target.
"""

import pytest
from httpx import AsyncClient

from .conftest import register_and_login

HOST_DOWN_XML = (
    '<?xml version="1.0"?><nmaprun>'
    '<host><status state="down" reason="no-response"/>'
    '<address addr="10.99.99.99" addrtype="ipv4"/></host>'
    "</nmaprun>"
)

HOST_UP_XML = (
    '<?xml version="1.0"?><nmaprun>'
    '<host><status state="up" reason="echo-reply"/>'
    '<address addr="10.99.99.99" addrtype="ipv4"/></host>'
    "</nmaprun>"
)


@pytest.mark.asyncio
async def test_discovery_both_signals_unreachable_returns_zero(client: AsyncClient, monkeypatch):
    """Both probes say down -> devices_found == 0 (no stale success)."""
    headers = await register_and_login(client, suffix="reachboth", role="admin")

    async def fake_nmap(target, args=None, timeout=300):
        return {"stdout": HOST_DOWN_XML}

    async def fake_probe(ip):
        return (False, None)

    monkeypatch.setattr("app.routes.discovery.tools_client.nmap", fake_nmap)
    monkeypatch.setattr("app.routes.discovery.probe_device_connectivity", fake_probe)

    resp = await client.post(
        "/api/discovery/scan",
        json={"ip_address": "10.99.99.99"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["devices_found"] == 0
    assert body["devices"] == []


@pytest.mark.asyncio
async def test_discovery_one_signal_unreachable_returns_zero(client: AsyncClient, monkeypatch):
    """ARP says up, TCP/ICMP says down -> discovery still returns 0."""
    headers = await register_and_login(client, suffix="reachone", role="admin")

    async def fake_nmap(target, args=None, timeout=300):
        return {"stdout": HOST_UP_XML}

    async def fake_probe(ip):
        return (False, None)

    monkeypatch.setattr("app.routes.discovery.tools_client.nmap", fake_nmap)
    monkeypatch.setattr("app.routes.discovery.probe_device_connectivity", fake_probe)

    resp = await client.post(
        "/api/discovery/scan",
        json={"ip_address": "10.99.99.99"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["devices_found"] == 0
    assert body["devices"] == []


@pytest.mark.asyncio
async def test_discovery_accepts_tcp_proof_when_arp_bypass_ping_misses_direct_device(
    client: AsyncClient,
    monkeypatch,
):
    """TCP says up, ARP-bypass ping says down -> direct-cable discovery proceeds."""
    headers = await register_and_login(client, suffix="reachtcp", role="admin")
    nmap_calls: list[tuple[str, tuple[str, ...] | None, int]] = []

    service_xml = (
        '<?xml version="1.0"?><nmaprun>'
        '<host><status state="up"/>'
        '<address addr="10.99.99.99" addrtype="ipv4"/>'
        '<ports><port protocol="tcp" portid="22">'
        '<state state="open"/><service name="ssh" product="Dropbear sshd"/>'
        "</port></ports></host></nmaprun>"
    )

    async def fake_nmap(target, args=None, timeout=300):
        nmap_calls.append((target, tuple(args or ()), timeout))
        if args and "-sn" in args:
            return {"stdout": HOST_DOWN_XML}
        return {"stdout": service_xml}

    async def fake_probe(ip):
        return (True, "tcp:22")

    monkeypatch.setattr("app.routes.discovery.tools_client.nmap", fake_nmap)
    monkeypatch.setattr("app.routes.discovery.probe_device_connectivity", fake_probe)

    resp = await client.post(
        "/api/discovery/scan",
        json={"ip_address": "10.99.99.99"},
        headers=headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["devices_found"] == 1
    assert body["devices"][0]["ip_address"] == "10.99.99.99"
    assert len(nmap_calls) == 2


@pytest.mark.asyncio
async def test_single_ip_discovery_uses_bounded_service_scan(client: AsyncClient, monkeypatch):
    """Single-IP discovery should not run an all-ports scan that can outlive the UI timeout."""
    headers = await register_and_login(client, suffix="reachfast", role="admin")
    nmap_calls: list[tuple[str, tuple[str, ...] | None, int]] = []

    service_xml = (
        '<?xml version="1.0"?><nmaprun>'
        '<host><status state="up"/>'
        '<address addr="10.99.99.99" addrtype="ipv4"/>'
        '<ports><port protocol="tcp" portid="80">'
        '<state state="open"/><service name="http"/>'
        "</port></ports></host></nmaprun>"
    )

    async def fake_nmap(target, args=None, timeout=300):
        nmap_calls.append((target, tuple(args or ()), timeout))
        if args and "-sn" in args:
            return {"stdout": HOST_UP_XML}
        return {"stdout": service_xml}

    async def fake_probe(ip):
        return (True, "tcp:80")

    monkeypatch.setattr("app.routes.discovery.tools_client.nmap", fake_nmap)
    monkeypatch.setattr("app.routes.discovery.probe_device_connectivity", fake_probe)

    resp = await client.post(
        "/api/discovery/scan",
        json={"ip_address": "10.99.99.99"},
        headers=headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["devices_found"] == 1
    assert body["devices"][0]["ip_address"] == "10.99.99.99"
    service_scan_args = nmap_calls[1][1]
    assert "-p-" not in service_scan_args
    assert "--top-ports" in service_scan_args
    assert nmap_calls[1][2] <= 60
