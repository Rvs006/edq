"""MAC vendor resolution helpers."""

from __future__ import annotations

import re
from typing import Optional

from app.services.tools_client import tools_client

_MAC_HEX_RE = re.compile(r"[^0-9A-Fa-f]+")

_FALLBACK_PREFIX_VENDORS = {
    "000CAB": "Commend International GmbH",
    "2C2D48": "Commend International GmbH",
    "BC6A44": "Commend International GmbH",
    "38D135": "EasyIO Corporation Sdn. Bhd.",
    "00408C": "Axis Communications AB",
    "ACCC8E": "Axis Communications AB",
    "B8A44F": "Axis Communications AB",
    "E82725": "Axis Communications AB",
    "00BC99": "Hangzhou Hikvision Digital Technology Co.,Ltd.",
    "0C75D2": "Hangzhou Hikvision Digital Technology Co.,Ltd.",
    "1012FB": "Hangzhou Hikvision Digital Technology Co.,Ltd.",
    "244845": "Hangzhou Hikvision Digital Technology Co.,Ltd.",
    "2857BE": "Hangzhou Hikvision Digital Technology Co.,Ltd.",
    "4CF5DC": "Hangzhou Hikvision Digital Technology Co.,Ltd.",
    "5850ED": "Hangzhou Hikvision Digital Technology Co.,Ltd.",
}


def normalize_mac(mac: Optional[str]) -> Optional[str]:
    if not mac:
        return None
    hex_only = _MAC_HEX_RE.sub("", mac)
    if len(hex_only) != 12:
        return None
    hex_only = hex_only.upper()
    return ":".join(hex_only[i:i + 2] for i in range(0, 12, 2))


def mac_prefix(mac: Optional[str]) -> Optional[str]:
    normalized = normalize_mac(mac)
    if not normalized:
        return None
    return normalized.replace(":", "")[:6]


def fallback_vendor_for_mac(mac: Optional[str]) -> Optional[str]:
    prefix = mac_prefix(mac)
    if not prefix:
        return None
    return _FALLBACK_PREFIX_VENDORS.get(prefix)


async def resolve_mac_vendor(
    mac: Optional[str],
    current_vendor: Optional[str] = None,
) -> Optional[str]:
    vendor = (current_vendor or "").strip()
    if vendor and vendor.lower() not in {"unknown", "n/a"}:
        return vendor

    normalized = normalize_mac(mac)
    if not normalized:
        return None

    try:
        result = await tools_client.mac_vendor(normalized)
        vendor = str(result.get("vendor") or "").strip()
        if vendor and vendor.lower() not in {"unknown", "n/a"}:
            return vendor
    except Exception:
        pass

    return fallback_vendor_for_mac(normalized)