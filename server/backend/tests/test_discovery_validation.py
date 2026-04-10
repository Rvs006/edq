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
