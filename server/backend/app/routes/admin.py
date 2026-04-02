"""Admin routes — system configuration and management."""

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.config import settings
from app.models.database import get_db
from app.models.user import User
from app.models.device import Device
from app.models.test_run import TestRun
from app.models.agent import Agent
from app.security.auth import require_role
from app.services.system_status import get_system_status
from app.utils.audit import log_security_event
from app.middleware.rate_limit import check_rate_limit

logger = logging.getLogger("edq.routes.admin")

router = APIRouter()


@router.get("/dashboard")
async def admin_dashboard(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin"])),
):
    """Get admin dashboard statistics."""
    users_count = await db.execute(select(func.count(User.id)))
    devices_count = await db.execute(select(func.count(Device.id)))
    test_runs_count = await db.execute(select(func.count(TestRun.id)))
    agents_count = await db.execute(select(func.count(Agent.id)).where(Agent.is_active == True))

    return {
        "users": users_count.scalar() or 0,
        "devices": devices_count.scalar() or 0,
        "test_runs": test_runs_count.scalar() or 0,
        "active_agents": agents_count.scalar() or 0,
    }


@router.get("/system-info")
async def system_info(_: User = Depends(require_role(["admin"]))):
    """Get system information."""
    status = await get_system_status(include_tool_versions=True)
    return {
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "app_version": settings.APP_VERSION,
        "debug": settings.DEBUG,
        "ai_enabled": bool(settings.AI_API_KEY),
        "status": status["status"],
        "checked_at": status["checked_at"],
        "api_status": "Connected" if status["backend"]["status"] == "ok" else "Unavailable",
        "database": "Connected" if status["database"]["status"] == "ok" else "Unavailable",
        "tools_sidecar_status": "Connected" if status["tools_sidecar"]["status"] == "ok" else "Unavailable",
        "tools": status.get("tools", {}),
    }


@router.post("/rotate-tools-key")
async def rotate_tools_key(
    request: Request,
    current_user: User = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    check_rate_limit(request, max_requests=3, window_seconds=300, action="admin_rotate_key")
    """Generate a new tools sidecar API key and push it to the sidecar.

    The new key is returned once — store it securely and update your .env file.
    """
    from app.services.tools_client import tools_client

    new_key = secrets.token_hex(32)

    try:
        await tools_client.rotate_key(new_key)
    except Exception:
        logger.exception("Failed to push new key to tools sidecar")
        raise HTTPException(
            status_code=502,
            detail="Failed to update tools sidecar — key was NOT rotated",
        )

    # Update in-memory config so the backend uses the new key going forward
    settings.TOOLS_API_KEY = new_key

    await log_security_event(
        db, "admin.tools_key_rotated", user_id=current_user.id,
        details={"note": "TOOLS_API_KEY rotated via admin endpoint"},
        request=request,
    )
    logger.info("Admin %s rotated TOOLS_API_KEY", current_user.id)

    return {
        "message": "Tools API key rotated successfully. Update your .env file with the new key.",
        "new_key": new_key,
        "warning": "This key is shown only once. Store it in your .env file.",
    }
