"""CVE auto-correlation — matches discovered services to known vulnerabilities."""

import logging
import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("edq.cve_correlator")


def build_cpe_queries(device_data: dict) -> list[dict]:
    """Build CVE search queries from device discovery data.

    Takes device info (open_ports, os_fingerprint, manufacturer, model)
    and returns a list of search queries for the NVD API.
    """
    queries: list[dict] = []

    open_ports = device_data.get("open_ports") or []
    for port_info in open_ports:
        service = port_info.get("service", "")
        product = port_info.get("product", "") or service
        version = port_info.get("version", "")
        if product and version and len(version) > 2:
            normalized_version = str(version)
            if normalized_version.lower().startswith(str(product).lower()):
                normalized_version = normalized_version[len(str(product)):].strip()
            # Extract product and version from service banner
            queries.append({
                "product": product,
                "version": normalized_version,
                "source": f"port {port_info.get('port', '?')}",
            })

    # OS fingerprint
    os_fp = device_data.get("os_fingerprint") or ""
    if os_fp and len(os_fp) > 3:
        queries.append({"product": os_fp, "version": "", "source": "OS fingerprint"})

    # Manufacturer + model combination (common for IoT/building devices)
    manufacturer = device_data.get("manufacturer") or ""
    model = device_data.get("model") or ""
    if manufacturer and model:
        queries.append({
            "product": f"{manufacturer} {model}",
            "version": "",
            "source": "manufacturer/model",
        })
    elif manufacturer and len(manufacturer) > 2:
        queries.append({
            "product": manufacturer,
            "version": "",
            "source": "manufacturer",
        })

    return queries


async def correlate_device_cves(device_id: str, db: AsyncSession) -> list[dict]:
    """Look up CVE search queries for a device based on its discovered services.

    Returns list of {"query": {...}, "device_id": str}.
    The query dict contains product, version, and source fields that the
    frontend can use to trigger actual NVD lookups via the existing
    ``POST /api/v1/cve/lookup`` endpoint.
    """
    from app.models.device import Device

    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        return []

    device_data = {
        "open_ports": device.open_ports or [],
        "os_fingerprint": device.os_fingerprint,
        "manufacturer": device.manufacturer,
        "model": device.model,
    }

    queries = build_cpe_queries(device_data)
    logger.info(
        "Built %d CVE correlation queries for device %s (%s)",
        len(queries),
        device_id,
        device.ip_address,
    )
    return [{"query": q, "device_id": device_id} for q in queries]
