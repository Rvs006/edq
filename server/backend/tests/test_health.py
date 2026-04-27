"""Tests for health endpoint."""

import asyncio

import pytest
from httpx import AsyncClient

from app.config import settings
from app.services import system_status as system_status_service


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    """Health endpoint should return status."""
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data


@pytest.mark.asyncio
async def test_metrics_requires_api_key_in_cloud_without_key(client: AsyncClient, monkeypatch):
    """Cloud deployments must not expose metrics accidentally."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "cloud")
    monkeypatch.setattr(settings, "METRICS_API_KEY", "")

    resp = await client.get("/api/health/metrics")

    assert resp.status_code == 401
    assert "METRICS_API_KEY" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_system_status_uses_health_for_availability_and_cached_versions(monkeypatch):
    """A slow version probe must not make a healthy scanner look unavailable."""
    original_cache = dict(system_status_service._tools_version_cache)
    original_update_cache = dict(system_status_service._tools_update_cache)
    system_status_service._tools_version_cache.update({
        "versions": None,
        "status": None,
        "message": None,
        "ts": 0.0,
    })
    system_status_service._tools_update_cache.update({"updates": None, "ts": 0.0})

    async def fake_versions_ok():
        return {"versions": {"nmap": "7.95"}}

    async def fake_health_ok():
        return {"tools": {key: True for key in system_status_service.TOOL_KEYS}}

    async def fake_updates_ok():
        return {
            "tools": {
                key: {"installed": "1.0", "latest_known": "1.0", "up_to_date": True}
                for key in system_status_service.TOOL_KEYS
            },
            "image_rebuild_recommended": False,
            "update_instructions": "All tools are up to date.",
        }

    monkeypatch.setattr(system_status_service.tools_client, "health", fake_health_ok)
    monkeypatch.setattr(system_status_service.tools_client, "versions", fake_versions_ok)
    monkeypatch.setattr(system_status_service.tools_client, "check_updates", fake_updates_ok)
    healthy = await system_status_service.get_system_status(include_tool_versions=True)
    assert healthy["tools_sidecar"]["status"] == "ok"
    assert healthy["tools"]["nmap"] == "7.95"
    assert healthy["scanner_updates"]["status"] == "ok"

    async def fake_versions_timeout():
        raise asyncio.TimeoutError()

    system_status_service._tools_version_cache.update({
        "versions": None,
        "status": None,
        "message": None,
        "ts": 0.0,
    })
    monkeypatch.setattr(system_status_service.tools_client, "versions", fake_versions_timeout)
    degraded = await system_status_service.get_system_status(include_tool_versions=True)
    assert degraded["tools_sidecar"]["status"] == "ok"
    assert degraded["status"] == "ok"
    assert degraded["tools"]["nmap"] == "installed"
    assert "version probe timed out" in degraded["tools_sidecar"]["message"].lower()

    system_status_service._tools_version_cache.clear()
    system_status_service._tools_version_cache.update(original_cache)
    system_status_service._tools_update_cache.clear()
    system_status_service._tools_update_cache.update(original_update_cache)


@pytest.mark.asyncio
async def test_system_status_reports_scanner_update_rebuild_guidance(monkeypatch):
    """Scanner freshness should be visible without mutating tools at runtime."""
    original_cache = dict(system_status_service._tools_update_cache)
    system_status_service._tools_update_cache.update({"updates": None, "ts": 0.0})

    async def fake_health_ok():
        return {"tools": {key: True for key in system_status_service.TOOL_KEYS}}

    async def fake_versions_ok():
        return {"versions": {"nmap": "Nmap version 7.94"}}

    async def fake_updates_outdated():
        return {
            "tools": {
                "nmap": {
                    "installed": "7.94",
                    "latest_known": "7.95",
                    "up_to_date": False,
                    "action": "rebuild image to update",
                }
            },
            "image_rebuild_recommended": True,
            "update_instructions": "Run 'docker compose up -d --build backend' to rebuild scanner tools.",
        }

    monkeypatch.setattr(system_status_service.tools_client, "health", fake_health_ok)
    monkeypatch.setattr(system_status_service.tools_client, "versions", fake_versions_ok)
    monkeypatch.setattr(system_status_service.tools_client, "check_updates", fake_updates_outdated)

    status = await system_status_service.get_system_status(include_tool_versions=True)

    assert status["scanner_updates"]["status"] == "outdated"
    assert status["scanner_updates"]["image_rebuild_recommended"] is True
    assert status["scanner_updates"]["tools"]["nmap"]["latest_known"] == "7.95"

    system_status_service._tools_update_cache.clear()
    system_status_service._tools_update_cache.update(original_cache)
