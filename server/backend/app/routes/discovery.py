"""Discovery routes — device auto-detection pipeline."""

import base64
import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.models.device import Device, DeviceCategory, DeviceStatus
from app.models.user import User
from app.schemas.device import DiscoveryRequest
from app.security.auth import get_current_active_user
from app.services.tools_client import tools_client
from app.services.parsers.nmap_parser import nmap_parser

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
    category: str = "unknown"
    status: str = "discovered"
    is_new: bool = True


def _decode_output_file(raw: Dict[str, Any]) -> str:
    """Decode base64-encoded output_file from tools sidecar response."""
    output_file = raw.get("output_file", "")
    if not output_file:
        return ""
    try:
        return base64.b64decode(output_file).decode("utf-8", errors="replace")
    except Exception:
        return output_file if isinstance(output_file, str) else ""




# Known manufacturer keywords found in nmap service banners / OUI vendor strings
_MANUFACTURER_KEYWORDS: Dict[str, str] = {
    "axis": "Axis Communications",
    "hikvision": "Hikvision",
    "dahua": "Dahua Technology",
    "pelco": "Pelco (Motorola)",
    "bosch": "Bosch Security",
    "honeywell": "Honeywell",
    "siemens": "Siemens",
    "schneider": "Schneider Electric",
    "2n": "2N Telekomunikace",
    "sauter": "Sauter AG",
    "easyio": "EasyIO",
    "hanwha": "Hanwha Techwin",
    "samsung": "Samsung",
    "panasonic": "Panasonic",
    "vivotek": "Vivotek",
    "mobotix": "Mobotix",
    "arecont": "Arecont Vision",
    "geovision": "GeoVision",
    "acti": "ACTi",
    "ubiquiti": "Ubiquiti",
    "mikrotik": "MikroTik",
    "trendnet": "TRENDnet",
    "dlink": "D-Link",
    "d-link": "D-Link",
    "tp-link": "TP-Link",
    "ruckus": "Ruckus Networks",
    "aruba": "Aruba Networks",
    "cisco": "Cisco",
    "johnson controls": "Johnson Controls",
    "trane": "Trane Technologies",
    "carrier": "Carrier Global",
    "lutron": "Lutron Electronics",
    "crestron": "Crestron Electronics",
    "control4": "Control4",
}


def _guess_manufacturer(oui_vendor: Optional[str], services: List[Dict[str, Any]]) -> Optional[str]:
    """Guess device manufacturer from OUI vendor string and service banners."""
    search_text = (oui_vendor or "").lower()
    for svc in services:
        search_text += " " + (svc.get("version", "") + " " + svc.get("service", "")).lower()

    for keyword, manufacturer in _MANUFACTURER_KEYWORDS.items():
        if keyword in search_text:
            return manufacturer
    return None


def _guess_model(services: List[Dict[str, Any]], os_fp: Optional[str]) -> Optional[str]:
    """Attempt to extract a device model from service banners or OS fingerprint."""
    # Check service product/version strings for model numbers
    for svc in services:
        version = svc.get("version", "")
        if not version:
            continue
        # Match patterns like "IPC-HDW5", "P3245-V", "EY-RC504", "FW-08"
        model_match = re.search(
            r'\b([A-Z]{1,4}[\-]?[A-Z0-9]{2,}[\-][A-Z0-9]+)\b',
            version,
            re.IGNORECASE,
        )
        if model_match:
            return model_match.group(1)

    # Check OS fingerprint for model info
    if os_fp:
        model_match = re.search(
            r'\b([A-Z]{1,4}[\-][A-Z0-9]{2,}[\-]?[A-Z0-9]*)\b',
            os_fp,
            re.IGNORECASE,
        )
        if model_match:
            return model_match.group(1)

    return None


