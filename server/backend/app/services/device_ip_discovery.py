"""Helpers for resolving DHCP device IP addresses from MAC addresses."""

from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.routes.authorized_networks import get_active_networks
from app.services.mac_vendor import normalize_mac, resolve_mac_vendor
from app.services.parsers.nmap_parser import nmap_parser
from app.services.tools_client import (
    describe_tools_error,
    get_tools_error_status,
    tools_client,
)

logger = logging.getLogger("edq.services.device_ip_discovery")

_DEFAULT_DHCP_SCAN_SUBNETS = (
    "192.168.1.0/24",
    "192.168.0.0/24",
    "10.0.0.0/24",
    "172.16.0.0/24",
)
_INVALID_NEIGHBOR_STATES = {"INCOMPLETE", "FAILED"}


def _append_scan_cidr(candidates: list[str], candidate: str) -> None:
    try:
        network = ipaddress.ip_network(candidate, strict=False)
    except ValueError:
        return
    normalized = str(network)
    if normalized not in candidates:
        candidates.append(normalized)


def _append_anchor_subnet(candidates: list[str], host: str, prefix: int = 24) -> None:
    try:
        subnet = ipaddress.ip_network(f"{host}/{prefix}", strict=False)
    except ValueError:
        return
    _append_scan_cidr(candidates, str(subnet))


def build_discovery_scan_ranges(
    authorized_cidrs: list[str],
    detection: dict | None,
) -> list[str]:
    candidates: list[str] = []
    detection = detection or {}
    host_ip = detection.get("host_ip")
    interfaces = detection.get("interfaces") or []

    all_sample_hosts: list[str] = []
    for interface in interfaces:
        for host in interface.get("sample_hosts") or []:
            if isinstance(host, str):
                all_sample_hosts.append(host)
    if isinstance(host_ip, str):
        all_sample_hosts.append(host_ip)

    for interface in interfaces:
        cidr = interface.get("cidr")
        if not isinstance(cidr, str):
            continue
        try:
            network = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            continue

        sample_hosts = [host for host in interface.get("sample_hosts") or [] if isinstance(host, str)]
        if network.network_address.is_link_local:
            for host in sample_hosts:
                _append_anchor_subnet(candidates, host)
            continue

        if network.prefixlen >= 24:
            _append_scan_cidr(candidates, str(network))

        for host in sample_hosts:
            _append_anchor_subnet(candidates, host)

    for cidr in authorized_cidrs:
        try:
            network = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            continue

        if network.network_address.is_link_local:
            for host in all_sample_hosts:
                try:
                    host_addr = ipaddress.ip_address(host)
                except ValueError:
                    continue
                if host_addr in network:
                    _append_anchor_subnet(candidates, host)
            continue

        if network.prefixlen >= 24:
            _append_scan_cidr(candidates, str(network))
            continue

        for host in all_sample_hosts:
            try:
                host_addr = ipaddress.ip_address(host)
            except ValueError:
                continue
            if host_addr in network:
                _append_anchor_subnet(candidates, host)

    if isinstance(host_ip, str):
        try:
            host_addr = ipaddress.ip_address(host_ip)
        except ValueError:
            host_addr = None
        if host_addr and host_addr.is_link_local:
            _append_anchor_subnet(candidates, host_ip)

    if not candidates:
        for subnet in _DEFAULT_DHCP_SCAN_SUBNETS:
            _append_scan_cidr(candidates, subnet)

    return candidates


@dataclass
class DeviceIpDiscoveryResult:
    discovered_ip: str | None = None
    vendor: str | None = None
    scanned_subnets: list[str] = field(default_factory=list)
    successful_scans: int = 0
    last_scan_error: str | None = None
    error_status: int | None = None


def _normalize_neighbor_entries(payload: dict[str, Any] | list[Any] | None) -> list[dict[str, str | None]]:
    raw_entries = payload
    if isinstance(payload, dict):
        raw_entries = payload.get("entries", [])
    if not isinstance(raw_entries, list):
        return []

    entries: list[dict[str, str | None]] = []
    for item in raw_entries:
        if not isinstance(item, dict):
            continue
        ip = str(item.get("ip") or "").strip()
        mac = normalize_mac(item.get("mac"))
        state = str(item.get("state") or "").strip().upper() or None
        vendor = str(item.get("vendor") or "").strip() or None
        if not ip or not mac or state in _INVALID_NEIGHBOR_STATES:
            continue
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            continue
        entries.append(
            {
                "ip": ip,
                "mac": mac,
                "vendor": vendor,
                "state": state,
            }
        )
    return entries


