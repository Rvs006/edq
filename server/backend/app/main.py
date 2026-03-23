"""EDQ — Electracom Device Qualifier: FastAPI Application Factory."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import os
from pathlib import Path

from app.config import settings
from app.models.database import init_db
from app.routes import (
    auth,
    users,
    devices,
    device_profiles,
    test_templates,
    test_runs,
    test_results,
    reports,
    agents,
    whitelists,
    discovery,
    audit_logs,
    admin,
    synopsis,
    websocket_routes,
    health,
)


# Path to built frontend — resolve from this file's location
_THIS_DIR = Path(__file__).resolve().parent  # app/
_BACKEND_DIR = _THIS_DIR.parent  # server/backend/
_PROJECT_ROOT = _BACKEND_DIR.parent.parent  # edq/
FRONTEND_DIR = str(_PROJECT_ROOT / "frontend" / "dist")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown lifecycle."""
    print(f"[EDQ] Frontend directory: {FRONTEND_DIR} (exists: {os.path.isdir(FRONTEND_DIR)})")
    await init_db()
    from app.services.test_engine import recover_orphaned_runs
    await recover_orphaned_runs()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="EDQ — Electracom Device Qualifier",
        description="Automated network security testing platform for smart building IP devices",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API Routes
    app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
    app.include_router(users.router, prefix="/api/users", tags=["Users"])
    app.include_router(devices.router, prefix="/api/devices", tags=["Devices"])
    app.include_router(device_profiles.router, prefix="/api/device-profiles", tags=["Device Profiles"])
    app.include_router(test_templates.router, prefix="/api/test-templates", tags=["Test Templates"])
    app.include_router(test_runs.router, prefix="/api/test-runs", tags=["Test Runs"])
    app.include_router(test_results.router, prefix="/api/test-results", tags=["Test Results"])
    app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])
    app.include_router(agents.router, prefix="/api/agents", tags=["Agents"])
    app.include_router(whitelists.router, prefix="/api/whitelists", tags=["Protocol Whitelists"])
    app.include_router(discovery.router, prefix="/api/discovery", tags=["Discovery"])
    app.include_router(audit_logs.router, prefix="/api/audit-logs", tags=["Audit Logs"])
    app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
    app.include_router(synopsis.router, prefix="/api/synopsis", tags=["AI Synopsis"])
    app.include_router(websocket_routes.router, prefix="/api/ws", tags=["WebSocket"])
    app.include_router(health.router, prefix="/api/health", tags=["Health"])

    # Serve built frontend static files
    if os.path.isdir(FRONTEND_DIR):
        # Mount assets directory for JS/CSS/images
        assets_dir = os.path.join(FRONTEND_DIR, "assets")
        if os.path.isdir(assets_dir):
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        # SPA fallback: serve index.html for all non-API routes
        @app.get("/{full_path:path}")
        async def serve_spa(request: Request, full_path: str):
            # Don't serve index.html for API or docs routes
            if full_path.startswith("api/") or full_path in ("docs", "redoc", "openapi.json"):
                return {"detail": "Not Found"}
            # Check if a static file exists
            file_path = os.path.join(FRONTEND_DIR, full_path)
            if full_path and os.path.isfile(file_path):
                return FileResponse(file_path)
            # Fallback to index.html for SPA routing
            return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

    return app


app = create_app()