def _guess_category(os_fp: Optional[str], services: List[Dict[str, Any]]) -> DeviceCategory:
    """Heuristic: guess device category from OS fingerprint and service list."""
    service_names = " ".join(s.get("service", "") + " " + s.get("version", "") for s in services).lower()
    os_lower = (os_fp or "").lower()

    if any(kw in service_names for kw in ("rtsp", "onvif", "axis", "hikvision", "dahua", "pelco", "hanwha", "vivotek")):
        return DeviceCategory.CAMERA
    if any(kw in service_names for kw in ("bacnet", "easyio", "sauter", "hvac", "lonworks", "knx")):
        return DeviceCategory.CONTROLLER
    if any(kw in service_names for kw in ("sip", "intercom", "2n")):
        return DeviceCategory.INTERCOM
    if any(kw in service_names for kw in ("access", "paxton", "gallagher", "hid")):
        return DeviceCategory.ACCESS_PANEL
    if any(kw in service_names for kw in ("lutron", "dali", "lighting", "dmx")):
        return DeviceCategory.LIGHTING
    if any(kw in service_names for kw in ("trane", "carrier", "thermostat", "chiller")):
        return DeviceCategory.HVAC
    if any(kw in service_names for kw in ("mqtt", "zigbee", "z-wave", "lorawan", "sensor")):
        return DeviceCategory.IOT_SENSOR
    if any(kw in service_names for kw in ("meter", "modbus", "iec")):
        return DeviceCategory.METER
    if "camera" in os_lower or "video" in os_lower:
        return DeviceCategory.CAMERA
    if "controller" in os_lower or "plc" in os_lower:
        return DeviceCategory.CONTROLLER
    return DeviceCategory.UNKNOWN


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
) -> tuple[Device, bool]:
    """Create or update a device record. Returns (device, is_new)."""
    result = await db.execute(select(Device).where(Device.ip_address == ip))
    device = result.scalar_one_or_none()
    is_new = device is None

    # Auto-detect manufacturer and model from scan data
    auto_manufacturer = _guess_manufacturer(vendor, open_ports or [])
    auto_model = _guess_model(open_ports or [], os_fp)

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
        )
        db.add(device)
    else:
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
        device.category = category
        device.status = DeviceStatus.IDENTIFIED

    await db.flush()
    await db.refresh(device)
    return device, is_new


@router.post("/scan")
async def initiate_discovery(
    data: DiscoveryRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Run nmap discovery against a single IP or subnet.

    - ip_address provided: full service detection + OS fingerprint (-sV -O -p-)
    - subnet provided: ping sweep (-sn) to list live hosts
    """
    target = data.ip_address or data.subnet
    if not target:
        raise HTTPException(status_code=400, detail="Provide either ip_address or subnet")

    discovered_devices: List[Dict[str, Any]] = []

    if data.ip_address:
        try:
            raw = await tools_client.nmap(
                data.ip_address,
                ["-sV", "-O", "-p-", "--max-rate", "300", "-oX", "-"],
                timeout=300,
            )
        except Exception as exc:
            logger.exception("Nmap service scan failed for %s: %s", data.ip_address, exc)
            raise HTTPException(status_code=502, detail=f"Tools sidecar error: {exc}")

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

        category = _guess_category(os_fp, open_ports)

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
            "category": device.category.value if hasattr(device.category, "value") else str(device.category),
            "status": device.status.value if hasattr(device.status, "value") else str(device.status),
            "is_new": is_new,
        })

    elif data.subnet:
        try:
            raw = await tools_client.nmap(
                data.subnet,
                ["-sn"],
                timeout=120,
            )
        except Exception as exc:
            logger.exception("Nmap ping sweep failed for %s: %s", data.subnet, exc)
            raise HTTPException(status_code=502, detail=f"Tools sidecar error: {exc}")

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
                "category": device.category.value if hasattr(device.category, "value") else str(device.category),
                "status": device.status.value if hasattr(device.status, "value") else str(device.status),
                "is_new": is_new,
            })

    return {
        "status": "complete",
        "target": target,
        "devices_found": len(discovered_devices),
        "devices": discovered_devices,
    }


@router.post("/register-device")
async def register_discovered_device(
    data: DiscoveryResult,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Register a device discovered by an agent."""
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
