"""Shared connectivity and IP-discovery helpers for test execution."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import AddressingMode, Device
from app.services.connectivity_probe import extract_probe_ports, probe_device_connectivity
from app.services.device_ip_discovery import discover_ip_for_mac


@dataclass(slots=True)
class DeviceExecutionReadiness:
    reason: str
    probe_ports: list[int]
    reachable: bool
    probe_method: str | None
    has_tcp_service: bool
    can_execute: bool
    missing_ip: bool
    dhcp_missing_ip: bool
    pause_message: str | None


def device_uses_dhcp(device: Device | None) -> bool:
    if not device:
        return False
    mode = getattr(device.addressing_mode, "value", device.addressing_mode)
    return mode == AddressingMode.DHCP.value


async def autodiscover_device_ip_if_needed(
    db: AsyncSession,
    device: Device | None,
    *,
    logger: logging.Logger | None = None,
) -> bool:
    if not device or device.ip_address or not device_uses_dhcp(device) or not device.mac_address:
        return False

    return await _refresh_dhcp_device_ip(
        db,
        device,
        logger=logger,
        log_context="before test execution",
    )


async def _refresh_dhcp_device_ip(
    db: AsyncSession,
    device: Device,
    *,
    logger: logging.Logger | None = None,
    log_context: str = "before test execution",
) -> bool:
    previous_ip = device.ip_address

    discovery = await discover_ip_for_mac(db, device.mac_address)
    if not discovery.discovered_ip:
        return False

    device.ip_address = discovery.discovered_ip
    if discovery.vendor and not device.oui_vendor:
        device.oui_vendor = discovery.vendor
    if discovery.vendor and not device.manufacturer:
        device.manufacturer = discovery.vendor
    await db.flush()
    await db.refresh(device)

    if logger:
        if previous_ip and previous_ip != device.ip_address:
            logger.info(
                "Refreshed DHCP device %s IP address from %s to %s %s",
                device.mac_address,
                previous_ip,
                device.ip_address,
                log_context,
            )
        elif previous_ip != device.ip_address:
            logger.info(
                "Auto-discovered DHCP device %s IP address as %s %s",
                device.mac_address,
                device.ip_address,
                log_context,
            )
    return True


async def probe_device_execution_readiness(device: Device | None) -> DeviceExecutionReadiness:
    if device is None:
        return DeviceExecutionReadiness(
            reason="missing_device",
            probe_ports=[],
            reachable=False,
            probe_method=None,
            has_tcp_service=False,
            can_execute=False,
            missing_ip=True,
            dhcp_missing_ip=False,
            pause_message=None,
        )

    if not device.ip_address:
        return DeviceExecutionReadiness(
            reason="missing_ip",
            probe_ports=[],
            reachable=False,
            probe_method=None,
            has_tcp_service=False,
            can_execute=False,
            missing_ip=True,
            dhcp_missing_ip=device_uses_dhcp(device),
            pause_message=None,
        )

    probe_ports = extract_probe_ports(device.open_ports)
    reachable, probe_method = await probe_device_connectivity(
        device.ip_address,
        probe_ports,
    )
    has_tcp_service = bool(probe_method) and probe_method.startswith("tcp:")
    can_execute = has_tcp_service or (reachable and not device.open_ports)

    if can_execute:
        reason = "ready"
        pause_message = None
    elif reachable:
        reason = "service_unreachable"
        pause_message = (
            f"Device {device.ip_address} is reachable but no supported service "
            "ports are open yet. Testing is paused until a service port becomes reachable."
        )
    else:
        reason = "unreachable"
        pause_message = (
            f"Target device {device.ip_address} is unreachable from this "
            "network. Testing is paused until connectivity is restored."
        )

    return DeviceExecutionReadiness(
        reason=reason,
        probe_ports=probe_ports,
        reachable=reachable,
        probe_method=probe_method,
        has_tcp_service=has_tcp_service,
        can_execute=can_execute,
        missing_ip=False,
        dhcp_missing_ip=False,
        pause_message=pause_message,
    )


async def ensure_device_execution_readiness(
    db: AsyncSession,
    device: Device | None,
    *,
    logger: logging.Logger | None = None,
) -> DeviceExecutionReadiness:
    await autodiscover_device_ip_if_needed(db, device, logger=logger)
    readiness = await probe_device_execution_readiness(device)
    if (
        device
        and readiness.reason == "unreachable"
        and device_uses_dhcp(device)
        and device.mac_address
        and device.ip_address
    ):
        previous_ip = device.ip_address
        refreshed = await _refresh_dhcp_device_ip(
            db,
            device,
            logger=logger,
            log_context="after connectivity loss",
        )
        if refreshed and device.ip_address != previous_ip:
            readiness = await probe_device_execution_readiness(device)
    return readiness
