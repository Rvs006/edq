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
        if re.search(rf'\b{re.escape(keyword)}\b', search_text):
            return manufacturer
    return None


def guess_model(services: List[Dict[str, Any]], os_fp: Optional[str]) -> Optional[str]:
    """Attempt to extract a device model from service banners or OS fingerprint."""
    # Common protocol/version strings that superficially match the model pattern
    _EXCLUDE_MODELS = {"TLS-1", "SSL-3", "HTTP-1", "SSH-2", "HTTP-GET"}
    _model_pattern = re.compile(
        r'\b([A-Z]{1,4}[\-]?[A-Z0-9]{2,}[\-][A-Z0-9]+)\b', re.IGNORECASE
    )

    for svc in services:
        version = svc.get("version", "")
        if not version:
            continue
        # Match patterns like "IPC-HDW5", "P3245-V", "EY-RC504", "FW-08"
        model_match = _model_pattern.search(version)
        if model_match:
            candidate = model_match.group(1)
            if candidate.upper() not in _EXCLUDE_MODELS and re.search(r'\d', candidate):
                return candidate

    if os_fp:
        model_match = re.search(
            r'\b([A-Z]{1,4}[\-][A-Z0-9]{2,}[\-]?[A-Z0-9]*)\b',
            os_fp,
            re.IGNORECASE,
        )
        if model_match:
            candidate = model_match.group(1)
            if candidate.upper() not in _EXCLUDE_MODELS and re.search(r'\d', candidate):
                return candidate

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

    # Prefer a meaningful hostname over everything else
    if host_lower not in generic_hosts and host_lower != ip.lower():
        return host

    # Fall back to manufacturer + model combined
    if combined:
        return combined

    if manufacturer:
        return manufacturer

    return ip_address


def guess_category(os_fp: Optional[str], services: List[Dict[str, Any]]) -> DeviceCategory:
    """Heuristic: guess device category from OS fingerprint and service list."""
    service_names = " ".join(s.get("service", "") + " " + s.get("version", "") for s in services).lower()
    os_lower = (os_fp or "").lower()

    def _any_kw(text: str, keywords) -> bool:
        return any(re.search(rf'\b{re.escape(kw)}\b', text) for kw in keywords)

    if _any_kw(service_names, ("rtsp", "onvif", "axis", "hikvision", "dahua", "pelco", "hanwha", "vivotek")):
        return DeviceCategory.CAMERA
    if _any_kw(service_names, ("bacnet", "easyio", "sauter", "hvac", "lonworks", "knx")):
        return DeviceCategory.CONTROLLER
    if _any_kw(service_names, ("sip", "intercom", "2n")):
        return DeviceCategory.INTERCOM
    if _any_kw(service_names, ("access", "paxton", "gallagher", "hid")):
        return DeviceCategory.ACCESS_PANEL
    if _any_kw(service_names, ("lutron", "dali", "lighting", "dmx")):
        return DeviceCategory.LIGHTING
    if _any_kw(service_names, ("trane", "carrier", "thermostat", "chiller")):
        return DeviceCategory.HVAC
    if _any_kw(service_names, ("mqtt", "zigbee", "z-wave", "lorawan", "sensor")):
        return DeviceCategory.IOT_SENSOR
    if _any_kw(service_names, ("meter", "modbus", "iec")):
        return DeviceCategory.METER
    if re.search(r'\b(camera|video)\b', os_lower):
        return DeviceCategory.CAMERA
    if re.search(r'\b(controller|plc)\b', os_lower):
        return DeviceCategory.CONTROLLER
    return DeviceCategory.UNKNOWN
