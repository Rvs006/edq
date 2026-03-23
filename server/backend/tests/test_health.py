"""Tests for health endpoint."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    """Health endpoint should return status."""
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
