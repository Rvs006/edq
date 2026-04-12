"""WebSocket routes for real-time test progress streaming."""

import asyncio
import logging
from typing import Dict, Optional, Set
from urllib.parse import urlsplit

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
import jwt
from jwt.exceptions import InvalidTokenError
from sqlalchemy import select

from app.config import settings
from app.models.database import async_session
from app.models.network_scan import NetworkScan
from app.models.test_run import TestRun
from app.models.user import User, UserRole
from app.security.auth import SESSION_COOKIE, is_access_token_revoked_for_user

logger = logging.getLogger("edq.routes.websocket")

router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, channel: str) -> None:
        await websocket.accept()
        async with self._lock:
            if channel not in self.active_connections:
                self.active_connections[channel] = set()
            self.active_connections[channel].add(websocket)

    async def disconnect(self, websocket: WebSocket, channel: str) -> None:
        async with self._lock:
            if channel in self.active_connections:
                self.active_connections[channel].discard(websocket)
                if not self.active_connections[channel]:
                    del self.active_connections[channel]

    async def broadcast(self, channel: str, message: dict) -> None:
        async with self._lock:
            connections = self.active_connections.get(channel)
            if not connections:
                return
            snapshot = connections.copy()
        dead: list[WebSocket] = []
        for connection in snapshot:
            try:
                await connection.send_json(message)
            except Exception as exc:
                logger.warning("WebSocket send failed on channel %s: %s", channel, exc)
                dead.append(connection)
        if dead:
            async with self._lock:
                conns = self.active_connections.get(channel)
                if conns:
                    for ws in dead:
                        conns.discard(ws)
                    if not conns:
                        del self.active_connections[channel]


manager = ConnectionManager()


