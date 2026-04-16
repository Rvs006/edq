"""Tests for rate limiting on import, report, and scan endpoints."""

import io
import uuid

import pytest
from httpx import AsyncClient

from ..conftest import register_and_login
from app.middleware.rate_limit import rate_limiter


@pytest.mark.asyncio
async def test_import_rate_limit(client: AsyncClient):
    """The device import endpoint should enforce rate limiting.

    After adding rate limiting (max_requests=5, window=60s, action=device_import),
    exceeding the limit should return 429.
    """
    headers = await register_and_login(client, suffix="import_rl")

    csv_content = "ip_address,name\n192.168.1.100,TestDevice\n"
    statuses = []

    for i in range(8):
        files = {"file": (f"devices_{i}.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        resp = await client.post(
            "/api/devices/import",
            files=files,
            headers=headers,
        )
        statuses.append(resp.status_code)

    assert 429 in statuses, (
        f"Expected at least one 429 response after exceeding rate limit. "
        f"Got statuses: {statuses}"
    )


@pytest.mark.asyncio
async def test_report_rate_limit(client: AsyncClient):
    """The report generation endpoint should enforce rate limiting.

    After adding rate limiting (max_requests=5, window=60s, action=report_generate),
    exceeding the limit should return 429.
    """
    rate_limiter._buckets.clear()
    headers = await register_and_login(client, suffix="report_rl")

    statuses = []
    payload = {
        "test_run_id": str(uuid.uuid4()),
        "report_type": "excel",
    }
    for _ in range(65):
        resp = await client.post(
            "/api/reports/generate",
            json=payload,
            headers=headers,
        )
        statuses.append(resp.status_code)

    assert 429 in statuses, (
        f"Expected at least one 429 response after exceeding rate limit. "
        f"Got statuses: {statuses}"
    )


@pytest.mark.asyncio
async def test_scan_rate_limit(client: AsyncClient):
    """The network scan endpoint should enforce rate limiting.

    Uses two buckets: DISCOVERY_GLOBAL_RATE_LIMIT_PER_MINUTE (per-client) and
    DISCOVERY_RATE_LIMIT_PER_MINUTE (per-target-scope). Exceeding the global
    cap must return 429 regardless of whether each target would have been
    authorized.
    """
    from app.config import settings

    rate_limiter._buckets.clear()
    headers = await register_and_login(client, suffix="scan_rl")

    # Fire enough requests to exceed the global cap. Each iteration uses the
    # same CIDR, so the per-scope bucket also trips; the global cap is higher
    # so it always hits last. Add a safety margin of +5.
    attempts = settings.DISCOVERY_GLOBAL_RATE_LIMIT_PER_MINUTE + 5

    statuses = []
    for _ in range(attempts):
        resp = await client.post(
            "/api/network-scan/discover",
            json={"cidr": "192.168.1.0/24", "connection_scenario": "test_lab", "test_ids": []},
            headers=headers,
        )
        statuses.append(resp.status_code)

    assert 429 in statuses, (
        f"Expected at least one 429 response after exceeding rate limit. "
        f"Got statuses: {statuses}"
    )
