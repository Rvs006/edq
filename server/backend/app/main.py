"""EDQ — Electracom Device Qualifier: FastAPI Application Factory."""

import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.logging_config import configure_logging

configure_logging()
logger = logging.getLogger("edq.main")
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
    cve,
    branding,
    scan_schedules,
    authorized_networks,
    two_factor,
    oidc,
)


_THIS_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _THIS_DIR.parent
_PROJECT_ROOT = _BACKEND_DIR.parent.parent
FRONTEND_DIR = str(_PROJECT_ROOT / "frontend" / "dist")

CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_EXEMPT_PATHS = {
    "/api/auth/login", "/api/auth/register", "/api/auth/refresh",
    "/api/auth/oidc/callback",
    "/api/health", "/api/health/",
    "/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/refresh",
    "/api/v1/auth/oidc/callback",
    "/api/v1/health", "/api/v1/health/",
    "/api/client-errors",
}


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in CSRF_SAFE_METHODS:
            return await call_next(request)

        path = request.url.path.rstrip("/")
        if path in {p.rstrip("/") for p in CSRF_EXEMPT_PATHS}:
            return await call_next(request)

        if not (request.url.path.startswith("/api/")):
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
        if settings.COOKIE_SECURE:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "img-src 'self' data: blob:; "
            "connect-src 'self' ws: wss:; "
            "font-src 'self' https://fonts.gstatic.com; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'; "
            "upgrade-insecure-requests"
        )
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), "
            "usb=(), bluetooth=(), serial=()"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique request ID to every request/response cycle."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """Redirect HTTP to HTTPS in production when COOKIE_SECURE=true.

    Trusts X-Forwarded-Proto from reverse proxy (nginx) to detect the
    original protocol. Does not redirect health checks or internal calls.
    """

    EXEMPT_PATHS = {"/api/health", "/api/v1/health", "/health"}

    async def dispatch(self, request: Request, call_next):
        proto = request.headers.get("X-Forwarded-Proto", request.url.scheme)
        if proto == "http" and request.url.path not in self.EXEMPT_PATHS:
            url = request.url.replace(scheme="https")
            return JSONResponse(
                status_code=301,
                headers={"Location": str(url)},
                content={"detail": "Redirecting to HTTPS"},
            )
        return await call_next(request)


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
    # Start background tasks
    from app.services.scan_scheduler import start_scheduler, stop_scheduler
    from app.services.token_cleanup import start_token_cleanup, stop_token_cleanup
    start_scheduler()
    start_token_cleanup()
    try:
        yield
    finally:
        stop_token_cleanup()
        stop_scheduler()


def _seed_on_startup() -> None:
    """Run synchronous seed logic (idempotent) after tables are created."""
    try:
        from init_db import init_db as seed_db
        seed_db()
    except Exception as e:
        print(f"[EDQ] Warning: seed data error (may be already seeded): {e}")


def create_app() -> FastAPI:
    # Disable Swagger/ReDoc docs in production (enable with DEBUG=true)
    docs_url = "/docs" if settings.DEBUG else None
    redoc_url = "/redoc" if settings.DEBUG else None
    openapi_url = "/openapi.json" if settings.DEBUG else None

    app = FastAPI(
        title="EDQ — Electracom Device Qualifier",
        description="Automated network security testing platform for smart building IP devices",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
        expose_headers=["X-CSRF-Token"],
    )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = []
        for err in exc.errors():
            errors.append({
                "field": ".".join(str(loc) for loc in err.get("loc", [])),
                "message": err.get("msg", "Validation error"),
            })
        return JSONResponse(
            status_code=422,
            content={"detail": "Validation error", "errors": errors},
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    app.add_middleware(CSRFMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIDMiddleware)

    # Redirect HTTP → HTTPS in production
    if settings.COOKIE_SECURE:
        app.add_middleware(HTTPSRedirectMiddleware)

    # Build the list of (router, suffix, tag) tuples for all API routes
    _api_routes = [
        (auth.router, "/auth", "Authentication"),
        (users.router, "/users", "Users"),
        (devices.router, "/devices", "Devices"),
        (device_profiles.router, "/device-profiles", "Device Profiles"),
        (test_templates.router, "/test-templates", "Test Templates"),
        (test_runs.router, "/test-runs", "Test Runs"),
        (test_results.router, "/test-results", "Test Results"),
        (reports.router, "/reports", "Reports"),
        (agents.router, "/agents", "Agents"),
        (whitelists.router, "/whitelists", "Protocol Whitelists"),
        (discovery.router, "/discovery", "Discovery"),
        (audit_logs.router, "/audit-logs", "Audit Logs"),
        (admin.router, "/admin", "Admin"),
        (synopsis.router, "/synopsis", "AI Synopsis"),
        (websocket_routes.router, "/ws", "WebSocket"),
        (health.router, "/health", "Health"),
        (network_scan.router, "/network-scan", "Network Scan"),
        (test_plans.router, "/test-plans", "Test Plans"),
        (cve.router, "/cve", "CVE Lookup"),
        (branding.router, "/settings", "Settings"),
        (scan_schedules.router, "/scan-schedules", "Scan Schedules"),
        (authorized_networks.router, "/authorized-networks", "Authorized Networks"),
        (two_factor.router, "/auth/2fa", "Two-Factor Auth"),
        (oidc.router, "/auth/oidc", "OIDC / SSO"),
    ]

    # Mount under both /api/ (legacy) and /api/v1/ (versioned) for backward compatibility
    for rtr, suffix, tag in _api_routes:
        app.include_router(rtr, prefix=f"/api{suffix}", tags=[tag])
        app.include_router(rtr, prefix=f"/api/v1{suffix}", tags=[f"v1 - {tag}"])

    @app.post("/api/client-errors", include_in_schema=False)
    async def receive_client_error(request: Request):
        """Receive frontend error reports via navigator.sendBeacon."""
        try:
            body = await request.body()
            import json
            data = json.loads(body)
            logger.warning(
                "Frontend error at %s: %s",
                data.get("url", "unknown"),
                data.get("message", "unknown"),
            )
        except Exception:
            pass
        return Response(status_code=204)

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
