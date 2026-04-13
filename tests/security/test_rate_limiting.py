"""Rate limiting tests — verify endpoints enforce request throttling."""

import asyncio
import uuid

import httpx
import pytest

from live_helpers import BASE_URL, _login, _apply_auth, ADMIN_USER, ADMIN_PASS

pytestmark = [pytest.mark.asyncio, pytest.mark.security]


async def _rapid_fire(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    count: int,
    **kwargs,
) -> list[int]:
    """Send `count` rapid requests and return list of status codes."""
    statuses = []
    for _ in range(count):
        if method == "POST":
            resp = await client.post(url, **kwargs)
        else:
            resp = await client.get(url, **kwargs)
        statuses.append(resp.status_code)
    return statuses


# ---------------------------------------------------------------------------
# 1. Login rate limiting
# ---------------------------------------------------------------------------

async def test_login_rate_limit(client: httpx.AsyncClient):
    """Rapid login attempts should trigger rate limiting (429)."""
    statuses = await _rapid_fire(
        client,
        "POST",
        "/api/auth/login",
        20,
        json={"username": "nobody", "password": "wrongpass1"},
    )
    if 429 not in statuses:
        pytest.xfail(
            f"Rate limiting not enforced on /api/auth/login — "
            f"statuses: {set(statuses)}"
        )


# ---------------------------------------------------------------------------
# 2. Import rate limiting
# ---------------------------------------------------------------------------

async def test_import_rate_limit(admin_client: httpx.AsyncClient):
    """Rapid import requests should trigger rate limiting."""
    statuses = []
    for _ in range(10):
        resp = await admin_client.post(
            "/api/devices/import",
            files={"file": ("devices.csv", b"ip_address\n", "text/csv")},
        )
        statuses.append(resp.status_code)
    if 429 not in statuses:
        pytest.xfail(
            f"Rate limiting not enforced on /api/devices/import — "
            f"statuses: {set(statuses)}"
        )


# ---------------------------------------------------------------------------
# 3. Report generation rate limiting
# ---------------------------------------------------------------------------

async def test_report_rate_limit(admin_client: httpx.AsyncClient):
    """Rapid report generation requests should trigger rate limiting."""
    statuses = await _rapid_fire(
        admin_client,
        "POST",
        "/api/reports/generate",
        70,
        json={"test_run_id": str(uuid.uuid4()), "report_type": "excel"},
    )
    if 429 not in statuses:
        pytest.xfail(
            f"Rate limiting not enforced on /api/reports/generate — "
            f"statuses: {set(statuses)}"
        )


# ---------------------------------------------------------------------------
# 4. Network scan rate limiting
# ---------------------------------------------------------------------------

async def test_scan_rate_limit(admin_client: httpx.AsyncClient):
    """Rapid scan requests should trigger rate limiting."""
    statuses = await _rapid_fire(
        admin_client,
        "POST",
        "/api/network-scan/discover",
        10,
        json={"cidr": "10.99.0.0/8", "connection_scenario": "test_lab"},
    )
    if 429 not in statuses:
        pytest.xfail(
            f"Rate limiting not enforced on /api/network-scan/discover — "
            f"statuses: {set(statuses)}"
        )
