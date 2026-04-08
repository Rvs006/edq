"""Device management routes."""

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from typing import List, Optional

from app.models.database import get_db
from app.models.device import Device
from app.models.user import User
from app.schemas.device import DeviceCreate, DeviceUpdate, DeviceResponse
from app.security.auth import get_current_active_user, require_role
from app.utils.sanitize import sanitize_dict
from app.utils.audit import log_action
from app.services.tools_client import tools_client

logger = logging.getLogger("edq.routes.devices")

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
            or_(
                Device.ip_address.contains(search),
                Device.mac_address.contains(search),
                Device.hostname.contains(search),
                Device.manufacturer.contains(search),
                Device.model.contains(search),
            )
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
    is_dhcp = data.addressing_mode == "dhcp"

    # DHCP devices require a MAC address instead of IP
    if is_dhcp:
        if not data.mac_address:
            raise HTTPException(
                status_code=422,
                detail="MAC address is required for DHCP devices",
            )
        # Check for duplicate MAC address
        existing_mac = await db.execute(
            select(Device).where(Device.mac_address == data.mac_address)
        )
        if existing_mac.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail=f"A device with MAC address {data.mac_address} already exists",
            )
    else:
        # Static devices require an IP address
        if not data.ip_address:
            raise HTTPException(
                status_code=422,
                detail="IP address is required for static devices",
            )
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
    await log_action(db, user, "create", "device", device.id, {"ip": device.ip_address, "mac": device.mac_address, "addressing_mode": data.addressing_mode}, request)
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
    if "addressing_mode" in updates:
        device.addressing_mode = updates["addressing_mode"]
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


@router.post("/{device_id}/discover-ip", response_model=DeviceResponse)
async def discover_device_ip(
    device_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Run an ARP scan on local subnets to find the IP for a DHCP device by MAC address."""
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    if not device.mac_address:
        raise HTTPException(
            status_code=422,
            detail="Device has no MAC address — cannot discover IP",
        )

    mac_upper = device.mac_address.upper().replace("-", ":")

    # Use nmap ARP scan on common subnets to find the device
    subnets_to_scan = ["192.168.1.0/24", "192.168.0.0/24", "10.0.0.0/24", "172.16.0.0/24"]
    discovered_ip = None

    for subnet in subnets_to_scan:
        try:
            scan_result = await tools_client.nmap(
                target=subnet,
                args=["-sn", "-PR"],  # ARP ping scan
                timeout=30,
            )
            stdout = scan_result.get("stdout", "")
            # Parse nmap output for MAC-to-IP mapping
            # nmap -sn output format:
            #   Nmap scan report for 192.168.1.50
            #   Host is up (0.0010s latency).
            #   MAC Address: AA:BB:CC:DD:EE:FF (Vendor)
            current_ip = None
            for line in stdout.splitlines():
                ip_match = re.match(r"Nmap scan report for (\S+)", line)
                if ip_match:
                    current_ip = ip_match.group(1)
                mac_match = re.match(r"MAC Address:\s*([0-9A-Fa-f:]+)", line.strip())
                if mac_match and current_ip:
                    found_mac = mac_match.group(1).upper()
                    if found_mac == mac_upper:
                        discovered_ip = current_ip
                        break
            if discovered_ip:
                break
        except Exception as exc:
            logger.warning("ARP scan on %s failed: %s", subnet, exc)
            continue

    if not discovered_ip:
        raise HTTPException(
            status_code=404,
            detail=f"Could not discover IP for MAC {device.mac_address}. "
                   "Ensure the device is powered on and connected to the network.",
        )

    # Check that no other device already has this IP
    existing_ip = await db.execute(
        select(Device).where(Device.ip_address == discovered_ip, Device.id != device_id)
    )
    if existing_ip.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Discovered IP {discovered_ip} is already assigned to another device",
        )

    device.ip_address = discovered_ip
    await db.flush()
    await db.refresh(device)
    await log_action(
        db, user, "discover_ip", "device", device_id,
        {"mac": device.mac_address, "discovered_ip": discovered_ip}, request,
    )
    return device
