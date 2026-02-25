"""Admin routes — system configuration and management."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.database import get_db
from app.models.user import User
from app.models.device import Device
from app.models.test_run import TestRun
from app.models.agent import Agent
from app.security.auth import require_role

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
    from app.config import settings
    return {
        "app_name": settings.APP_NAME,
        "app_version": settings.APP_VERSION,
        "debug": settings.DEBUG,
        "ai_enabled": bool(settings.AI_API_KEY),
    }
