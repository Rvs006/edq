"""Health check route — database + tools sidecar status."""

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.models.database import async_session
from app.models.user import User
from app.security.auth import get_current_active_user

router = APIRouter()


@router.get("")
async def health_check():
    """Public health endpoint for load balancers. No auth required."""
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


@router.get("/tools/versions")
async def tool_versions(_user: User = Depends(get_current_active_user)):
    """Return installed tool versions from the sidecar. Requires authentication."""
    from app.services.tools_client import tools_client
    try:
        result = await tools_client.versions()
        return {"tools": result.get("versions", {}), "status": "ok"}
    except Exception as e:
        return {"tools": {}, "error": str(e), "status": "error"}
