"""WebSocket routes for real-time test progress streaming."""

import logging
from typing import Dict, Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from jose import JWTError, jwt
from sqlalchemy import select

from app.config import settings
from app.models.database import async_session
from app.models.network_scan import NetworkScan
from app.models.test_run import TestRun
from app.models.user import UserRole
from app.security.auth import SESSION_COOKIE

logger = logging.getLogger("edq.routes.websocket")

router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, channel: str) -> None:
        await websocket.accept()
        if channel not in self.active_connections:
            self.active_connections[channel] = set()
        self.active_connections[channel].add(websocket)

    def disconnect(self, websocket: WebSocket, channel: str) -> None:
        if channel in self.active_connections:
            self.active_connections[channel].discard(websocket)

    async def broadcast(self, channel: str, message: dict) -> None:
        if channel in self.active_connections:
            for connection in self.active_connections[channel].copy():
                try:
                    await connection.send_json(message)
                except Exception:
                    self.active_connections[channel].discard(connection)


manager = ConnectionManager()


def _authenticate_ws(websocket: WebSocket) -> Optional[dict]:
    """Validate JWT from httpOnly cookie only. Return payload or None."""
    token = websocket.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != "access":
            return None
        return payload
    except JWTError:
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
    payload = _authenticate_ws(websocket)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication required")
        return

    if not await _authorize_test_run(payload, run_id):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Access denied")
        return

    channel = f"test-run:{run_id}"
    await manager.connect(websocket, channel)
    try:
        while True:
            # Receive-only: consume client messages but do not re-broadcast.
            # The server is the sole broadcaster via manager.broadcast().
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)


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
    payload = _authenticate_ws(websocket)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication required")
        return

    if not await _authorize_discovery_task(payload, task_id):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Access denied")
        return

    channel = f"discovery:{task_id}"
    await manager.connect(websocket, channel)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)


@router.websocket("/agents")
async def agents_ws(websocket: WebSocket):
    """WebSocket endpoint for real-time agent status updates.

    Broadcasts heartbeat events to all connected clients when agents
    report status changes via the heartbeat REST endpoint.
    """
    payload = _authenticate_ws(websocket)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication required")
        return

    channel = "agents"
    await manager.connect(websocket, channel)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)