async def get_neighbor_entries(subnet: str | None = None) -> list[dict[str, str | None]]:
    try:
        payload = await tools_client.neighbors(subnet=subnet)
    except Exception as exc:
        logger.debug("Neighbor cache lookup failed for %s: %s", subnet or "all", exc)
        return []
    return _normalize_neighbor_entries(payload)


def enrich_hosts_with_neighbor_entries(
    hosts: list[dict[str, Any]],
    neighbor_entries: list[dict[str, str | None]],
) -> list[dict[str, Any]]:
    if not hosts or not neighbor_entries:
        return hosts

    entries_by_ip = {
        str(entry.get("ip")): entry
        for entry in neighbor_entries
        if entry.get("ip")
    }
    for host in hosts:
        candidate_ip = str(host.get("ip") or "").strip()
        if not candidate_ip:
            continue
        neighbor = entries_by_ip.get(candidate_ip)
        if not neighbor:
            continue
        if not host.get("mac") and neighbor.get("mac"):
            host["mac"] = neighbor["mac"]
        if not host.get("vendor") and neighbor.get("vendor"):
            host["vendor"] = neighbor["vendor"]
    return hosts


def find_neighbor_entry_for_mac(
    normalized_mac: str,
    neighbor_entries: list[dict[str, str | None]],
) -> dict[str, str | None] | None:
    for entry in neighbor_entries:
        if entry.get("mac") == normalized_mac:
            return entry
    return None


async def discover_ip_for_mac(
    db: AsyncSession,
    mac_address: str,
) -> DeviceIpDiscoveryResult:
    normalized_mac = normalize_mac(mac_address)
    if not normalized_mac:
        return DeviceIpDiscoveryResult(
            last_scan_error="Invalid MAC address supplied for discovery",
            error_status=400,
        )

    authorized_networks = await get_active_networks(db)
    authorized_cidrs = [network.cidr for network in authorized_networks if network.cidr]

    detection = None
    try:
        detection = await tools_client.detect_networks()
    except Exception as exc:
        logger.warning("Network detection failed during DHCP IP discovery: %s", exc)

    subnets_to_scan = build_discovery_scan_ranges(authorized_cidrs, detection)
    result = DeviceIpDiscoveryResult(scanned_subnets=subnets_to_scan)

    for subnet in subnets_to_scan:
        try:
            neighbor_entries = await get_neighbor_entries(subnet=subnet)
            neighbor_match = find_neighbor_entry_for_mac(normalized_mac, neighbor_entries)
            if neighbor_match and neighbor_match.get("ip"):
                result.discovered_ip = neighbor_match["ip"]
                result.vendor = await resolve_mac_vendor(
                    neighbor_match.get("mac"),
                    neighbor_match.get("vendor"),
                )
                return result

            scan_result = await tools_client.nmap(
                target=subnet,
                args=["-sn", "-PR"],
                timeout=30,
            )
            result.successful_scans += 1
            hosts = nmap_parser.parse_host_discovery(scan_result.get("stdout", ""))
            for host in hosts:
                found_mac = normalize_mac(str(host.get("mac") or ""))
                candidate_ip = str(host.get("ip") or "").strip()
                if found_mac != normalized_mac or not candidate_ip:
                    continue
                try:
                    ipaddress.ip_address(candidate_ip)
                except ValueError:
                    logger.warning(
                        "Ignoring invalid discovered IP %s for MAC %s",
                        candidate_ip,
                        normalized_mac,
                    )
                    continue
                result.discovered_ip = candidate_ip
                result.vendor = await resolve_mac_vendor(found_mac, host.get("vendor"))
                return result

            neighbor_entries = await get_neighbor_entries(subnet=subnet)
            neighbor_match = find_neighbor_entry_for_mac(normalized_mac, neighbor_entries)
            if neighbor_match and neighbor_match.get("ip"):
                result.discovered_ip = neighbor_match["ip"]
                result.vendor = await resolve_mac_vendor(
                    neighbor_match.get("mac"),
                    neighbor_match.get("vendor"),
                )
                return result
        except Exception as exc:
            result.last_scan_error = describe_tools_error(
                exc,
                fallback=f"Discovery scan failed on {subnet}",
            )
            result.error_status = get_tools_error_status(exc)
            logger.warning("ARP scan on %s failed: %s", subnet, exc)

    return result