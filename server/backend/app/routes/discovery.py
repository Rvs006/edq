"""Discovery routes — device auto-detection pipeline."""

import asyncio
import base64
import logging
import socket
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.models.device import Device, DeviceCategory, DeviceStatus
from app.models.project import Project
from app.models.user import User
from app.schemas.device import DiscoveryRequest
from app.security.auth import get_current_active_user
from app.middleware.rate_limit import check_rate_limit
from app.services.connectivity_probe import probe_device_connectivity
from app.services.discovery_service import (
    build_device_display_name,
    guess_category,
    guess_manufacturer,
    guess_model,
)
from app.services.tools_client import describe_tools_error, get_tools_error_status, tools_client
from app.services.parsers.nmap_parser import nmap_parser
from app.utils.audit import log_action

logger = logging.getLogger("edq.routes.discovery")

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


class DiscoveredDeviceResponse(BaseModel):
    id: str
    ip_address: str
    mac_address: Optional[str] = None
    hostname: Optional[str] = None
    oui_vendor: Optional[str] = None
    os_fingerprint: Optional[str] = None
    open_ports: Optional[List[Any]] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    predicted_name: Optional[str] = None
    category: str = "unknown"
    status: str = "discovered"
    is_new: bool = True
    project_id: Optional[str] = None


def _decode_output_file(raw: Dict[str, Any]) -> str:
    """Decode base64-encoded output_file from tools sidecar response."""
    output_file = raw.get("output_file", "")
    if not output_file:
        return ""
    try:
        return base64.b64decode(output_file).decode("utf-8", errors="replace")
    except Exception:
        return output_file if isinstance(output_file, str) else ""


def _append_interface_arg(args: list[str], interface: Optional[str]) -> list[str]:
    if not interface:
        return list(args)
    return [*args, "-e", interface]


def _resolve_hostname(ip: str) -> Optional[str]:
    """Attempt reverse DNS lookup for an IP address (sync, run via to_thread)."""
    try:
        hostname, _, _ = socket.gethostbyaddr(ip)
        if hostname and not hostname.startswith(ip.replace(".", "-")):
            return hostname
    except (socket.herror, socket.gaierror, OSError):
        pass
    return None


async def _resolve_hostname_async(ip: str) -> Optional[str]:
    """Non-blocking reverse DNS lookup."""
    import asyncio
    return await asyncio.to_thread(_resolve_hostname, ip)


async def _upsert_device(
    db: AsyncSession,
    ip: str,
    mac: Optional[str],
    hostname: Optional[str],
    vendor: Optional[str],
    os_fp: Optional[str],
    open_ports: Optional[List[Dict[str, Any]]],
    discovery_data: Optional[Dict[str, Any]],
    category: DeviceCategory,
    project_id: Optional[str],
) -> tuple[Device, bool]:
    """Create or update a device record. Returns (device, is_new)."""
    from sqlalchemy.exc import IntegrityError

    # Active reverse DNS if nmap didn't provide hostname
    if not hostname:
        hostname = await _resolve_hostname_async(ip)

    result = await db.execute(select(Device).where(Device.ip_address == ip))
    device = result.scalar_one_or_none()

    # Also check by MAC address if IP lookup returned nothing
    if device is None and mac:
        mac_result = await db.execute(select(Device).where(Device.mac_address == mac))
        device = mac_result.scalar_one_or_none()
        if device and not device.ip_address:
            # Found DHCP device by MAC — assign the discovered IP
            device.ip_address = ip

    is_new = device is None

    # Auto-detect manufacturer and model from scan data
    auto_manufacturer = guess_manufacturer(vendor, open_ports or []) or vendor
    auto_model = guess_model(open_ports or [], os_fp)

    if is_new:
        device = Device(
            ip_address=ip,
            mac_address=mac,
            hostname=hostname,
            oui_vendor=vendor,
            os_fingerprint=os_fp,
            open_ports=open_ports,
            discovery_data=discovery_data,
            category=category,
            status=DeviceStatus.DISCOVERED,
            manufacturer=auto_manufacturer,
            model=auto_model,
            project_id=project_id,
        )
        db.add(device)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            # Race condition: another task inserted the same IP — re-select and update
            result = await db.execute(select(Device).where(Device.ip_address == ip))
            device = result.scalar_one_or_none()
            if device is None:
                raise
            is_new = False
            # Fall through to update path below

    if not is_new:
        if mac:
            device.mac_address = mac
        if hostname:
            device.hostname = hostname
        if vendor:
            device.oui_vendor = vendor
        if os_fp:
            device.os_fingerprint = os_fp
        if open_ports is not None:
            device.open_ports = open_ports
        if discovery_data is not None:
            device.discovery_data = discovery_data
        if auto_manufacturer and not device.manufacturer:
            device.manufacturer = auto_manufacturer
        if auto_model and not device.model:
            device.model = auto_model
        if project_id and not device.project_id:
            device.project_id = project_id
        device.category = category
        device.status = DeviceStatus.IDENTIFIED
        await db.flush()

    await db.refresh(device)
    return device, is_new


