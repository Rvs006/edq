"""Configuration tests for runtime defaults and explicit overrides."""

import pytest

from app.config import Settings, _apply_runtime_security_guards


def _base_settings(**overrides) -> Settings:
    values = {
        "JWT_SECRET": "jwt_test_value_for_tests_only",
        "JWT_REFRESH_SECRET": "refresh_test_value_for_tests_only",
        "SECRET_KEY": "app_test_value_for_tests_only",
        "TOOLS_API_KEY": "tools_api_value_for_tests_only",
        "INITIAL_ADMIN_PASSWORD": "AdminPassForTests1",
    }
    values.update(overrides)
    return Settings(**values)


def test_database_url_defaults_to_postgres_components():
    db_credential = "db-credential-for-tests"
    settings = _base_settings(
        DATABASE_URL="",
        DB_HOST="db.internal",
        DB_PORT=5433,
        DB_NAME="edq_runtime",
        DB_USER="edq_user",
        DB_PASSWORD=db_credential,
    )

    assert settings.DATABASE_URL == (
        f"postgresql+asyncpg://edq_user:{db_credential}@db.internal:5433/edq_runtime"
    )


def test_explicit_database_url_is_preserved():
    unused_db_credential = "unused-db-credential"
    settings = _base_settings(
        DATABASE_URL="sqlite+aiosqlite:///./test.db",
        DB_HOST="ignored-host",
        DB_PASSWORD=unused_db_credential,
    )

    assert settings.DATABASE_URL == "sqlite+aiosqlite:///./test.db"


def test_log_json_defaults_follow_debug_mode():
    prod_settings = _base_settings(DEBUG=False, LOG_JSON=None)
    debug_settings = _base_settings(DEBUG=True, LOG_JSON=None)

    assert prod_settings.LOG_JSON is True
    assert debug_settings.LOG_JSON is False


def test_docker_environment_keeps_localhost_cors_origins():
    settings = _apply_runtime_security_guards(
        _base_settings(
            DEBUG=False,
            ENVIRONMENT="docker",
            CORS_ORIGINS=["http://localhost:3000", "http://127.0.0.1:3000"],
        )
    )

    assert settings.CORS_ORIGINS == ["http://localhost:3000", "http://127.0.0.1:3000"]


def test_secure_docker_environment_strips_localhost_cors_origins():
    with pytest.warns(UserWarning, match="Stripped localhost origins"):
        settings = _apply_runtime_security_guards(
            _base_settings(
                DEBUG=False,
                ENVIRONMENT="docker",
                COOKIE_SECURE=True,
                CORS_ORIGINS=["https://edq.example.com", "http://localhost:3000", "http://127.0.0.1:3000"],
            )
        )

    assert settings.CORS_ORIGINS == ["https://edq.example.com"]


def test_cloud_environment_strips_localhost_cors_origins():
    with pytest.warns(UserWarning) as captured:
        settings = _apply_runtime_security_guards(
            _base_settings(
                DEBUG=False,
                ENVIRONMENT="cloud",
                CORS_ORIGINS=["https://edq.example.com", "http://localhost:3000"],
            )
        )

    assert settings.CORS_ORIGINS == ["https://edq.example.com"]
    messages = [str(warning.message) for warning in captured]
    assert any("COOKIE_SECURE=false in production environment" in message for message in messages)
    assert any("Stripped localhost origins" in message for message in messages)


def test_normalize_debug_accepts_production_aliases():
    settings = _base_settings(DEBUG="production")
    assert settings.DEBUG is False


def test_normalize_debug_accepts_development_aliases():
    settings = _base_settings(DEBUG="development")
    assert settings.DEBUG is True


def test_finalize_runtime_defaults_for_cloud_enable_secure_cookie():
    settings = _base_settings(
        ENVIRONMENT="cloud",
        COOKIE_SECURE=False,
        COOKIE_SAMESITE="strict",
        DATABASE_URL="",
    )

    assert settings.COOKIE_SECURE is True
    assert settings.COOKIE_SAMESITE == "lax"
    assert settings.DB_HOST == "postgres"
    assert settings.DB_PORT == 5432


def test_redis_required_defaults_false():
    settings = _base_settings()
    assert settings.REDIS_REQUIRED is False
