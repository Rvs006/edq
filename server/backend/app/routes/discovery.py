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

from app.config import settings
from app.models.database import get_db
from app.models.device import Device, DeviceCategory, DeviceStatus
from app.models.project import Project
from app.models.user import User
from app.schemas.device import DiscoveryRequest
from app.security.auth import get_current_active_user
from app.middleware.rate_limit import check_rate_limit
from app.services.connectivity_probe import probe_device_connectivity
from app.services.mac_vendor import resolve_mac_vendor
from app.services.discovery_service import (
    build_device_display_name,
    guess_category,
    guess_manufacturer,
    guess_model,
)
from app.services.tools_client import describe_tools_error, get_tools_error_status, tools_client
from app.services.parsers.nmap_parser import nmap_parser
from app.utils.audit import log_action
from app.utils.datetime import utcnow_naive

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
    vendor = await resolve_mac_vendor(mac, vendor)

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

    # Only promote status / bump last_seen_at when the probe produced
    # at least one piece of positive evidence the device is actually there.
    positive_signal = bool(mac) or bool(open_ports) or bool(os_fp) or bool(hostname)

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
            last_seen_at=utcnow_naive() if positive_signal else None,
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
        if positive_signal:
            device.status = DeviceStatus.IDENTIFIED
            device.last_seen_at = utcnow_naive()
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
    project_id = await _validate_project_id(db, data.project_id)
    target = data.ip_address or data.subnet
    if not target:
        raise HTTPException(status_code=400, detail="Provide either ip_address or subnet")
    # Global cap first (no scope) to bound sweep-style abuse across many targets.
    check_rate_limit(
        request,
        max_requests=settings.DISCOVERY_GLOBAL_RATE_LIMIT_PER_MINUTE,
        window_seconds=60,
        action="discovery_scan_global",
    )
    check_rate_limit(
        request,
        max_requests=settings.DISCOVERY_RATE_LIMIT_PER_MINUTE,
        window_seconds=60,
        action="discovery_scan",
        scope=target,
    )

    discovered_devices: List[Dict[str, Any]] = []
    unreachable_skipped = 0

    if data.ip_address:
        # Strict pre-flight: flush ARP cache for this IP, then do a fresh
        # TCP + ICMP probe.  ARP cache can make probes succeed for ~30s
        # after a cable is unplugged, causing false "device found" results.
        scan_timeout = 300
        # Run a quick nmap ping-only probe with --send-ip to bypass ARP
        # cache. This forces a fresh ICMP/TCP probe that won't succeed
        # from a stale ARP entry after cable is unplugged.
        try:
            arp_flush_scan = await tools_client.nmap(
                data.ip_address,
                [
                    "--send-ip",
                    "-sn",
                    "-n",
                    "-PE",
                    "-PS22,80,135,443,445,3389,8080",
                    "-PA80,443",
                    "--max-retries",
                    "2",
                    "--host-timeout",
                    "8s",
                    "-oX",
                    "-",
                ],
                timeout=12,
            )
            arp_parsed = nmap_parser.parse_xml(arp_flush_scan.get("stdout", ""))
            arp_host_alive = any(
                h.get("ip") == data.ip_address and h.get("status") == "up"
                for h in arp_parsed.get("hosts", [])
            )
        except Exception:
            arp_host_alive = False

        try:
            is_reachable, probe_source = await asyncio.wait_for(
                probe_device_connectivity(data.ip_address),
                timeout=6.0,
            )
        except asyncio.TimeoutError:
            logger.warning("Connectivity pre-check timed out for %s", data.ip_address)
            is_reachable = False
            probe_source = None
        except Exception:
            logger.exception("Connectivity pre-check crashed for %s", data.ip_address)
            is_reachable = False
            probe_source = None

        # Trust TCP-level reachability (requires a real SYN-ACK from the
        # target's OS) or nmap -sn confirmation. Do NOT trust ICMP-only —
        # in Docker NAT, stale ARP caches + proxy-ARP by routers/gateways
        # can make ICMP ping succeed for an unplugged device for minutes.
        # Strong reachability signals:
        #  - "tcp:<port>"         — open service, device's OS answered SYN-ACK
        #  - "tcp_refused:<port>" — device's TCP stack sent RST (alive, firewalled port)
        #  - "icmp:<N>ms"         — ICMP reply with real LAN latency (>=1ms),
        #                           proves real network hop (not localhost loopback)
        tcp_reachable = bool(
            is_reachable
            and probe_source
            and (
                str(probe_source).startswith("tcp")
                or str(probe_source).startswith("icmp:")
            )
        )
        # AND-gate: BOTH signals (TCP/ICMP probe AND nmap ARP-bypass ping)
        # must agree the host is up before we proceed to a full scan.
        # Rationale: a stale ARP entry can make nmap -sn show "up" for
        # minutes after a cable is pulled; requiring a fresh probe to also
        # confirm eliminates ghost results.
        if not tcp_reachable or not arp_host_alive:
            if not tcp_reachable and not arp_host_alive:
                reason = "unreachable"
            elif not tcp_reachable:
                reason = "probe_down_arp_up"
            else:
                reason = "probe_up_arp_down"
            if is_reachable and str(probe_source or "") == "icmp":
                message = (
                    f"Device {data.ip_address} only answered ICMP. This is not "
                    "trustworthy in Docker/NAT environments (stale ARP can make a "
                    "removed device appear to reply). Check the cable and power."
                )
            else:
                message = (
                    f"Device {data.ip_address} is not reachable. "
                    "Check that the cable is connected and the device is powered on."
                )
            logger.info(
                "Device %s failed reachability gate (%s) — skipping nmap scan",
                data.ip_address,
                reason,
            )
            await log_action(db, user, "discovery.scan", "discovery", data.ip_address,
                             {"devices_found": 0, "reason": reason}, request)
            return {
                "status": "complete",
                "target": data.ip_address,
                "devices_found": 0,
                "devices": [],
                "message": message,
            }

        logger.debug("Connectivity pre-check confirmed %s via %s", data.ip_address, probe_source)

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

        probe_sem = asyncio.Semaphore(8)

        async def _gated_probe(ip: str) -> bool:
            async with probe_sem:
                try:
                    reachable, _source = await asyncio.wait_for(
                        probe_device_connectivity(ip),
                        timeout=6.0,
                    )
                    return bool(reachable)
                except asyncio.TimeoutError:
                    logger.warning("Subnet probe timed out for %s", ip)
                    return False
                except Exception:
                    logger.exception("Subnet probe crashed for %s", ip)
                    return False

        probe_results = await asyncio.gather(
            *(_gated_probe(host["ip"]) for host in hosts)
        ) if hosts else []

        for host, is_reachable in zip(hosts, probe_results):
            if not is_reachable:
                unreachable_skipped += 1
                logger.info(
                    "Subnet discovery skipping ghost host %s (probe unreachable)",
                    host.get("ip"),
                )
                continue

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
                     {"devices_found": len(discovered_devices),
                      "unreachable_skipped": unreachable_skipped}, request)

    return {
        "status": "complete",
        "target": target,
        "devices_found": len(discovered_devices),
        "devices": discovered_devices,
        "unreachable_skipped": unreachable_skipped,
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

    try:
        is_reachable, _probe_source = await asyncio.wait_for(
            probe_device_connectivity(data.ip_address),
            timeout=6.0,
        )
    except asyncio.TimeoutError:
        logger.warning("Register-device probe timed out for %s", data.ip_address)
        is_reachable = False
    except Exception:
        logger.exception("Register-device probe crashed for %s", data.ip_address)
        is_reachable = False

    if not is_reachable:
        raise HTTPException(
            status_code=422,
            detail=(
                "Host not reachable from backend; refusing to register unverified "
                "device. If this is an agent report from a remote network segment, "
                "include X-Agent-Key and use the dedicated agent-registration "
                "path."
            ),
        )

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
