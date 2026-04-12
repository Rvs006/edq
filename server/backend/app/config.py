"""Application configuration from environment variables."""

import os
from pathlib import Path
from typing import List
from urllib.parse import quote_plus

from dotenv import load_dotenv
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _resolve_env_file() -> Path:
    current_file = Path(__file__).resolve()
    parents = current_file.parents

    if len(parents) > 3 and parents[1].name == "backend" and parents[2].name == "server":
        return parents[3] / ".env"

    return Path("/app/.env")


ROOT_ENV_FILE = _resolve_env_file()
load_dotenv(ROOT_ENV_FILE, override=False)


def _partition_localhost_origins(origins: List[str]) -> tuple[list[str], bool]:
    localhost_origins = [
        origin
        for origin in origins
        if "localhost" in origin or "127.0.0.1" in origin
    ]
    localhost_only = bool(origins) and len(localhost_origins) == len(origins)
    return localhost_origins, localhost_only


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "EDQ"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production-use-openssl-rand-hex-32"

    ENVIRONMENT: str = "local"

    DATABASE_URL: str = ""
    DB_DRIVER: str = "postgresql+asyncpg"
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 55432
    DB_NAME: str = "edq"
    DB_USER: str = "edq"
    DB_PASSWORD: str = "edq-postgres-secret"
    DB_CONNECT_TIMEOUT_SECONDS: int = 15

    JWT_SECRET: str = "change-me-jwt-secret-use-openssl-rand-hex-64"
    JWT_REFRESH_SECRET: str = "change-me-refresh-secret-use-openssl-rand-hex-64"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8080",
    ]

    UPLOAD_DIR: str = "./uploads"
    REPORT_DIR: str = "./reports"
    MAX_FILE_SIZE: int = 50 * 1024 * 1024
    MAX_NESSUS_FILE_SIZE: int = 10 * 1024 * 1024

    AGENT_API_KEY_LENGTH: int = 64
    AGENT_HEARTBEAT_TIMEOUT: int = 300

    AI_API_KEY: str = ""
    AI_API_URL: str = ""
    AI_MODEL: str = "gpt-4o"
    AI_MAX_SYNOPSIS_PER_HOUR: int = 10

    TOOLS_SIDECAR_URL: str = "http://localhost:8001"
    TOOLS_API_KEY: str = ""

    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "strict"
    INITIAL_ADMIN_PASSWORD: str = ""
    SSL_VERIFY_DEVICES: bool = True
    ALLOW_REGISTRATION: bool = False

    METRICS_API_KEY: str = ""

    RATE_LIMIT_PER_MINUTE: int = 60
    LOGIN_RATE_LIMIT_PER_MINUTE: int = 15
    REDIS_URL: str = ""
    ACCOUNT_LOCKOUT_ATTEMPTS: int = 5
    ACCOUNT_LOCKOUT_MINUTES: int = 15

    OIDC_PROVIDER: str = ""
    OIDC_CLIENT_ID: str = ""
    OIDC_CLIENT_SECRET: str = ""
    OIDC_DISCOVERY_URL: str = ""
    OIDC_ALLOWED_DOMAINS: str = ""

    SENTRY_DSN: str = ""
    SENTRY_ENVIRONMENT: str = "production"
    SENTRY_RELEASE: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    SENTRY_PROFILES_SAMPLE_RATE: float = 0.0
    SENTRY_LOG_LEVEL: str = "INFO"
    SENTRY_EVENT_LEVEL: str = "ERROR"
    SENTRY_SEND_DEFAULT_PII: bool = False

    AUDIT_LOG_RETENTION_DAYS: int = 365

    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool | None = None

    @field_validator("DEBUG", mode="before")
    @classmethod
    def normalize_debug(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production", "false", "0", "off", "no"}:
                return False
            if normalized in {"debug", "dev", "development", "true", "1", "on", "yes"}:
                return True
        return value

    @field_validator("ENVIRONMENT", mode="before")
    @classmethod
    def normalize_environment(cls, value: str) -> str:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"local", "dev", "development"}:
                return "local"
            if normalized in {"docker", "container"}:
                return "docker"
            if normalized in {"cloud", "prod", "production", "staging"}:
                return "cloud"
        return value

    @model_validator(mode="after")
    def finalize_runtime_defaults(self):
        local_db_host = "127.0.0.1"
        local_db_port = 55432

        if self.ENVIRONMENT == "docker":
            if self.DB_HOST == local_db_host:
                self.DB_HOST = "postgres"
            if self.DB_PORT == local_db_port:
                self.DB_PORT = 5432
            _, localhost_only = _partition_localhost_origins(self.CORS_ORIGINS)
            if not self.COOKIE_SECURE and not localhost_only:
                import warnings

                warnings.warn(
                    "[EDQ SECURITY] COOKIE_SECURE=false in docker environment - session cookies "
                    "will be sent over plain HTTP. Set COOKIE_SECURE=true when deploying behind HTTPS.",
                    stacklevel=2,
                )
        elif self.ENVIRONMENT == "cloud":
            if self.DB_HOST == local_db_host:
                self.DB_HOST = "postgres"
            if self.DB_PORT == local_db_port:
                self.DB_PORT = 5432
            if not self.COOKIE_SECURE:
                import warnings

                warnings.warn(
                    "[EDQ SECURITY] COOKIE_SECURE=false in production environment - session cookies "
                    "will be sent over plain HTTP. Set COOKIE_SECURE=true when deploying behind HTTPS.",
                    stacklevel=2,
                )
                self.COOKIE_SECURE = True
            if self.COOKIE_SAMESITE == "strict":
                self.COOKIE_SAMESITE = "lax"

        if not self.DATABASE_URL:
            self.DATABASE_URL = (
                f"{self.DB_DRIVER}://"
                f"{quote_plus(self.DB_USER)}:{quote_plus(self.DB_PASSWORD)}"
                f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            )

        if self.LOG_JSON is None:
            self.LOG_JSON = not self.DEBUG

        return self


