from types import SimpleNamespace

import jwt
import pytest

from app.config import settings
from app.middleware import rate_limit as rate_limit_module
from app.routes import websocket_routes
from app.routes.websocket_routes import (
    _authenticate_ws,
    _authorize_discovery_task,
    _authorize_test_run,
    _validate_ws_origin,
)
from app.security.auth import SESSION_COOKIE


class DummyWebSocket:
    def __init__(
        self,
        headers: dict[str, str],
        cookies: dict[str, str] | None = None,
        path: str = "/ws/test",
    ):
        self.headers = headers
        self.cookies = cookies or {}
        self.url = SimpleNamespace(path=path)


@pytest.mark.asyncio
async def test_validate_ws_origin_allows_configured_origin(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "CORS_ORIGINS", ["http://localhost:3000"])
    websocket = DummyWebSocket(
        {
            "origin": "http://localhost:3000",
            "host": "localhost:3000",
            "x-forwarded-proto": "http",
        }
    )

    assert _validate_ws_origin(websocket) is True


@pytest.mark.asyncio
async def test_validate_ws_origin_allows_same_host_origin_not_in_cors(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "CORS_ORIGINS", ["http://localhost:3000"])
    websocket = DummyWebSocket(
        {
            "origin": "http://127.0.0.1:3000",
            "host": "127.0.0.1:3000",
            "x-forwarded-proto": "http",
        }
    )

    assert _validate_ws_origin(websocket) is True


@pytest.mark.asyncio
async def test_validate_ws_origin_rejects_cross_site_origin(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "CORS_ORIGINS", ["http://localhost:3000"])
    websocket = DummyWebSocket(
        {
            "origin": "http://evil.example",
            "host": "127.0.0.1:3000",
            "x-forwarded-proto": "http",
        }
    )

    assert _validate_ws_origin(websocket) is False


@pytest.mark.asyncio
async def test_authenticate_ws_rejects_missing_cookie(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "CORS_ORIGINS", ["http://localhost:3000"])
    websocket = DummyWebSocket({"origin": "http://localhost:3000", "host": "localhost:3000"})

    assert await _authenticate_ws(websocket) is None


@pytest.mark.asyncio
async def test_authenticate_ws_rejects_invalid_token(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "CORS_ORIGINS", ["http://localhost:3000"])
    monkeypatch.setattr(settings, "JWT_SECRET", "jwt_test_value_for_tests_only_123")
    websocket = DummyWebSocket(
        {"origin": "http://localhost:3000", "host": "localhost:3000"},
        cookies={SESSION_COOKIE: "bad-token"},
    )

    assert await _authenticate_ws(websocket) is None


@pytest.mark.asyncio
async def test_authenticate_ws_accepts_valid_active_user(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "CORS_ORIGINS", ["http://localhost:3000"])
    monkeypatch.setattr(settings, "JWT_SECRET", "jwt_test_value_for_tests_only_123")
    token = jwt.encode(
        {"sub": "user-1", "type": "access"},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    websocket = DummyWebSocket(
        {"origin": "http://localhost:3000", "host": "localhost:3000"},
        cookies={SESSION_COOKIE: token},
    )

    class DummyResult:
        def scalar_one_or_none(self):
            return SimpleNamespace(id="user-1", is_active=True)

    class DummySession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, query):
            return DummyResult()

    monkeypatch.setattr(websocket_routes, "async_session", lambda: DummySession())
    monkeypatch.setattr(
        websocket_routes,
        "is_access_token_revoked_for_user",
        lambda user, payload: False,
    )

    payload = await _authenticate_ws(websocket)

    assert payload is not None
    assert payload["sub"] == "user-1"


@pytest.mark.asyncio
async def test_authorize_test_run_allows_admin():
    assert await _authorize_test_run({"role": "admin", "sub": "user-1"}, "run-1") is True


@pytest.mark.asyncio
async def test_authorize_test_run_checks_engineer_ownership(monkeypatch: pytest.MonkeyPatch):
    class DummyResult:
        def scalar_one_or_none(self):
            return "user-1"

    class DummySession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, query):
            return DummyResult()

    monkeypatch.setattr(websocket_routes, "async_session", lambda: DummySession())

    assert await _authorize_test_run({"role": "engineer", "sub": "user-1"}, "run-1") is True
    assert await _authorize_test_run({"role": "engineer", "sub": "user-2"}, "run-1") is False


@pytest.mark.asyncio
async def test_authorize_discovery_task_checks_creator(monkeypatch: pytest.MonkeyPatch):
    class DummyResult:
        def scalar_one_or_none(self):
            return "user-7"

    class DummySession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, query):
            return DummyResult()

    monkeypatch.setattr(websocket_routes, "async_session", lambda: DummySession())

    assert await _authorize_discovery_task({"role": "engineer", "sub": "user-7"}, "task-1") is True
    assert await _authorize_discovery_task({"role": "engineer", "sub": "user-9"}, "task-1") is False


def test_rate_limiter_resets_to_in_memory_when_redis_disabled(monkeypatch: pytest.MonkeyPatch):
    from app.config import settings

    monkeypatch.setattr(settings, "REDIS_URL", "")
    monkeypatch.setattr(settings, "REDIS_REQUIRED", False)

    limiter = rate_limit_module.reset_rate_limiter()

    assert limiter.__class__.__name__ == "InMemoryRateLimiter"


def test_rate_limiter_raises_when_redis_required_and_unavailable(monkeypatch: pytest.MonkeyPatch):
    from app.config import settings

    monkeypatch.setattr(settings, "REDIS_URL", "redis://127.0.0.1:6399/0")
    monkeypatch.setattr(settings, "REDIS_REQUIRED", True)

    with pytest.raises(RuntimeError, match="REDIS_REQUIRED=true"):
        rate_limit_module.reset_rate_limiter()

    monkeypatch.setattr(settings, "REDIS_URL", "")
    monkeypatch.setattr(settings, "REDIS_REQUIRED", False)
    rate_limit_module.reset_rate_limiter()