"""Health check route — database + tools sidecar status + Prometheus metrics."""

import hmac
import logging
import time

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text, func, select

from app.config import settings
from app.models.database import async_session
from app.models.audit_log import AuditLog
from app.models.device import Device
from app.models.network_scan import NetworkScan, NetworkScanStatus
from app.models.project import Project
from app.models.test_result import TestResult, TestVerdict
from app.models.test_run import TestRun
from app.models.user import User
from app.security.auth import get_current_active_user
from app.services.system_status import get_system_status
from app.middleware.rate_limit import check_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter()

# Simple in-process counters for Prometheus metrics
_metrics = {
    "http_requests_total": 0,
    "startup_time": time.time(),
}

# In-process cache for /system-status responses to prevent
# repeated expensive sidecar calls under 30s frontend polling.
_system_status_cache: dict = {"data": None, "ts": 0.0}
_SYSTEM_STATUS_CACHE_TTL = 10.0  # seconds


def _increment_requests():
    _metrics["http_requests_total"] += 1


@router.get("")
async def health_check(request: Request):
    """Public health endpoint for load balancers. No auth required."""
    check_rate_limit(request, max_requests=60, window_seconds=60, action="health")
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

    Returns operational metrics in Prometheus text exposition format.

    When ``METRICS_API_KEY`` is configured, requests must include
    ``Authorization: Bearer <key>``. In cloud/production, an API key is
    required before metrics are exposed.
    """
    # --- auth gate -------------------------------------------------------
    if settings.ENVIRONMENT == "cloud" and not settings.METRICS_API_KEY:
        return JSONResponse(
            status_code=401,
            content={"detail": "METRICS_API_KEY is required in cloud environment"},
        )
    if settings.METRICS_API_KEY:
        auth_header = request.headers.get("Authorization", "")
        if (
            not auth_header.startswith("Bearer ")
            or not hmac.compare_digest(auth_header[7:], settings.METRICS_API_KEY)
        ):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing metrics API key"},
            )

    # --- collect metrics from the database --------------------------------
    db_ok = 1
    devices_total = 0
    total_test_runs = 0
    test_runs_by_status: dict[str, int] = {}
    test_pass_rate = 0.0
    projects_total = 0
    users_total = 0
    scans_active = 0
    total_network_scans = 0
    audit_logs_total = 0

    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("Prometheus metrics health probe failed: %s", exc)
        db_ok = 0

    if db_ok:
        try:
            async with async_session() as session:
                # Devices
                result = await session.execute(select(func.count()).select_from(Device))
                devices_total = result.scalar() or 0

                result = await session.execute(select(func.count()).select_from(TestRun))
                total_test_runs = result.scalar() or 0

                # Test runs grouped by status
                rows = (
                    await session.execute(
                        select(TestRun.status, func.count())
                        .group_by(TestRun.status)
                    )
                ).all()
                for status_val, cnt in rows:
                    key = status_val.value if hasattr(status_val, "value") else str(status_val)
                    test_runs_by_status[key] = cnt

                # Test pass rate (across all completed test results)
                total_judged = await session.execute(
                    select(func.count()).select_from(TestResult).where(
                        TestResult.verdict.in_([
                            TestVerdict.PASS,
                            TestVerdict.FAIL,
                        ])
                    )
                )
                total_judged_count = total_judged.scalar() or 0

                if total_judged_count > 0:
                    passed = await session.execute(
                        select(func.count()).select_from(TestResult).where(
                            TestResult.verdict == TestVerdict.PASS
                        )
                    )
                    passed_count = passed.scalar() or 0
                    test_pass_rate = round(passed_count / total_judged_count, 3)

                # Projects
                result = await session.execute(select(func.count()).select_from(Project))
                projects_total = result.scalar() or 0

                # Users
                result = await session.execute(select(func.count()).select_from(User))
                users_total = result.scalar() or 0

                # Active scans (discovering or scanning)
                result = await session.execute(
                    select(func.count()).select_from(NetworkScan).where(
                        NetworkScan.status.in_([
                            NetworkScanStatus.DISCOVERING,
                            NetworkScanStatus.SCANNING,
                        ])
                    )
                )
                scans_active = result.scalar() or 0

                result = await session.execute(select(func.count()).select_from(NetworkScan))
                total_network_scans = result.scalar() or 0

                result = await session.execute(select(func.count()).select_from(AuditLog))
                audit_logs_total = result.scalar() or 0

        except Exception as exc:
            logger.warning("Failed to collect extended Prometheus metrics: %s", exc)

    uptime = time.time() - _metrics["startup_time"]
    table_counts = {
        "users": users_total,
        "devices": devices_total,
        "test_runs": total_test_runs,
        "audit_logs": audit_logs_total,
        "network_scans": total_network_scans,
    }

    # --- format Prometheus text exposition --------------------------------
    lines: list[str] = [
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
        "",
        "# HELP edq_devices_total Total number of registered devices",
        "# TYPE edq_devices_total gauge",
        f"edq_devices_total {devices_total}",
        "",
        "# HELP edq_test_runs_total Total test runs by status",
        "# TYPE edq_test_runs_total gauge",
    ]
    # Always emit at least the canonical statuses the caller expects
    _CANONICAL_STATUSES = ("completed", "running", "pending", "failed", "cancelled")
    emitted: set[str] = set()
    for st in _CANONICAL_STATUSES:
        lines.append(f'edq_test_runs_total{{status="{st}"}} {test_runs_by_status.get(st, 0)}')
        emitted.add(st)
    for st, cnt in sorted(test_runs_by_status.items()):
        if st not in emitted:
            lines.append(f'edq_test_runs_total{{status="{st}"}} {cnt}')

    lines += [
        "",
        "# HELP edq_test_pass_rate Overall test pass rate",
        "# TYPE edq_test_pass_rate gauge",
        f"edq_test_pass_rate {test_pass_rate}",
        "",
        "# HELP edq_projects_total Total projects",
        "# TYPE edq_projects_total gauge",
        f"edq_projects_total {projects_total}",
        "",
        "# HELP edq_users_total Total users",
        "# TYPE edq_users_total gauge",
        f"edq_users_total {users_total}",
        "",
        "# HELP edq_scans_active Currently active network scans",
        "# TYPE edq_scans_active gauge",
        f"edq_scans_active {scans_active}",
        "",
        "# HELP edq_table_rows Number of rows per table",
        "# TYPE edq_table_rows gauge",
    ]
    for table, count in table_counts.items():
        lines.append(f'edq_table_rows{{table="{table}"}} {count}')

    body = "\n".join(lines) + "\n"
    return Response(
        content=body,
        media_type="text/plain; version=0.0.4; charset=utf-8",
        status_code=200 if db_ok else 503,
    )


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
    """Return the authenticated system-status payload used by the frontend.

    Results are cached in-process for ``_SYSTEM_STATUS_CACHE_TTL`` seconds to
    avoid hammering the tools sidecar when the frontend polls every 30s.
    """
    now = time.time()
    cached = _system_status_cache.get("data")
    if cached is not None and (now - _system_status_cache.get("ts", 0.0)) < _SYSTEM_STATUS_CACHE_TTL:
        return cached
    data = await get_system_status(include_tool_versions=True)
    _system_status_cache["data"] = data
    _system_status_cache["ts"] = now
    return data
