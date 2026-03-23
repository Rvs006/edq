"""EDQ — Electracom Device Qualifier: FastAPI Application Factory."""

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
import os
from pathlib import Path

from app.config import settings
from app.models.database import init_db
from app.security.auth import CSRF_COOKIE, SESSION_COOKIE
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
    network_scan,
    test_plans,
)


_THIS_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _THIS_DIR.parent
_PROJECT_ROOT = _BACKEND_DIR.parent.parent
FRONTEND_DIR = str(_PROJECT_ROOT / "frontend" / "dist")

CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_EXEMPT_PATHS = {"/api/auth/login", "/api/auth/register", "/api/health", "/api/health/"}


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in CSRF_SAFE_METHODS:
            return await call_next(request)

        path = request.url.path.rstrip("/")
        if path in {p.rstrip("/") for p in CSRF_EXEMPT_PATHS}:
            return await call_next(request)

        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        session_cookie = request.cookies.get(SESSION_COOKIE)
        if not session_cookie:
            return await call_next(request)

        csrf_cookie = request.cookies.get(CSRF_COOKIE)
        csrf_header = request.headers.get("X-CSRF-Token")

        if not csrf_cookie or not csrf_header:
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token missing"},
            )

        if csrf_cookie != csrf_header:
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token mismatch"},
            )

        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[EDQ] Frontend directory: {FRONTEND_DIR} (exists: {os.path.isdir(FRONTEND_DIR)})")
    await init_db()
    _seed_on_startup()
    try:
        from app.services.test_engine import recover_orphaned_runs
        await recover_orphaned_runs()
    except Exception as e:
        print(f"[EDQ] Warning: could not recover orphaned runs: {e}")
    yield


def _seed_on_startup() -> None:
    """Run synchronous seed logic (idempotent) after tables are created."""
    try:
        from init_db import init_db as seed_db
        seed_db()
    except Exception as e:
        print(f"[EDQ] Warning: seed data error (may be already seeded): {e}")


def create_app() -> FastAPI:
    app = FastAPI(
        title="EDQ — Electracom Device Qualifier",
        description="Automated network security testing platform for smart building IP devices",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:80", "http://localhost"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*", "X-CSRF-Token"],
        expose_headers=["X-CSRF-Token"],
    )

    app.add_middleware(CSRFMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

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
    app.include_router(network_scan.router, prefix="/api/network-scan", tags=["Network Scan"])
    app.include_router(test_plans.router, prefix="/api/test-plans", tags=["Test Plans"])

    if os.path.isdir(FRONTEND_DIR):
        assets_dir = os.path.join(FRONTEND_DIR, "assets")
        if os.path.isdir(assets_dir):
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/{full_path:path}")
        async def serve_spa(request: Request, full_path: str):
            if full_path.startswith("api/") or full_path in ("docs", "redoc", "openapi.json"):
                return {"detail": "Not Found"}
            file_path = os.path.join(FRONTEND_DIR, full_path)
            if full_path and os.path.isfile(file_path):
                return FileResponse(file_path)
            return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

    return app


app = create_app()
