"""Application configuration from environment variables."""

from pathlib import Path
from typing import List
import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings


def _resolve_env_file() -> Path:
    current_file = Path(__file__).resolve()
    parents = current_file.parents

    # Repo checkout layout: <repo>/server/backend/app/config.py
    if len(parents) > 3 and parents[1].name == "backend" and parents[2].name == "server":
        return parents[3] / ".env"

    # Container layout: /app/app/config.py
    return Path("/app/.env")


ROOT_ENV_FILE = _resolve_env_file()
load_dotenv(ROOT_ENV_FILE, override=False)


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "EDQ"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production-use-openssl-rand-hex-32"

    # Database — defaults to SQLite for standalone mode
    DATABASE_URL: str = "sqlite+aiosqlite:///./edq.db"

    # JWT
    JWT_SECRET: str = "change-me-jwt-secret-use-openssl-rand-hex-64"
    JWT_REFRESH_SECRET: str = "change-me-refresh-secret-use-openssl-rand-hex-64"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60  # 1 hour (use refresh tokens for longer sessions)
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000", "http://localhost:8080"]

    # File Storage
    UPLOAD_DIR: str = "./uploads"
    REPORT_DIR: str = "./reports"
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB
    MAX_NESSUS_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB

    # Agent
    AGENT_API_KEY_LENGTH: int = 64
    AGENT_HEARTBEAT_TIMEOUT: int = 300  # 5 minutes

    # AI Synopsis (optional — configure with your preferred LLM provider)
    AI_API_KEY: str = ""
    AI_API_URL: str = ""
    AI_MODEL: str = "gpt-4o"
    AI_MAX_SYNOPSIS_PER_HOUR: int = 10

    # Tools Sidecar
    TOOLS_SIDECAR_URL: str = "http://localhost:8001"
    TOOLS_API_KEY: str = ""  # Shared secret for backend ↔ tools sidecar auth

    # Security
    COOKIE_SECURE: bool = False  # Set True when serving over HTTPS
    COOKIE_SAMESITE: str = "strict"  # "strict" or "lax" — use "lax" if external-link navigation breaks
    INITIAL_ADMIN_PASSWORD: str = ""  # REQUIRED — must be set in .env
    SSL_VERIFY_DEVICES: bool = True  # Set False only if your devices use self-signed certs
    ALLOW_REGISTRATION: bool = False  # Set True to allow public self-registration

    # Metrics
    METRICS_API_KEY: str = ""  # Optional bearer token for /health/metrics. If set, requests must include Authorization: Bearer <key>

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    LOGIN_RATE_LIMIT_PER_MINUTE: int = 15
    REDIS_URL: str = ""  # Optional: redis://host:6379/0 for persistent rate limiting across instances
    ACCOUNT_LOCKOUT_ATTEMPTS: int = 5
    ACCOUNT_LOCKOUT_MINUTES: int = 15

    # OIDC / SSO (optional — Google, Microsoft, Keycloak, or any OIDC provider)
    OIDC_PROVIDER: str = ""  # "google", "microsoft", or "custom"
    OIDC_CLIENT_ID: str = ""
    OIDC_CLIENT_SECRET: str = ""
    OIDC_DISCOVERY_URL: str = ""  # Required for "custom" provider
    OIDC_ALLOWED_DOMAINS: str = ""  # Comma-separated: "electracom.com,example.com"

    # Sentry (optional — error tracking & performance monitoring)
    SENTRY_DSN: str = ""
    SENTRY_ENVIRONMENT: str = "production"
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1

    # Audit log retention
    AUDIT_LOG_RETENTION_DAYS: int = 365  # Auto-delete audit logs older than this

    # Logging
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = str(ROOT_ENV_FILE)
        env_file_encoding = "utf-8"


settings = Settings()

# --- Production safety checks ---

import secrets as _secrets
import sys as _sys
import warnings as _warnings

# INITIAL_ADMIN_PASSWORD must be set explicitly
if not settings.INITIAL_ADMIN_PASSWORD:
    _generated = _secrets.token_urlsafe(16)
    settings.INITIAL_ADMIN_PASSWORD = _generated
    print(
        f"\n[EDQ SECURITY] INITIAL_ADMIN_PASSWORD was not set. "
        f"Generated one-time password: {_generated}\n"
        f"Set INITIAL_ADMIN_PASSWORD in your .env file for future starts.\n",
        file=_sys.stderr,
    )

# Reject placeholder or CHANGE_ME secrets — app must not start with unsafe values
_PLACEHOLDER_PREFIXES = ("change-me", "CHANGE_ME")
_SECRET_FIELDS = {
    "SECRET_KEY": settings.SECRET_KEY,
    "JWT_SECRET": settings.JWT_SECRET,
    "JWT_REFRESH_SECRET": settings.JWT_REFRESH_SECRET,
}
for _name, _value in _SECRET_FIELDS.items():
    if any(_value.startswith(p) for p in _PLACEHOLDER_PREFIXES):
        _msg = (
            f"[EDQ SECURITY] {_name} is still set to a placeholder value. "
            "Generate a strong secret with: openssl rand -hex 64"
        )
        raise RuntimeError(_msg)

if not settings.TOOLS_API_KEY or any(
    settings.TOOLS_API_KEY.startswith(p) for p in _PLACEHOLDER_PREFIXES
):
    _msg = (
        "[EDQ SECURITY] TOOLS_API_KEY is not set or is a placeholder. "
        "The tools sidecar requires a valid key. Generate with: openssl rand -hex 32"
    )
    if not settings.DEBUG:
        raise RuntimeError(_msg)
    _warnings.warn(_msg, stacklevel=2)

_localhost_origins = [o for o in settings.CORS_ORIGINS if "localhost" in o or "127.0.0.1" in o]
_localhost_only = bool(settings.CORS_ORIGINS) and len(_localhost_origins) == len(settings.CORS_ORIGINS)
if _localhost_origins and not settings.DEBUG and not _localhost_only:
    # Auto-strip localhost origins in production to prevent accidental CORS bypass
    settings.CORS_ORIGINS = [o for o in settings.CORS_ORIGINS if o not in _localhost_origins]
    _warnings.warn(
        "[EDQ SECURITY] Stripped localhost origins from CORS_ORIGINS in production: "
        f"{_localhost_origins}. Only non-localhost origins remain.",
        stacklevel=2,
    )

if not settings.COOKIE_SECURE and not settings.DEBUG and not _localhost_only:
    _warnings.warn(
        "[EDQ SECURITY] COOKIE_SECURE=false in production mode — session cookies will be "
        "sent over plain HTTP. Set COOKIE_SECURE=true when deploying behind HTTPS.",
        stacklevel=2,
    )

# --- Sentry integration (optional) ---
if settings.SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.SENTRY_ENVIRONMENT,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            integrations=[FastApiIntegration(), SqlalchemyIntegration()],
            send_default_pii=False,
        )
        print(f"[EDQ] Sentry initialized (env={settings.SENTRY_ENVIRONMENT})", file=_sys.stderr)
    except ImportError:
        _warnings.warn(
            "[EDQ] SENTRY_DSN is set but sentry-sdk is not installed. "
            "Install with: pip install sentry-sdk[fastapi]",
            stacklevel=2,
        )

# Ensure directories exist
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.REPORT_DIR, exist_ok=True)