settings = Settings()

import secrets as _secrets
import sys as _sys
import warnings as _warnings


def _apply_runtime_security_guards(runtime_settings: Settings) -> Settings:
    localhost_origins, localhost_only = _partition_localhost_origins(runtime_settings.CORS_ORIGINS)
    production_like_env = runtime_settings.ENVIRONMENT == "cloud" or (
        runtime_settings.ENVIRONMENT == "docker" and runtime_settings.COOKIE_SECURE
    )

    if localhost_origins and production_like_env:
        runtime_settings.CORS_ORIGINS = [
            origin for origin in runtime_settings.CORS_ORIGINS if origin not in localhost_origins
        ]
        _warnings.warn(
            "[EDQ SECURITY] Stripped localhost origins from CORS_ORIGINS in production: "
            f"{localhost_origins}. Only non-localhost origins remain.",
            stacklevel=2,
        )

    if not runtime_settings.COOKIE_SECURE and production_like_env and not localhost_only:
        _warnings.warn(
            "[EDQ SECURITY] COOKIE_SECURE=false in production mode - session cookies will be "
            "sent over plain HTTP. Set COOKIE_SECURE=true when deploying behind HTTPS.",
            stacklevel=2,
        )

    return runtime_settings


settings = _apply_runtime_security_guards(settings)

if not settings.INITIAL_ADMIN_PASSWORD:
    generated = _secrets.token_urlsafe(16)
    settings.INITIAL_ADMIN_PASSWORD = generated
    print(
        f"\n[EDQ SECURITY] INITIAL_ADMIN_PASSWORD was not set. "
        f"Generated one-time password: {generated}\n"
        f"Set INITIAL_ADMIN_PASSWORD in your .env file for future starts.\n",
        file=_sys.stderr,
    )

placeholder_prefixes = ("change-me", "CHANGE_ME")
secret_fields = {
    "SECRET_KEY": settings.SECRET_KEY,
    "JWT_SECRET": settings.JWT_SECRET,
    "JWT_REFRESH_SECRET": settings.JWT_REFRESH_SECRET,
}
for name, value in secret_fields.items():
    if any(value.startswith(prefix) for prefix in placeholder_prefixes):
        message = (
            f"[EDQ SECURITY] {name} is still set to a placeholder value. "
            "Generate a strong secret with: openssl rand -hex 64"
        )
        raise RuntimeError(message)

if not settings.TOOLS_API_KEY or any(
    settings.TOOLS_API_KEY.startswith(prefix) for prefix in placeholder_prefixes
):
    message = (
        "[EDQ SECURITY] TOOLS_API_KEY is not set or is a placeholder. "
        "The tools sidecar requires a valid key. Generate with: openssl rand -hex 32"
    )
    raise RuntimeError(message)

if len(settings.TOOLS_API_KEY) < 32:
    message = (
        "[EDQ SECURITY] TOOLS_API_KEY must be at least 32 characters. "
        "Generate a strong key with: openssl rand -hex 32"
    )
    raise RuntimeError(message)

if settings.DATABASE_URL.startswith("sqlite") and not settings.DEBUG:
    _warnings.warn(
        "[EDQ DATABASE] SQLite is enabled outside debug mode. PostgreSQL is the supported "
        "runtime for concurrent or production workloads.",
        stacklevel=2,
    )

if settings.DEBUG:
    print(
        f"[EDQ CONFIG] ENVIRONMENT={settings.ENVIRONMENT} "
        f"DB_HOST={settings.DB_HOST}:{settings.DB_PORT} "
        f"COOKIE_SECURE={settings.COOKIE_SECURE} "
        f"COOKIE_SAMESITE={settings.COOKIE_SAMESITE} "
        f"DEBUG={settings.DEBUG} "
        f"CORS_ORIGINS={settings.CORS_ORIGINS}",
        file=_sys.stderr,
    )

_sentry_configured = False


def configure_sentry() -> None:
    """Initialize Sentry once when a DSN is configured."""
    global _sentry_configured

    if _sentry_configured or not settings.SENTRY_DSN:
        return

    try:
        import logging

        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        breadcrumb_level = getattr(logging, settings.SENTRY_LOG_LEVEL.upper(), logging.INFO)
        event_level = getattr(logging, settings.SENTRY_EVENT_LEVEL.upper(), logging.ERROR)
        sentry_logging = LoggingIntegration(
            level=breadcrumb_level,
            event_level=event_level,
        )

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.SENTRY_ENVIRONMENT,
            release=settings.SENTRY_RELEASE or None,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            profiles_sample_rate=settings.SENTRY_PROFILES_SAMPLE_RATE,
            integrations=[
                FastApiIntegration(),
                SqlalchemyIntegration(),
                sentry_logging,
            ],
            send_default_pii=settings.SENTRY_SEND_DEFAULT_PII,
        )
        _sentry_configured = True
        print(
            f"[EDQ] Sentry initialized (env={settings.SENTRY_ENVIRONMENT})",
            file=_sys.stderr,
        )
    except ImportError:
        _warnings.warn(
            "[EDQ] SENTRY_DSN is set but sentry-sdk is not installed. "
            "Install with: pip install sentry-sdk[fastapi]",
            stacklevel=2,
        )


os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.REPORT_DIR, exist_ok=True)