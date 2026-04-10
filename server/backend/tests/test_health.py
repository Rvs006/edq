"""Tests for health endpoint."""

import pytest
from httpx import AsyncClient

from app.services import system_status as system_status_service


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    """Health endpoint should return status."""
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data


@pytest.mark.asyncio
async def test_system_status_uses_cached_versions_but_reports_unavailable(monkeypatch):
    """Cached tool versions must not make a live sidecar failure look healthy."""
    original_cache = dict(system_status_service._tools_version_cache)
    system_status_service._tools_version_cache.update({
        "versions": None,
        "status": None,
        "message": None,
        "ts": 0.0,
    })

    async def fake_versions_ok():
        return {"versions": {"nmap": "7.95"}}

    async def fake_versions_fail():
        raise RuntimeError("sidecar down")

    monkeypatch.setattr(system_status_service.tools_client, "versions", fake_versions_ok)
    healthy = await system_status_service.get_system_status(include_tool_versions=True)
    assert healthy["tools_sidecar"]["status"] == "ok"
    assert healthy["tools"]["nmap"] == "7.95"

    monkeypatch.setattr(system_status_service.tools_client, "versions", fake_versions_fail)
    degraded = await system_status_service.get_system_status(include_tool_versions=True)
    assert degraded["tools_sidecar"]["status"] == "unavailable"
    assert degraded["status"] == "degraded"
    assert degraded["tools"]["nmap"] == "7.95"
    assert "cached tool versions" in degraded["tools_sidecar"]["message"].lower()

    system_status_service._tools_version_cache.clear()
    system_status_service._tools_version_cache.update(original_cache)
