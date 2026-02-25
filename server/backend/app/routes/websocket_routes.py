"""WebSocket routes for real-time test progress streaming."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Set
import json

router = APIRouter()

# Active WebSocket connections
connections: Dict[str, Set[WebSocket]] = {}


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, channel: str):
        await websocket.accept()
        if channel not in self.active_connections:
            self.active_connections[channel] = set()
        self.active_connections[channel].add(websocket)

    def disconnect(self, websocket: WebSocket, channel: str):
        if channel in self.active_connections:
            self.active_connections[channel].discard(websocket)

    async def broadcast(self, channel: str, message: dict):
        if channel in self.active_connections:
            for connection in self.active_connections[channel].copy():
                try:
                    await connection.send_json(message)
                except Exception:
                    self.active_connections[channel].discard(connection)


manager = ConnectionManager()


@router.websocket("/test-run/{run_id}")
async def test_run_ws(websocket: WebSocket, run_id: str):
    """WebSocket endpoint for real-time test run progress."""
    channel = f"test-run:{run_id}"
    await manager.connect(websocket, channel)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            # Broadcast updates to all watchers of this test run
            await manager.broadcast(channel, message)
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)


@router.websocket("/discovery/{task_id}")
async def discovery_ws(websocket: WebSocket, task_id: str):
    """WebSocket endpoint for real-time discovery progress."""
    channel = f"discovery:{task_id}"
    await manager.connect(websocket, channel)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            await manager.broadcast(channel, message)
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)
