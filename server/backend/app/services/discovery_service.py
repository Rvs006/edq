"""Discovery service — device classification and manufacturer/model detection."""

import re
import logging
from typing import Any, Dict, List, Optional

from app.models.device import DeviceCategory

logger = logging.getLogger("edq.services.discovery")

# Known manufacturer keywords found in nmap service banners / OUI vendor strings
MANUFACTURER_KEYWORDS: Dict[str, str] = {
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


def guess_manufacturer(oui_vendor: Optional[str], services: List[Dict[str, Any]]) -> Optional[str]:
    """Guess device manufacturer from OUI vendor string and service banners."""
    search_text = (oui_vendor or "").lower()
    for svc in services:
        search_text += " " + (svc.get("version", "") + " " + svc.get("service", "")).lower()

    for keyword, manufacturer in MANUFACTURER_KEYWORDS.items():
        if keyword in search_text:
            return manufacturer
    return None


def guess_model(services: List[Dict[str, Any]], os_fp: Optional[str]) -> Optional[str]:
    """Attempt to extract a device model from service banners or OS fingerprint."""
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

    if os_fp:
        model_match = re.search(
            r'\b([A-Z]{1,4}[\-][A-Z0-9]{2,}[\-]?[A-Z0-9]*)\b',
            os_fp,
            re.IGNORECASE,
        )
        if model_match:
            return model_match.group(1)

    return None


def build_device_display_name(
    ip_address: Optional[str],
    hostname: Optional[str],
    manufacturer: Optional[str],
    model: Optional[str],
) -> Optional[str]:
    """Return the most useful user-facing label for a device."""
    host = (hostname or "").strip()
    host_lower = host.lower()
    ip = (ip_address or "").strip()
    combined = " ".join(
        part.strip()
        for part in (manufacturer, model)
        if part and part.strip()
    ).strip()

    generic_hosts = {
        "",
        "localhost",
        "unknown",
        "device",
        "e2e run device",
    }

    if combined:
        return combined

    if host_lower not in generic_hosts and host_lower != ip.lower():
        return host

    if manufacturer:
        return manufacturer

    return ip_address


def guess_category(os_fp: Optional[str], services: List[Dict[str, Any]]) -> DeviceCategory:
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
