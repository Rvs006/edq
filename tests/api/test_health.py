"""Health endpoint tests — public health check, metrics, tool versions, system status."""

import httpx
import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.api]


# ---------------------------------------------------------------------------
# 1. Public health check — no auth required
# ---------------------------------------------------------------------------

async def test_health_check_public(client: httpx.AsyncClient):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") in ("ok", "degraded")


# ---------------------------------------------------------------------------
# 2. Metrics endpoint
# ---------------------------------------------------------------------------

async def test_health_metrics(client: httpx.AsyncClient):
    resp = await client.get("/api/health/metrics")
    # Metrics may require an API key; 200 if open, 401 if locked down
    assert resp.status_code in (200, 401)
    if resp.status_code == 200:
        # Should return Prometheus text exposition format
        assert "text/plain" in resp.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# 3. Tool versions — authenticated
# ---------------------------------------------------------------------------

async def test_tool_versions_auth(admin_client: httpx.AsyncClient):
    resp = await admin_client.get("/api/health/tools/versions")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data


# ---------------------------------------------------------------------------
# 4. System status — authenticated
# ---------------------------------------------------------------------------

async def test_system_status_auth(admin_client: httpx.AsyncClient):
    resp = await admin_client.get("/api/health/system-status")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# 5. Tool versions — no auth should 401
# ---------------------------------------------------------------------------

async def test_tool_versions_no_auth(client: httpx.AsyncClient):
    resp = await client.get("/api/health/tools/versions")
    assert resp.status_code == 401
