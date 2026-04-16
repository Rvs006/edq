"""Regression tests for the discovery reachability AND-gate.

Ensures that POST /api/v1/discovery/scan does NOT return a stale "found"
result when either the TCP/ICMP probe or nmap's ARP-bypass ping says
the host is unreachable (e.g. cable unplugged but ARP cache still warm).
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
    headers = await register_and_login(client, suffix="reachboth")

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
    """ARP says up, TCP/ICMP says down -> AND-gate still returns 0."""
    headers = await register_and_login(client, suffix="reachone")

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
