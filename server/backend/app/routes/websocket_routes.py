"""WebSocket routes for real-time test progress streaming."""

import json
import logging
from typing import Dict, Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from jose import JWTError, jwt

from app.config import settings
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


@router.websocket("/test-run/{run_id}")
async def test_run_ws(websocket: WebSocket, run_id: str):
    """WebSocket endpoint for real-time test run progress."""
    payload = _authenticate_ws(websocket)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication required")
        return

    channel = f"test-run:{run_id}"
    await manager.connect(websocket, channel)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            await manager.broadcast(channel, message)
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)


@router.websocket("/discovery/{task_id}")
async def discovery_ws(websocket: WebSocket, task_id: str):
    """WebSocket endpoint for real-time discovery progress."""
    payload = _authenticate_ws(websocket)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication required")
        return

    channel = f"discovery:{task_id}"
    await manager.connect(websocket, channel)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            await manager.broadcast(channel, message)
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
            data = await websocket.receive_text()
            message = json.loads(data)
            await manager.broadcast(channel, message)
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)
