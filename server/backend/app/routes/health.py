"""Health check route — database + tools sidecar status + Prometheus metrics."""

import time

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text, func, select

from app.models.database import async_session
from app.models.user import User
from app.security.auth import get_current_active_user

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
    db_status = "connected"
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        db_status = "unreachable"

    overall = "ok" if db_status == "connected" else "degraded"

    return {
        "status": overall,
    }


@router.get("/metrics", response_class=Response)
async def prometheus_metrics():
    """Prometheus-compatible metrics endpoint. No auth (scraped by monitoring)."""
    db_ok = 1
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        db_ok = 0

    uptime = time.time() - _metrics["startup_time"]

    # Count table rows for operational metrics
    table_counts = {}
    try:
        async with async_session() as session:
            for table in ["users", "devices", "test_runs", "audit_logs", "network_scans"]:
                try:
                    result = await session.execute(text(f"SELECT COUNT(*) FROM {table}"))
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
    from app.services.tools_client import tools_client
    try:
        result = await tools_client.versions()
        return {"tools": result.get("versions", {}), "status": "ok"}
    except Exception:
        return {"tools": {}, "error": "Tools sidecar unreachable", "status": "error"}
