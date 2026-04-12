"""Helpers for deciding whether a device is currently reachable."""

import asyncio
import logging
from typing import Any

from app.services.tools_client import tools_client

logger = logging.getLogger("edq.connectivity_probe")

DEFAULT_CONNECTIVITY_PORTS = (80, 443, 22, 23, 554, 8080, 8443, 1883, 8883, 502, 47808)
MAX_PROBE_PORTS = 12


def extract_probe_ports(open_ports: Any) -> list[int]:
    """Build a short, stable list of ports to use for TCP reachability probes."""
    ports: list[int] = []
    seen: set[int] = set()

    if isinstance(open_ports, list):
        for item in open_ports:
            port = item.get("port") if isinstance(item, dict) else item
            if isinstance(port, int) and 1 <= port <= 65535 and port not in seen:
                seen.add(port)
                ports.append(port)
            if len(ports) >= MAX_PROBE_PORTS:
                break

    for port in DEFAULT_CONNECTIVITY_PORTS:
        if port not in seen:
            ports.append(port)
            seen.add(port)
        if len(ports) >= MAX_PROBE_PORTS:
            break

    return ports


async def _tcp_probe(ip: str, port: int, timeout: float) -> tuple[int, bool]:
    writer = None
    try:
        _reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=timeout)
        return (port, True)
    except Exception:
        return (port, False)
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass


async def probe_device_connectivity(
    ip: str,
    probe_ports: list[int] | None = None,
    tcp_timeout: float = 3.0,
) -> tuple[bool, str | None]:
    """Return whether the target is reachable via ICMP or a quick TCP probe.

    Runs ICMP and TCP probes in parallel for faster detection.

    Prefer reporting a TCP hit when one exists so callers that inspect the
    probe source can distinguish "host is up" from "host has a testable
    service port open".
    """
    ports = probe_ports or list(DEFAULT_CONNECTIVITY_PORTS[:MAX_PROBE_PORTS])

    # Run ICMP and TCP probes in parallel
    async def _icmp_probe():
        try:
            result = await tools_client.ping(ip, count=1)
            if result.get("exit_code") == 0:
                return (True, "icmp")
        except Exception as exc:
            logger.debug("ICMP probe failed for %s: %s", ip, exc)
        return (False, None)

    async def _tcp_probes():
        results = await asyncio.gather(
            *(_tcp_probe(ip, port, tcp_timeout) for port in ports),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, tuple):
                port, reachable = result
                if reachable:
                    return (True, f"tcp:{port}")
        return (False, None)

    icmp_result, tcp_result = await asyncio.gather(_icmp_probe(), _tcp_probes())

    if tcp_result[0]:
        return tcp_result
    if icmp_result[0]:
        return icmp_result
    return (False, None)
