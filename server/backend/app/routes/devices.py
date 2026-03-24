"""Device management routes."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional

from app.models.database import get_db
from app.models.device import Device
from app.models.user import User
from app.schemas.device import DeviceCreate, DeviceUpdate, DeviceResponse
from app.security.auth import get_current_active_user, require_role
from app.utils.sanitize import sanitize_dict
from app.utils.audit import log_action

router = APIRouter()


@router.get("/", response_model=List[DeviceResponse])
async def list_devices(
    category: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    query = select(Device)
    if category:
        query = query.where(Device.category == category)
    if status:
        query = query.where(Device.status == status)
    if search:
        query = query.where(
            (Device.ip_address.contains(search)) |
            (Device.hostname.contains(search)) |
            (Device.manufacturer.contains(search)) |
            (Device.model.contains(search))
        )
    query = query.order_by(Device.updated_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/stats")
async def device_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """Get device statistics for the dashboard."""
    total = await db.execute(select(func.count(Device.id)))
    by_status = await db.execute(
        select(Device.status, func.count(Device.id)).group_by(Device.status)
    )
    by_category = await db.execute(
        select(Device.category, func.count(Device.id)).group_by(Device.category)
    )
    return {
        "total": total.scalar() or 0,
        "by_status": {row[0]: row[1] for row in by_status.all()},
        "by_category": {row[0]: row[1] for row in by_category.all()},
    }


@router.post("/", response_model=DeviceResponse, status_code=201)
async def create_device(
    data: DeviceCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    # Check for duplicate IP address
    existing = await db.execute(
        select(Device).where(Device.ip_address == data.ip_address)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"A device with IP address {data.ip_address} already exists",
        )
    clean = sanitize_dict(data.model_dump(), ["hostname", "manufacturer", "model", "notes"])
    device = Device(**clean)
    db.add(device)
    await db.flush()
    await db.refresh(device)
    await log_action(db, user, "create", "device", device.id, {"ip": device.ip_address}, request)
    return device


@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.patch("/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: str,
    data: DeviceUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    updates = sanitize_dict(data.model_dump(exclude_unset=True), ["hostname", "manufacturer", "model", "notes"])
    if "ip_address" in updates:
        device.ip_address = updates["ip_address"]
    if "mac_address" in updates:
        device.mac_address = updates["mac_address"]
    if "hostname" in updates:
        device.hostname = updates["hostname"]
    if "manufacturer" in updates:
        device.manufacturer = updates["manufacturer"]
    if "model" in updates:
        device.model = updates["model"]
    if "firmware_version" in updates:
        device.firmware_version = updates["firmware_version"]
    if "category" in updates:
        device.category = updates["category"]
    if "status" in updates:
        device.status = updates["status"]
    if "notes" in updates:
        device.notes = updates["notes"]
    if "profile_id" in updates:
        device.profile_id = updates["profile_id"]
    if "open_ports" in updates:
        device.open_ports = updates["open_ports"]
    if "discovery_data" in updates:
        device.discovery_data = updates["discovery_data"]
    await db.flush()
    await db.refresh(device)
    await log_action(db, user, "update", "device", device_id, {"fields": list(updates.keys())}, request)
    return device


@router.delete("/{device_id}", status_code=204)
async def delete_device(
    device_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["admin"])),
):
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    await log_action(db, user, "delete", "device", device_id, {"ip": device.ip_address}, request)
    await db.delete(device)