async def _validate_project_id(db: AsyncSession, project_id: Optional[str]) -> Optional[str]:
    if not project_id:
        return None
    result = await db.execute(select(Project.id).where(Project.id == project_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project_id


@router.post("/scan")
async def initiate_discovery(
    data: DiscoveryRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Run nmap discovery against a single IP or subnet.

    - ip_address provided: full service detection + OS fingerprint (-sV -O -p-)
    - subnet provided: ping sweep (-sn) to list live hosts
    """
    check_rate_limit(request, max_requests=3, window_seconds=60, action="discovery_scan")

    project_id = await _validate_project_id(db, data.project_id)
    target = data.ip_address or data.subnet
    if not target:
        raise HTTPException(status_code=400, detail="Provide either ip_address or subnet")

    discovered_devices: List[Dict[str, Any]] = []

    if data.ip_address:
        # Best-effort pre-flight: use it to bound scan time, but do not hard-fail
        # the request. Some real devices block ICMP or only expose non-default
        # services, so a quick probe can miss a device that nmap can still find.
        scan_timeout = 300
        try:
            is_reachable, probe_source = await asyncio.wait_for(
                probe_device_connectivity(data.ip_address),
                timeout=5.0,
            )
        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning("Connectivity pre-check failed for %s: %s", data.ip_address, exc)
            is_reachable = False
            probe_source = None

        if not is_reachable:
            logger.info(
                "Connectivity pre-check did not confirm %s; proceeding with full scan timeout anyway",
                data.ip_address,
            )
        else:
            logger.debug(
                "Connectivity pre-check confirmed %s via %s",
                data.ip_address,
                probe_source,
            )

        try:
            raw = await tools_client.nmap(
                data.ip_address,
                _append_interface_arg(["-sV", "-O", "-p-", "--max-rate", "300", "-oX", "-"], data.interface),
                timeout=scan_timeout,
            )
        except Exception as exc:
            logger.exception("Nmap service scan failed for %s", data.ip_address)
            raise HTTPException(
                status_code=get_tools_error_status(exc),
                detail=describe_tools_error(exc, fallback="Device discovery failed"),
            )

        xml_out = raw.get("stdout", "")
        parsed = nmap_parser.parse_xml(xml_out) if xml_out else {}

        open_ports = parsed.get("open_ports", [])
        os_fp = parsed.get("os_fingerprint")
        mac = parsed.get("mac_address")
        vendor = parsed.get("oui_vendor")
        hostname = None
        for h in parsed.get("hosts", []):
            if h.get("ip") == data.ip_address and h.get("hostname"):
                hostname = h["hostname"]
                break

        category = guess_category(os_fp, open_ports)

        device, is_new = await _upsert_device(
            db,
            ip=data.ip_address,
            mac=mac,
            hostname=hostname,
            vendor=vendor,
            os_fp=os_fp,
            open_ports=open_ports,
            discovery_data=parsed,
            category=category,
            project_id=project_id,
        )

        discovered_devices.append({
            "id": device.id,
            "ip_address": device.ip_address,
            "mac_address": device.mac_address,
            "hostname": device.hostname,
            "oui_vendor": device.oui_vendor,
            "os_fingerprint": device.os_fingerprint,
            "open_ports": device.open_ports,
            "manufacturer": device.manufacturer,
            "model": device.model,
            "predicted_name": build_device_display_name(
                device.ip_address,
                device.hostname,
                device.manufacturer,
                device.model,
            ),
            "category": device.category.value if hasattr(device.category, "value") else str(device.category),
            "status": device.status.value if hasattr(device.status, "value") else str(device.status),
            "is_new": is_new,
            "project_id": device.project_id,
        })

    elif data.subnet:
        try:
            raw = await tools_client.nmap(
                data.subnet,
                _append_interface_arg(["-sn"], data.interface),
                timeout=120,
            )
        except Exception as exc:
            logger.exception("Nmap ping sweep failed for %s", data.subnet)
            raise HTTPException(
                status_code=get_tools_error_status(exc),
                detail=describe_tools_error(exc, fallback="Subnet discovery failed"),
            )

        hosts = nmap_parser.parse_host_discovery(raw.get("stdout", ""))

        for host in hosts:
            device, is_new = await _upsert_device(
                db,
                ip=host["ip"],
                mac=host.get("mac"),
                hostname=host.get("hostname"),
                vendor=host.get("vendor"),
                os_fp=None,
                open_ports=None,
                discovery_data={"source": "ping_sweep", "raw_host": host},
                category=DeviceCategory.UNKNOWN,
                project_id=project_id,
            )

            discovered_devices.append({
                "id": device.id,
                "ip_address": device.ip_address,
                "mac_address": device.mac_address,
                "hostname": device.hostname,
                "oui_vendor": device.oui_vendor,
                "os_fingerprint": device.os_fingerprint,
                "open_ports": device.open_ports,
                "manufacturer": device.manufacturer,
                "model": device.model,
                "predicted_name": build_device_display_name(
                    device.ip_address,
                    device.hostname,
                    device.manufacturer,
                    device.model,
                ),
                "category": device.category.value if hasattr(device.category, "value") else str(device.category),
                "status": device.status.value if hasattr(device.status, "value") else str(device.status),
                "is_new": is_new,
                "project_id": device.project_id,
            })

    await log_action(db, user, "discovery.scan", "discovery", target,
                     {"devices_found": len(discovered_devices)}, request)

    return {
        "status": "complete",
        "target": target,
        "devices_found": len(discovered_devices),
        "devices": discovered_devices,
    }


@router.post("/register-device")
async def register_discovered_device(
    data: DiscoveryResult,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Register a device discovered by an agent."""
    # Check for existing device by IP to prevent duplicates
    existing = await db.execute(
        select(Device).where(Device.ip_address == data.ip_address)
    )
    device = existing.scalar_one_or_none()
    if device:
        # Update existing device with new discovery data
        if data.mac_address:
            device.mac_address = data.mac_address
        if data.hostname:
            device.hostname = data.hostname
        if data.oui_vendor:
            device.oui_vendor = data.oui_vendor
        if data.open_ports is not None:
            device.open_ports = data.open_ports
        if data.os_fingerprint:
            device.os_fingerprint = data.os_fingerprint
        if data.category and data.category != "unknown":
            device.category = data.category
        await db.flush()
        await db.refresh(device)
        await log_action(db, user, "discovery.register_device", "device", device.id,
                         {"ip_address": data.ip_address, "updated": True}, request)
        return {"device_id": device.id, "message": "Device updated with new discovery data"}

    device = Device(
        ip_address=data.ip_address,
        mac_address=data.mac_address,
        hostname=data.hostname,
        oui_vendor=data.oui_vendor,
        open_ports=data.open_ports,
        os_fingerprint=data.os_fingerprint,
        category=data.category,
        status=DeviceStatus.DISCOVERED,
    )
    db.add(device)
    await db.flush()
    await db.refresh(device)
    await log_action(db, user, "discovery.register_device", "device", device.id,
                     {"ip_address": data.ip_address}, request)
    return {"device_id": device.id, "message": "Device registered successfully"}
