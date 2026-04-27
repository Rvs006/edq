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

from app.config import configure_sentry, settings
from app.logging_config import (
    bind_request_log_context,
    configure_logging,
    reset_request_log_context,
)
from app.middleware.rate_limit import check_rate_limit

configure_logging()
configure_sentry()
logger = logging.getLogger("edq.main")
_MAX_CLIENT_ERROR_BODY_BYTES = 16 * 1024
_MAX_CLIENT_ERROR_FIELD_CHARS = 2000
from app.models.database import init_db
from app.security.auth import CSRF_COOKIE, SESSION_COOKIE
from app.routes import (
    auth,
    users,
    projects,
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
    protocol_observer_settings,
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
    "/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/refresh",
    "/api/v1/auth/oidc/callback",
    "/api/v1/health", "/api/v1/health/",
    "/api/v1/client-errors",
}


# ---------------------------------------------------------------------------
# Pure ASGI middleware (avoids BaseHTTPMiddleware per-request task overhead)
# ---------------------------------------------------------------------------

_CSRF_EXEMPT_STRIPPED = {p.rstrip("/") for p in CSRF_EXEMPT_PATHS}


class CSRFMiddleware:
    """CSRF protection as pure ASGI middleware."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        if request.method in CSRF_SAFE_METHODS:
            await self.app(scope, receive, send)
            return

        path = request.url.path.rstrip("/")
        if path in _CSRF_EXEMPT_STRIPPED:
            await self.app(scope, receive, send)
            return

        if not request.url.path.startswith("/api/"):
            await self.app(scope, receive, send)
            return

        session_cookie = request.cookies.get(SESSION_COOKIE)
        if not session_cookie:
            await self.app(scope, receive, send)
            return

        csrf_cookie = request.cookies.get(CSRF_COOKIE)
        csrf_header = request.headers.get("X-CSRF-Token")

        if not csrf_cookie or not csrf_header:
            response = JSONResponse(status_code=403, content={"detail": "CSRF token missing"})
            await response(scope, receive, send)
            return

        if csrf_cookie != csrf_header:
            response = JSONResponse(status_code=403, content={"detail": "CSRF token mismatch"})
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


def _upsert_header(headers: list[tuple[bytes, bytes]], name: bytes, value: bytes) -> list[tuple[bytes, bytes]]:
    """Replace an existing header value or append it when absent."""
    lowered = name.lower()
    filtered = [(k, v) for k, v in headers if k.lower() != lowered]
    filtered.append((name, value))
    return filtered


def _merge_csv_header(
    headers: list[tuple[bytes, bytes]],
    name: bytes,
    values: list[bytes],
) -> list[tuple[bytes, bytes]]:
    """Merge comma-separated header tokens without clobbering existing values."""
    lowered = name.lower()
    merged: list[str] = []
    seen: set[str] = set()
    kept_headers: list[tuple[bytes, bytes]] = []

    for key, value in headers:
        if key.lower() != lowered:
            kept_headers.append((key, value))
            continue
        for token in value.decode("latin-1").split(","):
            normalized = token.strip()
            if not normalized:
                continue
            lowered_token = normalized.lower()
            if lowered_token not in seen:
                merged.append(normalized)
                seen.add(lowered_token)

    for raw in values:
        normalized = raw.decode("latin-1").strip()
        if not normalized:
            continue
        lowered_token = normalized.lower()
        if lowered_token not in seen:
            merged.append(normalized)
            seen.add(lowered_token)

    kept_headers.append((name, ", ".join(merged).encode("latin-1")))
    return kept_headers


class RequestIDMiddleware:
    """Attach a unique request ID to every request/response cycle."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        request_id = headers.get(b"x-request-id", b"").decode() or str(uuid.uuid4())
        log_context_tokens = bind_request_log_context(
            request_id,
            method=scope.get("method"),
            path=scope.get("path"),
        )
        scope.setdefault("state", {})
        if isinstance(scope["state"], dict):
            scope["state"]["request_id"] = request_id
        scope["_request_id"] = request_id

        async def send_with_request_id(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers = _upsert_header(headers, b"x-request-id", request_id.encode())
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            reset_request_log_context(log_context_tokens)


class SecurityHeadersMiddleware:
    """Attach baseline security headers without BaseHTTPMiddleware overhead."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]

        async def send_with_security_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers = _upsert_header(headers, b"x-content-type-options", b"nosniff")
                headers = _upsert_header(headers, b"x-frame-options", b"DENY")
                headers = _upsert_header(headers, b"x-xss-protection", b"1; mode=block")
                headers = _upsert_header(headers, b"referrer-policy", b"strict-origin-when-cross-origin")
                headers = _upsert_header(
                    headers,
                    b"content-security-policy",
                    (
                        b"default-src 'self'; "
                        b"script-src 'self'; "
                        b"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                        b"img-src 'self' data: blob:; "
                        b"connect-src 'self' ws: wss:; "
                        b"font-src 'self' https://fonts.gstatic.com; "
                        b"object-src 'none'; "
                        b"base-uri 'self'; "
                        b"form-action 'self'; "
                        b"frame-ancestors 'none'; "
                        b"upgrade-insecure-requests"
                    ),
                )
                headers = _upsert_header(
                    headers,
                    b"permissions-policy",
                    b"camera=(), microphone=(), geolocation=(), payment=(), usb=(), bluetooth=(), serial=()",
                )
                if settings.COOKIE_SECURE:
                    headers = _upsert_header(
                        headers,
                        b"strict-transport-security",
                        b"max-age=31536000; includeSubDomains",
                    )
                if path.startswith("/api/"):
                    headers = _merge_csv_header(
                        headers,
                        b"vary",
                        [b"Origin", b"Cookie", b"Authorization"],
                    )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_security_headers)


# Only the public health probe benefits from short caching.
_CACHEABLE_API_PATHS: set[str] = set()


class APICacheControlMiddleware:
    """Set smart Cache-Control headers for API responses.

    Read-only endpoints get short caching; everything else gets no-store.
    Replaces the removed SecurityHeadersMiddleware's blanket no-store.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        if not path.startswith("/api/"):
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        is_cacheable = method == "GET" and path in _CACHEABLE_API_PATHS

        async def send_with_cache(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                if is_cacheable:
                    headers = _upsert_header(
                        headers,
                        b"cache-control",
                        b"public, max-age=30, stale-while-revalidate=60",
                    )
                else:
                    headers = _upsert_header(headers, b"cache-control", b"no-store")
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_cache)


class HTTPSRedirectMiddleware:
    """Redirect HTTP to HTTPS in production when COOKIE_SECURE=true."""

    EXEMPT_PATHS = {
        "/api/health",
        "/api/health/",
        "/api/v1/health",
        "/api/v1/health/",
        "/health",
    }

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        headers = dict(scope.get("headers", []))
        proto = headers.get(b"x-forwarded-proto", b"").decode() or request.url.scheme
        path = scope["path"]

        if proto == "http" and path not in self.EXEMPT_PATHS:
            response = JSONResponse(
                status_code=307,
                headers={"Location": str(request.url.replace(scheme="https"))},
                content={"detail": "Redirecting to HTTPS"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


class LegacyAPIRewriteMiddleware:
    """Transparently rewrite /api/* to /api/v1/* for backward compatibility."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            path = scope["path"]
            if path.startswith("/api/") and not path.startswith("/api/v1/"):
                scope["path"] = "/api/v1" + path[4:]
        await self.app(scope, receive, send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[EDQ] Frontend directory: {FRONTEND_DIR} (exists: {os.path.isdir(FRONTEND_DIR)})")
    await init_db()
    admin_created = _seed_on_startup()
    # If the admin user was just created by the sync engine, re-sync the
    # password hash through the async engine so that API requests (which use
    # the async connection) can verify it.  This fixes a SQLite WAL isolation
    # issue where the async connection cannot see uncommitted/uncheckpointed
    # writes made by the separate sync connection.
    from init_db import should_seed_local_test_users
    force_local_admin_password = should_seed_local_test_users()
    if admin_created or force_local_admin_password:
        await _ensure_admin_password_synced(force_reset=force_local_admin_password)
    await _ensure_local_test_users_synced()
    await _load_protocol_observer_settings_from_db()
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


def _seed_on_startup() -> bool:
    """Run synchronous seed logic (idempotent) after tables are created.

    Returns True if the admin user was newly created (first boot).
    """
    from init_db import init_db as seed_db
    return seed_db()


async def _ensure_admin_password_synced(force_reset: bool = False) -> None:
    """Re-write the admin password hash through the async engine.

    On first boot the admin user is created by init_db.py using a *sync*
    SQLAlchemy session.  The running server uses an *async* engine which
    holds a separate SQLite connection.  Due to WAL isolation the async
    connection may not see the sync write until a checkpoint occurs.

    This function reads the admin row through the async engine and, if the
    password does not verify, re-hashes and writes it so the async
    connection's own WAL view is authoritative.

    Only called when the admin was just created (first run / fresh DB).
    On subsequent restarts the admin already exists in the DB and the
    password is left untouched — this avoids overwriting a password that
    was changed by the user, especially when INITIAL_ADMIN_PASSWORD is
    auto-generated and differs each restart.
    """
    from app.models.database import async_session
    from app.models.user import User
    from app.security.auth import hash_password, verify_password
    from app.config import settings
    from sqlalchemy import select

    async with async_session() as db:
        result = await db.execute(select(User).where(User.username == "admin"))
        admin = result.scalar_one_or_none()
        if admin is None:
            # Admin not visible to async engine at all — write a fresh row
            import uuid
            admin = User(
                id=str(uuid.uuid4()),
                username="admin",
                email="admin@electracom.co.uk",
                password_hash=hash_password(settings.INITIAL_ADMIN_PASSWORD),
                full_name="System Administrator",
                role="admin",
                is_active=True,
            )
            db.add(admin)
            await db.commit()
            print("[EDQ] Admin user created through async engine (WAL isolation workaround)")
        elif not verify_password(settings.INITIAL_ADMIN_PASSWORD, admin.password_hash):
            # Row visible but hash doesn't match (stale WAL page) — re-hash
            admin.password_hash = hash_password(settings.INITIAL_ADMIN_PASSWORD)
            await db.commit()
            print("[EDQ] Admin password re-synced through async engine (WAL isolation workaround)")
        else:
            print("[EDQ] Admin password verified OK through async engine")


async def _ensure_local_test_users_synced() -> None:
    """Make deterministic local test users visible to the async API engine."""
    from init_db import LOCAL_TEST_USERS, should_seed_local_test_users

    if not should_seed_local_test_users():
        return

    from app.models.database import async_session
    from app.models.user import User
    from app.security.auth import hash_password, verify_password
    from sqlalchemy import func, select

    async with async_session() as db:
        changed = False
        for spec in LOCAL_TEST_USERS:
            result = await db.execute(
                select(User).where(func.lower(User.username) == spec["username"].casefold())
            )
            user = result.scalar_one_or_none()

            if user is None:
                import uuid

                user = User(
                    id=str(uuid.uuid4()),
                    username=spec["username"],
                    email=spec["email"],
                    password_hash=hash_password(spec["password"]),
                    full_name=spec["full_name"],
                    role=spec["role"],
                    is_active=True,
                )
                db.add(user)
                changed = True
                continue

            if user.username != spec["username"]:
                user.username = spec["username"]
                changed = True
            if user.email != spec["email"]:
                user.email = spec["email"]
                changed = True
            if not verify_password(spec["password"], user.password_hash):
                user.password_hash = hash_password(spec["password"])
                changed = True
            if str(user.role) != spec["role"]:
                user.role = spec["role"]
                changed = True
            if user.full_name != spec["full_name"]:
                user.full_name = spec["full_name"]
                changed = True
            if not user.is_active:
                user.is_active = True
                changed = True
            if user.failed_login_attempts:
                user.failed_login_attempts = 0
                changed = True
            if user.locked_until is not None:
                user.locked_until = None
                changed = True

        if changed:
            await db.commit()
            print("[EDQ] Local test users synced through async engine")


async def _load_protocol_observer_settings_from_db() -> None:
    from sqlalchemy import select

    from app.models.database import async_session
    from app.models.protocol_observer_settings import ProtocolObserverSettings
    from app.services.protocol_observer import apply_protocol_observer_settings

    async with async_session() as db:
        result = await db.execute(select(ProtocolObserverSettings).limit(1))
        row = result.scalar_one_or_none()
        if not row:
            return
        apply_protocol_observer_settings({
            "enabled": row.enabled,
            "bind_host": row.bind_host,
            "timeout_seconds": row.timeout_seconds,
            "dns_port": row.dns_port,
            "ntp_port": row.ntp_port,
            "dhcp_port": row.dhcp_port,
            "dhcp_offer_ip": row.dhcp_offer_ip,
            "dhcp_subnet_mask": row.dhcp_subnet_mask,
            "dhcp_router_ip": row.dhcp_router_ip,
            "dhcp_dns_server": row.dhcp_dns_server,
            "dhcp_lease_seconds": row.dhcp_lease_seconds,
        })


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
        if settings.SENTRY_DSN:
            try:
                import sentry_sdk

                sentry_sdk.set_tag("request_id", getattr(request.state, "request_id", ""))
                sentry_sdk.capture_exception(exc)
            except Exception:
                logger.debug("Failed to capture exception in Sentry", exc_info=True)
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    app.add_middleware(CSRFMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(APICacheControlMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(LegacyAPIRewriteMiddleware)

    # Redirect HTTP → HTTPS in production
    if settings.COOKIE_SECURE:
        app.add_middleware(HTTPSRedirectMiddleware)

    # Build the list of (router, suffix, tag) tuples for all API routes
    _api_routes = [
        (auth.router, "/auth", "Authentication"),
        (users.router, "/users", "Users"),
        (projects.router, "/projects", "Projects"),
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
        (protocol_observer_settings.router, "/settings", "Settings"),
        (scan_schedules.router, "/scan-schedules", "Scan Schedules"),
        (authorized_networks.router, "/authorized-networks", "Authorized Networks"),
        (two_factor.router, "/auth/2fa", "Two-Factor Auth"),
        (oidc.router, "/auth/oidc", "OIDC / SSO"),
    ]

    # Mount under /api/v1/ as canonical prefix.
    # LegacyAPIRewriteMiddleware transparently rewrites /api/* → /api/v1/*
    for rtr, suffix, tag in _api_routes:
        app.include_router(rtr, prefix=f"/api/v1{suffix}", tags=[tag])

    @app.post("/api/v1/client-errors", include_in_schema=False)
    async def receive_client_error(request: Request):
        """Receive frontend error reports via navigator.sendBeacon."""
        try:
            check_rate_limit(request, max_requests=30, window_seconds=60, action="client_error")
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > _MAX_CLIENT_ERROR_BODY_BYTES:
                        return Response(status_code=413)
                except ValueError:
                    return Response(status_code=400)
            body = await request.body()
            if len(body) > _MAX_CLIENT_ERROR_BODY_BYTES:
                return Response(status_code=413)
            import json
            data = json.loads(body)

            def _safe_field(name: str, default: str = "") -> str:
                value = data.get(name, default)
                if value is None:
                    return default
                return str(value)[:_MAX_CLIENT_ERROR_FIELD_CHARS]

            logger.warning(
                "Frontend error at %s: %s",
                _safe_field("url", "unknown"),
                _safe_field("message", "unknown"),
            )
            already_captured = bool(data.get("capturedByFrontendSentry"))
            if settings.SENTRY_DSN and not already_captured:
                try:
                    import sentry_sdk

                    with sentry_sdk.push_scope() as scope:
                        scope.set_tag("source", "frontend")
                        scope.set_tag("request_id", getattr(request.state, "request_id", ""))
                        scope.set_context(
                            "frontend_error",
                            {
                                "url": _safe_field("url", "unknown"),
                                "message": _safe_field("message", "unknown"),
                                "stack": _safe_field("stack"),
                                "component_stack": _safe_field("componentStack"),
                                "timestamp": _safe_field("timestamp"),
                                "user_agent": request.headers.get("user-agent", ""),
                                "telemetry": str(data.get("telemetry", ""))[:_MAX_CLIENT_ERROR_FIELD_CHARS],
                            },
                        )
                        sentry_sdk.capture_message(
                            f"Frontend error: {_safe_field('message', 'unknown error')}",
                            level="error",
                        )
                except Exception:
                    logger.debug("Failed to forward frontend error to Sentry", exc_info=True)
        except Exception as e:
            logger.debug("Failed to log client error: %s", e)
        return Response(status_code=204)

    if os.path.isdir(FRONTEND_DIR):
        assets_dir = os.path.join(FRONTEND_DIR, "assets")
        if os.path.isdir(assets_dir):
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/{full_path:path}")
        async def serve_spa(request: Request, full_path: str):
            if full_path.startswith("api/") or full_path in ("docs", "redoc", "openapi.json"):
                return JSONResponse(status_code=404, content={"detail": "Not Found"})
            from pathlib import Path
            file_path = os.path.join(FRONTEND_DIR, full_path)
            resolved = Path(file_path).resolve()
            if not resolved.is_relative_to(Path(FRONTEND_DIR).resolve()):
                return JSONResponse(status_code=404, content={"detail": "Not Found"})
            if full_path and os.path.isfile(file_path):
                return FileResponse(file_path)
            return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

    return app


app = create_app()
