import pytest

from app.config import settings
from app.routes.websocket_routes import _validate_ws_origin


class DummyWebSocket:
    def __init__(self, headers: dict[str, str]):
        self.headers = headers


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