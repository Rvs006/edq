"""Manual-add reachability probe on POST /api/v1/devices/."""

import pytest
from httpx import AsyncClient

from .conftest import register_and_login


@pytest.mark.asyncio
async def test_create_device_unreachable_marks_last_seen_none(
    client: AsyncClient, monkeypatch
):
    headers = await register_and_login(client, "devreachfalse", role="admin")

    async def fake_probe(ip, probe_ports=None, tcp_timeout=2.0):
        return (False, None)

    monkeypatch.setattr(
        "app.routes.devices.probe_device_connectivity", fake_probe
    )

    resp = await client.post(
        "/api/devices/",
        json={"ip_address": "192.168.77.10", "hostname": "ghost-device"},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["reachability_verified"] is False
    assert body["last_seen_at"] is None


@pytest.mark.asyncio
async def test_create_device_reachable_sets_last_seen(
    client: AsyncClient, monkeypatch
):
    headers = await register_and_login(client, "devreachtrue", role="admin")

    async def fake_probe(ip, probe_ports=None, tcp_timeout=2.0):
        return (True, "icmp")

    monkeypatch.setattr(
        "app.routes.devices.probe_device_connectivity", fake_probe
    )

    resp = await client.post(
        "/api/devices/",
        json={"ip_address": "192.168.77.20", "hostname": "real-device"},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["reachability_verified"] is True
    assert body["last_seen_at"] is not None
