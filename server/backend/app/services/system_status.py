"""Helpers for building a consistent system-status payload."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.config import settings
from app.models.database import async_session
from app.services.tools_client import tools_client

TOOL_KEYS = ("nmap", "testssl", "ssh_audit", "hydra", "nikto", "snmpwalk")
_TOOLS_VERSION_CACHE_TTL = 300.0
_tools_version_cache: dict[str, Any] = {"versions": None, "status": None, "message": None, "ts": 0.0}


async def _get_database_status() -> str:
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "error"


async def get_system_status(include_tool_versions: bool = True) -> dict[str, Any]:
    """Return the live status of the backend dependencies."""
    database_status = await _get_database_status()
    tools_status = "ok"
    tools_message: str | None = None
    versions: dict[str, str] = {}

    # Check if tools sidecar is configured at all
    _tools_url = (settings.TOOLS_SIDECAR_URL or "").strip()
    _tools_configured = bool(_tools_url) and _tools_url not in (
        "http://localhost:0",
        "http://tools:0",
        "",
    )

    if not _tools_configured:
        tools_status = "not_configured"
        tools_message = "Tools sidecar URL is not configured. Manual tests are still available."
        if include_tool_versions:
            versions = {key: "not_configured" for key in TOOL_KEYS}
    else:
        cached_versions = _tools_version_cache.get("versions")
        try:
            result = await asyncio.wait_for(
                tools_client.versions(),
                timeout=8.0,
            )
            raw_versions = result.get("versions", {}) if isinstance(result, dict) else {}
            versions = {
                key: str(raw_versions.get(key, "unavailable"))
                for key in TOOL_KEYS
            }
            _tools_version_cache["versions"] = dict(versions)
            _tools_version_cache["status"] = "ok"
            _tools_version_cache["message"] = None
            _tools_version_cache["ts"] = datetime.now(timezone.utc).timestamp()
        except asyncio.TimeoutError:
            tools_status = "unavailable"
            tools_message = "Tools sidecar did not respond within 8s. Automated tests may be delayed."
            if include_tool_versions:
                if cached_versions is not None:
                    versions = dict(cached_versions)
                    tools_message = "Using cached tool versions; live version probe timed out."
                else:
                    versions = {key: "unavailable" for key in TOOL_KEYS}
        except Exception:
            tools_status = "unavailable"
            tools_message = "Tools sidecar is unreachable. Automated tests will not run."
            if include_tool_versions:
                if cached_versions is not None:
                    versions = dict(cached_versions)
                    tools_message = "Using cached tool versions; live sidecar probe failed."
                else:
                    versions = {key: "unavailable" for key in TOOL_KEYS}

    # The app is fully functional without tools — only mark degraded when the
    # database is down.  Tools being unreachable is a warning, not an error.
    overall = "ok"
    if database_status != "ok" or tools_status == "unavailable":
        overall = "degraded"

    payload: dict[str, Any] = {
        "status": overall,
        "app_name": settings.APP_NAME,
        "app_version": settings.APP_VERSION,
        "debug": settings.DEBUG,
        "ai_enabled": bool(settings.AI_API_KEY),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "backend": {"status": "ok"},
        "database": {"status": database_status},
        "tools_sidecar": {"status": tools_status},
    }

    if tools_message:
        payload["tools_sidecar"]["message"] = tools_message

    if include_tool_versions:
        payload["tools"] = versions

    return payload
