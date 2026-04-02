"""Helpers for building a consistent system-status payload."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.config import settings
from app.models.database import async_session
from app.services.tools_client import tools_client

TOOL_KEYS = ("nmap", "testssl", "ssh_audit", "hydra", "nikto", "snmpwalk")


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
    versions: dict[str, str] = {}

    try:
        result = await tools_client.versions()
        raw_versions = result.get("versions", {}) if isinstance(result, dict) else {}
        versions = {
            key: str(raw_versions.get(key, "unavailable"))
            for key in TOOL_KEYS
        }
    except Exception:
        tools_status = "error"
        if include_tool_versions:
            versions = {key: "unavailable" for key in TOOL_KEYS}

    overall = "ok" if database_status == "ok" and tools_status == "ok" else "degraded"

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

    if include_tool_versions:
        payload["tools"] = versions

    return payload
