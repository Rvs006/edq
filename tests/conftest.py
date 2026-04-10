"""Root conftest — shared fixtures for all EDQ integration tests.

All tests hit the running app at BASE_URL (default http://localhost:3000).
Auth is cookie-based: login sets edq_session (JWT) and edq_csrf cookies.
Mutating requests must include X-CSRF-Token header.
"""

import uuid
from typing import AsyncGenerator

import httpx
import pytest
import pytest_asyncio

from tests.auth_cache import get_cached_auth
from tests.helpers import (
    BASE_URL, ADMIN_USER, ADMIN_PASS,
    ENGINEER_USER, ENGINEER_PASS,
    REVIEWER_USER, REVIEWER_PASS,
    unique_ip, _login, _apply_auth,
)

def _make_client(auth: dict) -> httpx.AsyncClient:
    """Create an httpx.AsyncClient pre-configured with auth."""
    c = httpx.AsyncClient(base_url=BASE_URL, timeout=30.0)
    _apply_auth(c, auth)
    return c


# ---------------------------------------------------------------------------
# Unauthenticated client
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as c:
        yield c


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def admin_auth() -> dict:
    return await get_cached_auth(ADMIN_USER, ADMIN_PASS)


@pytest_asyncio.fixture
async def admin_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    auth = await get_cached_auth(ADMIN_USER, ADMIN_PASS)
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as c:
        _apply_auth(c, auth)
        yield c


# ---------------------------------------------------------------------------
# Engineer
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def engineer_auth() -> dict:
    return await get_cached_auth(ENGINEER_USER, ENGINEER_PASS)


@pytest_asyncio.fixture
async def engineer_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    auth = await get_cached_auth(ENGINEER_USER, ENGINEER_PASS)
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as c:
        _apply_auth(c, auth)
        yield c


# ---------------------------------------------------------------------------
# Reviewer
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def reviewer_auth() -> dict:
    return await get_cached_auth(REVIEWER_USER, REVIEWER_PASS)


@pytest_asyncio.fixture
async def reviewer_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    auth = await get_cached_auth(REVIEWER_USER, REVIEWER_PASS)
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as c:
        _apply_auth(c, auth)
        yield c


# ---------------------------------------------------------------------------
# Test data fixtures
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def test_device(admin_client: httpx.AsyncClient) -> AsyncGenerator[dict, None]:
    ip = unique_ip()
    resp = await admin_client.post(
        "/api/devices/",
        json={
            "ip_address": ip,
            "hostname": f"fixture-dev-{uuid.uuid4().hex[:6]}",
            "manufacturer": "FixtureCo",
            "model": "FX-100",
            "device_type": "controller",
            "category": "controller",
        },
    )
    assert resp.status_code == 201, f"Failed to create test device: {resp.text}"
    device = resp.json()
    yield device
    await admin_client.delete(f"/api/devices/{device['id']}")


@pytest_asyncio.fixture
async def test_project(admin_client: httpx.AsyncClient) -> AsyncGenerator[dict, None]:
    resp = await admin_client.post(
        "/api/projects/",
        json={
            "name": f"fixture-proj-{uuid.uuid4().hex[:6]}",
            "client_name": "FixtureCorp",
            "location": "Test Lab",
        },
    )
    assert resp.status_code == 201, f"Failed to create test project: {resp.text}"
    project = resp.json()
    yield project
    await admin_client.delete(f"/api/projects/{project['id']}")
