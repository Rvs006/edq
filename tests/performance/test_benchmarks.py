"""Performance benchmark tests — latency, concurrency, compression, caching."""

import asyncio
import re
import subprocess
import time

import httpx
import pytest

from live_helpers import BASE_URL

pytestmark = [pytest.mark.asyncio, pytest.mark.performance]


# ---------------------------------------------------------------------------
# 1. Health endpoint under 50ms
# ---------------------------------------------------------------------------

async def test_health_under_100ms(client: httpx.AsyncClient):
    """GET /api/health should respond in under 100ms."""
    # Warm up
    await client.get("/api/health")

    start = time.monotonic()
    resp = await client.get("/api/health")
    elapsed_ms = (time.monotonic() - start) * 1000

    assert resp.status_code == 200
    assert elapsed_ms < 100, f"Health endpoint took {elapsed_ms:.1f}ms (limit: 100ms)"


# ---------------------------------------------------------------------------
# 2. Frontend loads under 100ms
# ---------------------------------------------------------------------------

async def test_frontend_under_100ms(client: httpx.AsyncClient):
    """GET / should respond in under 100ms."""
    # Warm up
    await client.get("/")

    start = time.monotonic()
    resp = await client.get("/")
    elapsed_ms = (time.monotonic() - start) * 1000

    assert resp.status_code == 200
    assert elapsed_ms < 100, f"Frontend took {elapsed_ms:.1f}ms (limit: 100ms)"


# ---------------------------------------------------------------------------
# 3. Authenticated API under 100ms
# ---------------------------------------------------------------------------

async def test_auth_api_under_100ms(admin_client: httpx.AsyncClient):
    """GET /api/devices/ with auth should respond in under 100ms."""
    # Warm up
    await admin_client.get("/api/devices/")

    start = time.monotonic()
    resp = await admin_client.get("/api/devices/")
    elapsed_ms = (time.monotonic() - start) * 1000

    assert resp.status_code == 200
    assert elapsed_ms < 100, f"Auth API took {elapsed_ms:.1f}ms (limit: 100ms)"


# ---------------------------------------------------------------------------
# 4. Device list under 200ms
# ---------------------------------------------------------------------------

async def test_device_list_under_200ms(admin_client: httpx.AsyncClient):
    """GET /api/devices/ should respond in under 200ms."""
    # Warm up
    await admin_client.get("/api/devices/")

    start = time.monotonic()
    resp = await admin_client.get("/api/devices/")
    elapsed_ms = (time.monotonic() - start) * 1000

    assert resp.status_code == 200
    assert elapsed_ms < 200, f"Device list took {elapsed_ms:.1f}ms (limit: 200ms)"


# ---------------------------------------------------------------------------
# 5. 20 concurrent requests under 5 seconds total
# ---------------------------------------------------------------------------

async def test_concurrent_20_requests(admin_client: httpx.AsyncClient):
    """20 concurrent GET /api/devices/ should all succeed within 5 seconds."""

    async def fetch() -> httpx.Response:
        return await admin_client.get("/api/devices/")

    start = time.monotonic()
    responses = await asyncio.gather(
        *[fetch() for _ in range(20)],
        return_exceptions=True,
    )
    total_ms = (time.monotonic() - start) * 1000

    for i, resp in enumerate(responses):
        if isinstance(resp, Exception):
            pytest.fail(f"Request {i} raised {type(resp).__name__}: {resp}")
        assert resp.status_code == 200, f"Request {i} returned {resp.status_code}"

    assert total_ms < 5000, f"20 concurrent requests took {total_ms:.0f}ms (limit: 5000ms)"


# ---------------------------------------------------------------------------
# 6. Gzip / Brotli compression
# ---------------------------------------------------------------------------

async def test_gzip_compression(admin_client: httpx.AsyncClient):
    """API should return compressed responses when Accept-Encoding is set."""
    resp = await admin_client.get(
        "/api/devices/",
        headers={"Accept-Encoding": "gzip, deflate, br"},
    )
    assert resp.status_code == 200

    encoding = resp.headers.get("content-encoding", "").lower()
    # nginx or FastAPI may compress with gzip, br, or deflate
    assert encoding in ("gzip", "br", "deflate"), (
        f"Expected compressed response, got Content-Encoding: '{encoding}'. "
        "Check that nginx or the backend has compression enabled."
    )


# ---------------------------------------------------------------------------
# 7. Static asset caching headers
# ---------------------------------------------------------------------------

async def test_static_asset_caching(client: httpx.AsyncClient):
    """Static JS/CSS assets should have Cache-Control with max-age."""
    # Fetch the HTML to find a hashed asset reference
    resp = await client.get("/")
    assert resp.status_code == 200
    html = resp.text

    # Look for Vite-hashed assets like /assets/index-abc123.js
    asset_match = re.search(r'(?:src|href)=["\'](/assets/[^"\']+\.(js|css))', html)
    if not asset_match:
        pytest.skip("No hashed static assets found in HTML — may be dev mode")

    asset_path = asset_match.group(1)
    asset_resp = await client.get(asset_path)
    assert asset_resp.status_code == 200

    cache_control = asset_resp.headers.get("cache-control", "")
    assert "max-age" in cache_control.lower(), (
        f"Static asset {asset_path} missing Cache-Control max-age. "
        f"Got: '{cache_control}'"
    )


# ---------------------------------------------------------------------------
# 8. Docker memory usage
# ---------------------------------------------------------------------------

async def test_docker_memory(client: httpx.AsyncClient):
    """Backend container should use less than 2GB of memory."""
    try:
        result = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{.Name}} {{.MemUsage}}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pytest.skip("Docker CLI not available or timed out")

    if result.returncode != 0:
        pytest.skip(f"docker stats failed: {result.stderr.strip()}")

    output = result.stdout.strip()
    if not output:
        pytest.skip("No docker containers running")

    for line in output.splitlines():
        parts = line.strip().split()
        if len(parts) < 2:
            continue

        container_name = parts[0]
        mem_usage = parts[1]  # e.g. "150.2MiB" or "1.5GiB"

        # Only check backend-related containers
        if "backend" not in container_name.lower():
            continue

        # Parse memory value
        mem_mb = _parse_mem_to_mb(mem_usage)
        if mem_mb is not None:
            assert mem_mb < 2048, (
                f"Container {container_name} using {mem_mb:.0f}MB "
                f"(limit: 2048MB / 2GB)"
            )


def _parse_mem_to_mb(mem_str: str) -> float | None:
    """Parse Docker memory string like '150.2MiB' or '1.5GiB' to megabytes."""
    match = re.match(r"([\d.]+)\s*(KiB|MiB|GiB|kB|MB|GB|B)", mem_str, re.IGNORECASE)
    if not match:
        return None

    value = float(match.group(1))
    unit = match.group(2).lower()

    multipliers = {
        "b": 1 / (1024 * 1024),
        "kib": 1 / 1024,
        "kb": 1 / 1024,
        "mib": 1,
        "mb": 1,
        "gib": 1024,
        "gb": 1024,
    }
    return value * multipliers.get(unit, 1)
