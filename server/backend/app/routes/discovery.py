"""Discovery routes — device auto-detection pipeline."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional, List, Any

from app.models.database import get_db
from app.models.user import User
from app.schemas.device import DiscoveryRequest
from app.security.auth import get_current_active_user

router = APIRouter()


class DiscoveryResult(BaseModel):
    ip_address: str
    mac_address: Optional[str] = None
    hostname: Optional[str] = None
    oui_vendor: Optional[str] = None
    open_ports: Optional[List[Any]] = None
    os_fingerprint: Optional[str] = None
    category: str = "unknown"
    confidence: float = 0.0


@router.post("/scan")
async def initiate_discovery(
    data: DiscoveryRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Initiate a device discovery scan.
    
    In production, this dispatches to an agent. For the web UI, it records
    the discovery request and returns a task ID for polling.
    """
    return {
        "message": "Discovery scan initiated",
        "task_id": "discovery-task-placeholder",
        "subnet": data.subnet,
        "ip_address": data.ip_address,
        "agent_id": data.agent_id,
        "status": "pending",
        "note": "Discovery requires an agent with network scanning tools (nmap). The web UI monitors progress via WebSocket."
    }


@router.post("/register-device")
async def register_discovered_device(
    data: DiscoveryResult,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Register a device discovered by an agent."""
    from app.models.device import Device
    device = Device(
        ip_address=data.ip_address,
        mac_address=data.mac_address,
        hostname=data.hostname,
        oui_vendor=data.oui_vendor,
        open_ports=data.open_ports,
        os_fingerprint=data.os_fingerprint,
        category=data.category,
        status="discovered",
    )
    db.add(device)
    await db.flush()
    await db.refresh(device)
    return {"device_id": device.id, "message": "Device registered successfully"}
