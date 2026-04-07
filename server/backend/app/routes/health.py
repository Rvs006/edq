"""Health check route — database + tools sidecar status + Prometheus metrics."""

import time

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text, func, select
from sqlalchemy.sql import quoted_name

from app.config import settings
from app.models.database import async_session
from app.models.user import User
from app.security.auth import get_current_active_user
from app.services.system_status import get_system_status

router = APIRouter()

# Simple in-process counters for Prometheus metrics
_metrics = {
    "http_requests_total": 0,
    "startup_time": time.time(),
}


def _increment_requests():
    _metrics["http_requests_total"] += 1


@router.get("")
async def health_check():
    """Public health endpoint for load balancers. No auth required."""
    _increment_requests()
    db_status = "ok"
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "database": db_status,
    }


@router.get("/metrics", response_class=Response)
async def prometheus_metrics(request: Request):
    """Prometheus-compatible metrics endpoint.

    When METRICS_API_KEY is configured, requests must include
    ``Authorization: Bearer <key>``. When no key is set the endpoint
    remains open for easy Prometheus scraping.
    """
    if settings.METRICS_API_KEY:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer ") or auth_header[7:] != settings.METRICS_API_KEY:
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing metrics API key"})
    db_ok = 1
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        db_ok = 0

    uptime = time.time() - _metrics["startup_time"]

    # Count table rows for operational metrics
    # Use a hardcoded allowlist and quoted identifiers instead of f-string interpolation
    _ALLOWED_TABLES = frozenset({"users", "devices", "test_runs", "audit_logs", "network_scans"})
    table_counts = {}
    try:
        async with async_session() as session:
            for table in _ALLOWED_TABLES:
                try:
                    safe_table = quoted_name(table, quote=True)
                    result = await session.execute(
                        text("SELECT COUNT(*) FROM " + str(safe_table))
                    )
                    table_counts[table] = result.scalar() or 0
                except Exception:
                    table_counts[table] = 0
    except Exception:
        pass

    lines = [
        "# HELP edq_up Whether the EDQ backend is up (1=healthy, 0=unhealthy)",
        "# TYPE edq_up gauge",
        f"edq_up {db_ok}",
        "",
        "# HELP edq_uptime_seconds Seconds since backend started",
        "# TYPE edq_uptime_seconds gauge",
        f"edq_uptime_seconds {uptime:.0f}",
        "",
        "# HELP edq_health_checks_total Total health check requests",
        "# TYPE edq_health_checks_total counter",
        f'edq_health_checks_total {_metrics["http_requests_total"]}',
    ]

    if table_counts:
        lines += [
            "",
            "# HELP edq_table_rows Number of rows per table",
            "# TYPE edq_table_rows gauge",
        ]
        for table, count in table_counts.items():
            lines.append(f'edq_table_rows{{table="{table}"}} {count}')

    body = "\n".join(lines) + "\n"
    return Response(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")


@router.get("/tools/versions")
async def tool_versions(_user: User = Depends(get_current_active_user)):
    """Return installed tool versions from the sidecar. Requires authentication."""
    status = await get_system_status(include_tool_versions=True)
    tools_ok = status.get("tools_sidecar", {}).get("status") == "ok"
    return {
        "tools": status.get("tools", {}),
        "status": "ok" if tools_ok else "error",
        "error": None if tools_ok else "Tools sidecar unreachable",
    }


@router.get("/system-status")
async def system_status(_user: User = Depends(get_current_active_user)):
    """Return the authenticated system-status payload used by the frontend."""
    return await get_system_status(include_tool_versions=True)
