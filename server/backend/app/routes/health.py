"""Health check route — database + tools sidecar status."""

from fastapi import APIRouter
from sqlalchemy import text

from app.models.database import async_session

router = APIRouter()


@router.get("")
async def health_check():
    """Public health endpoint. No auth required."""
    db_status = "connected"
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        db_status = "unreachable"

    tools_status = "unreachable"
    try:
        from app.services.tools_client import tools_client
        result = await tools_client.health()
        if result.get("status") == "healthy":
            tools_status = "healthy"
    except Exception:
        tools_status = "unreachable"

    overall = "ok" if db_status == "connected" else "degraded"

    return {
        "status": overall,
        "database": db_status,
        "tools_sidecar": tools_status,
    }


@router.get("/tools/versions")
async def tool_versions():
    """Return installed tool versions from the sidecar."""
    from app.services.tools_client import tools_client
    try:
        result = await tools_client.versions()
        return {"tools": result.get("versions", {}), "status": "ok"}
    except Exception as e:
        return {"tools": {}, "error": str(e), "status": "error"}
