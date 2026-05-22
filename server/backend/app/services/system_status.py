"""Helpers for building a consistent system-status payload."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.config import settings
from app.models.database import async_session
from app.services.tools_client import tools_client

TOOL_KEYS = ("nmap", "testssl", "ssh_audit", "hydra", "nikto", "snmpwalk")
_TOOLS_VERSION_CACHE_TTL = 300.0
_TOOLS_UPDATE_CACHE_TTL = 3600.0
_tools_version_cache: dict[str, Any] = {"versions": None, "status": None, "message": None, "ts": 0.0}
_tools_update_cache: dict[str, Any] = {"updates": None, "ts": 0.0}
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _clean_tool_version(value: Any) -> str:
    text_value = _ANSI_ESCAPE_RE.sub("", str(value or "unavailable"))
    for line in text_value.splitlines():
        line = line.strip()
        if line and any(char.isalnum() for char in line):
            return line[:100]
    return "installed"


async def _get_database_status() -> str:
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "error"


def _scanner_updates_unavailable(status: str, message: str) -> dict[str, Any]:
    return {
        "status": status,
        "image_rebuild_recommended": None,
        "tools": {},
        "message": message,
    }


async def _get_scanner_update_status(tools_configured: bool, tools_available: bool) -> dict[str, Any]:
    if not tools_configured:
        return _scanner_updates_unavailable(
            "not_configured",
            "Scanner update status is unavailable because the tools sidecar is not configured.",
        )
    if not tools_available:
        return _scanner_updates_unavailable(
            "unavailable",
            "Scanner update status is unavailable because the tools sidecar is unreachable.",
        )

    cached_updates = _tools_update_cache.get("updates")
    cached_at = float(_tools_update_cache.get("ts") or 0.0)
    now_ts = datetime.now(timezone.utc).timestamp()
    if isinstance(cached_updates, dict) and (now_ts - cached_at) < _TOOLS_UPDATE_CACHE_TTL:
        return dict(cached_updates)

    try:
        result = await asyncio.wait_for(tools_client.check_updates(), timeout=5.0)
    except Exception:
        if isinstance(cached_updates, dict):
            cached = dict(cached_updates)
            cached["message"] = "Using cached scanner update status; live update check failed."
            return cached
        return _scanner_updates_unavailable(
            "unknown",
            "Scanner update status could not be checked. Re-run system status or rebuild the scanner image manually.",
        )

    tools = result.get("tools", {}) if isinstance(result, dict) else {}
    rebuild_recommended = bool(result.get("image_rebuild_recommended")) if isinstance(result, dict) else False
    updates = {
        "status": "outdated" if rebuild_recommended else "ok",
        "image_rebuild_recommended": rebuild_recommended,
        "tools": tools,
        "message": (
            result.get("update_instructions")
            if isinstance(result, dict) and result.get("update_instructions")
            else (
                "Rebuild the scanner image to update scanner tools."
                if rebuild_recommended
                else "Scanner tools match the image's pinned latest-known versions."
            )
        ),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    _tools_update_cache["updates"] = dict(updates)
    _tools_update_cache["ts"] = now_ts
    return updates


async def get_system_status(include_tool_versions: bool = True) -> dict[str, Any]:
    """Return the live status of the backend dependencies."""
    database_status = await _get_database_status()
    ai_status = settings.get_ai_provider_status()
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
        cached_at = float(_tools_version_cache.get("ts") or 0.0)
        now_ts = datetime.now(timezone.utc).timestamp()
        cached_fresh = cached_versions is not None and (now_ts - cached_at) < _TOOLS_VERSION_CACHE_TTL
        try:
            health = await asyncio.wait_for(tools_client.health(), timeout=3.0)
            raw_tool_health = health.get("tools", {}) if isinstance(health, dict) else {}
            missing = [key for key in TOOL_KEYS if not raw_tool_health.get(key)]
            if missing:
                tools_status = "unavailable"
                tools_message = f"Required scanner tools are missing: {', '.join(missing)}."

            if include_tool_versions and cached_fresh:
                versions = dict(cached_versions)
            elif include_tool_versions:
                try:
                    result = await asyncio.wait_for(tools_client.versions(), timeout=3.0)
                    raw_versions = result.get("versions", {}) if isinstance(result, dict) else {}
                    versions = {
                        key: _clean_tool_version(raw_versions.get(key, "unavailable"))
                        for key in TOOL_KEYS
                    }
                    _tools_version_cache["versions"] = dict(versions)
                    _tools_version_cache["status"] = "ok"
                    _tools_version_cache["message"] = None
                    _tools_version_cache["ts"] = now_ts
                except asyncio.TimeoutError:
                    if cached_versions is not None:
                        versions = dict(cached_versions)
                        tools_message = "Using cached tool versions; live version probe timed out."
                    else:
                        versions = {
                            key: "installed" if raw_tool_health.get(key) else "unavailable"
                            for key in TOOL_KEYS
                        }
                        tools_message = "Scanner health is OK; detailed version probe timed out."
                except Exception:
                    if cached_versions is not None:
                        versions = dict(cached_versions)
                        tools_message = "Using cached tool versions; live version probe failed."
                    else:
                        versions = {
                            key: "installed" if raw_tool_health.get(key) else "unavailable"
                            for key in TOOL_KEYS
                        }
                        tools_message = "Scanner health is OK; detailed version probe failed."
        except asyncio.TimeoutError:
            tools_status = "unavailable"
            tools_message = "Tools sidecar health probe did not respond within 3s. Automated tests may be delayed."
            if include_tool_versions:
                if cached_versions is not None:
                    versions = dict(cached_versions)
                    tools_message = "Using cached tool versions; live sidecar health probe timed out."
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
    scanner_updates = await _get_scanner_update_status(
        _tools_configured,
        tools_status == "ok",
    )

    overall = "ok"
    if database_status != "ok" or tools_status == "unavailable":
        overall = "degraded"

    payload: dict[str, Any] = {
        "status": overall,
        "app_name": settings.APP_NAME,
        "app_version": settings.APP_VERSION,
        "debug": settings.DEBUG,
        "ai_enabled": bool(ai_status["enabled"]),
        "ai_status": ai_status["status"],
        "ai_message": ai_status["message"],
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "backend": {"status": "ok"},
        "database": {"status": database_status},
        "tools_sidecar": {"status": tools_status},
        "scanner_updates": scanner_updates,
    }

    if tools_message:
        payload["tools_sidecar"]["message"] = tools_message

    if include_tool_versions:
        payload["tools"] = versions

    return payload