def _normalize_origin(origin: str) -> tuple[str, str] | None:
    raw_origin = str(origin or "").strip()
    if not raw_origin:
        return None
    parsed = urlsplit(raw_origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return parsed.scheme.lower(), parsed.netloc.lower()


def _same_host_origins(websocket: WebSocket) -> set[tuple[str, str]]:
    host = (
        websocket.headers.get("x-forwarded-host")
        or websocket.headers.get("host")
        or ""
    ).strip().lower()
    if not host:
        return set()

    forwarded_proto = (
        websocket.headers.get("x-forwarded-proto")
        or ""
    ).split(",")[0].strip().lower()
    if forwarded_proto in {"http", "https"}:
        return {(forwarded_proto, host)}
    return {("http", host), ("https", host)}


def _validate_ws_origin(websocket: WebSocket) -> bool:
    """Validate that the WebSocket Origin header matches allowed origins."""
    origin = websocket.headers.get("origin", "")
    if not origin:
        return True  # Same-origin requests may omit Origin
    normalized_origin = _normalize_origin(origin)
    if normalized_origin is None:
        logger.warning(
            "WS origin rejected: invalid origin header origin=%r host=%r forwarded_host=%r forwarded_proto=%r",
            origin,
            websocket.headers.get("host"),
            websocket.headers.get("x-forwarded-host"),
            websocket.headers.get("x-forwarded-proto"),
        )
        return False
    allowed = getattr(settings, "CORS_ORIGINS", [])
    if "*" in allowed:
        return True
    normalized_allowed = {
        candidate
        for candidate in (_normalize_origin(value) for value in allowed)
        if candidate is not None
    }
    if normalized_origin in normalized_allowed:
        return True
    if normalized_origin in _same_host_origins(websocket):
        return True
    logger.warning(
        "WS origin rejected: origin=%r normalized=%r host=%r forwarded_host=%r forwarded_proto=%r allowed=%r",
        origin,
        normalized_origin,
        websocket.headers.get("host"),
        websocket.headers.get("x-forwarded-host"),
        websocket.headers.get("x-forwarded-proto"),
        sorted(normalized_allowed),
    )
    return False


async def _authenticate_ws(websocket: WebSocket) -> Optional[dict]:
    """Validate JWT from httpOnly cookie only. Return payload or None."""
    if not _validate_ws_origin(websocket):
        return None
    token = websocket.cookies.get(SESSION_COOKIE)
    if not token:
        logger.warning(
            "WS auth rejected: missing session cookie path=%s host=%r forwarded_host=%r",
            websocket.url.path,
            websocket.headers.get("host"),
            websocket.headers.get("x-forwarded-host"),
        )
        return None
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != "access":
            logger.warning("WS auth rejected: non-access token path=%s", websocket.url.path)
            return None
        user_id = payload.get("sub")
        if not user_id:
            logger.warning("WS auth rejected: token missing sub path=%s", websocket.url.path)
            return None
        async with async_session() as db:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user or not user.is_active:
                logger.warning("WS auth rejected: inactive or missing user user_id=%r path=%s", user_id, websocket.url.path)
                return None
            if is_access_token_revoked_for_user(user, payload):
                logger.warning("WS auth rejected: revoked token user_id=%r path=%s", user_id, websocket.url.path)
                return None
        return payload
    except InvalidTokenError:
        logger.warning("WS auth rejected: invalid token path=%s", websocket.url.path)
        return None


async def _authorize_test_run(payload: dict, run_id: str) -> bool:
    """Check if the authenticated user is allowed to access this test run.

    Admins and reviewers can access all test runs.
    Engineers can only access their own.
    """
    role = payload.get("role", "engineer")
    if role in (UserRole.ADMIN.value, UserRole.REVIEWER.value):
        return True
    user_id = payload.get("sub")
    async with async_session() as db:
        result = await db.execute(select(TestRun.engineer_id).where(TestRun.id == run_id))
        row = result.scalar_one_or_none()
        if row is None:
            return False
        return row == user_id


@router.websocket("/test-run/{run_id}")
async def test_run_ws(websocket: WebSocket, run_id: str):
    """WebSocket endpoint for real-time test run progress."""
    payload = await _authenticate_ws(websocket)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication required")
        return

    if not await _authorize_test_run(payload, run_id):
        logger.warning("WS auth rejected: access denied run_id=%s user_id=%r role=%r", run_id, payload.get("sub"), payload.get("role"))
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Access denied")
        return

    channel = f"test-run:{run_id}"
    await manager.connect(websocket, channel)

    async def _keepalive():
        try:
            while True:
                await asyncio.sleep(20)
                await websocket.send_json({"type": "keepalive"})
        except Exception:
            pass

    keepalive_task = asyncio.create_task(_keepalive())
    try:
        while True:
            # Receive-only: consume client messages but do not re-broadcast.
            # The server is the sole broadcaster via manager.broadcast().
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        keepalive_task.cancel()
        await manager.disconnect(websocket, channel)


async def _authorize_discovery_task(payload: dict, task_id: str) -> bool:
    """Check if the authenticated user is allowed to access this discovery task.

    Admins and reviewers can access all discovery tasks.
    Engineers can only access tasks they created.
    """
    role = payload.get("role", "engineer")
    if role in (UserRole.ADMIN.value, UserRole.REVIEWER.value):
        return True
    user_id = payload.get("sub")
    async with async_session() as db:
        result = await db.execute(
            select(NetworkScan.created_by).where(NetworkScan.id == task_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return False
        return row == user_id


@router.websocket("/discovery/{task_id}")
async def discovery_ws(websocket: WebSocket, task_id: str):
    """WebSocket endpoint for real-time discovery progress."""
    payload = await _authenticate_ws(websocket)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication required")
        return

    if not await _authorize_discovery_task(payload, task_id):
        logger.warning("WS auth rejected: discovery access denied task_id=%s user_id=%r role=%r", task_id, payload.get("sub"), payload.get("role"))
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Access denied")
        return

    channel = f"discovery:{task_id}"
    await manager.connect(websocket, channel)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket, channel)


@router.websocket("/agents")
async def agents_ws(websocket: WebSocket):
    """WebSocket endpoint for real-time agent status updates.

    Broadcasts heartbeat events to all connected clients when agents
    report status changes via the heartbeat REST endpoint.
    """
    payload = await _authenticate_ws(websocket)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication required")
        return

    channel = "agents"
    await manager.connect(websocket, channel)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket, channel)
