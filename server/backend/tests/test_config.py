"""Configuration tests for runtime defaults and explicit overrides."""

from app.config import Settings


def _base_settings(**overrides) -> Settings:
    values = {
        "JWT_SECRET": "test-jwt-secret",
        "JWT_REFRESH_SECRET": "test-refresh-secret",
        "SECRET_KEY": "test-secret-key",
        "TOOLS_API_KEY": "test-tools-api-key",
        "INITIAL_ADMIN_PASSWORD": "AdminPass1",
    }
    values.update(overrides)
    return Settings(**values)


def test_database_url_defaults_to_postgres_components():
    settings = _base_settings(
        DATABASE_URL="",
        DB_HOST="db.internal",
        DB_PORT=5433,
        DB_NAME="edq_runtime",
        DB_USER="edq_user",
        DB_PASSWORD="super-secret",
    )

    assert settings.DATABASE_URL == (
        "postgresql+asyncpg://edq_user:super-secret@db.internal:5433/edq_runtime"
    )


def test_explicit_database_url_is_preserved():
    settings = _base_settings(
        DATABASE_URL="sqlite+aiosqlite:///./test.db",
        DB_HOST="ignored-host",
        DB_PASSWORD="ignored-password",
    )

    assert settings.DATABASE_URL == "sqlite+aiosqlite:///./test.db"


def test_log_json_defaults_follow_debug_mode():
    prod_settings = _base_settings(DEBUG=False, LOG_JSON=None)
    debug_settings = _base_settings(DEBUG=True, LOG_JSON=None)

    assert prod_settings.LOG_JSON is True
    assert debug_settings.LOG_JSON is False
