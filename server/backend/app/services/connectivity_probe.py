"""Helpers for deciding whether a device is currently reachable."""

import asyncio
import logging
import re
from typing import Any

from app.services.tools_client import tools_client

# Match ICMP ping reply latency from stdout: "time=7.47 ms" / "time<1 ms"
_PING_LATENCY_RE = re.compile(r"time[=<]\s*([\d.]+)\s*ms", re.IGNORECASE)

# Sub-50us ICMP replies indicate localhost loopback / Docker NAT self-hit
# (loopback typically answers in <10us). Real LAN round-trip on modern
# 1/10GbE with a local switch is ~0.1–2ms; a 1ms floor would falsely
# reject many legitimate LAN replies. Use 50us (0.05ms) as the floor so
# we only exclude clear-cut loopback/self-hit cases.
_REAL_LAN_LATENCY_THRESHOLD_MS = 0.05

logger = logging.getLogger("edq.connectivity_probe")

DEFAULT_CONNECTIVITY_PORTS = (
    # Smart building / IoT (primary EDQ target)
    80, 443, 22, 23, 554, 8080, 8443, 1883, 8883, 502, 47808,
    # Common Windows / general-purpose (needed because a "tcp_refused" from any
    # of these is proof the TCP stack is alive, even if the service isn't)
    135, 139, 445, 3389, 5000, 8000, 5985, 9100,
)
MAX_PROBE_PORTS = 20


def extract_known_probe_ports(open_ports: Any) -> list[int]:
    """Return only ports already discovered or saved for the device."""
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

    return ports


def extract_probe_ports(open_ports: Any) -> list[int]:
    """Build a short, stable list of ports to use for TCP reachability probes."""
    ports = extract_known_probe_ports(open_ports)
    seen: set[int] = set(ports)

    for port in DEFAULT_CONNECTIVITY_PORTS:
        if port not in seen:
            ports.append(port)
            seen.add(port)
        if len(ports) >= MAX_PROBE_PORTS:
            break

    return ports


async def _tcp_probe(ip: str, port: int, timeout: float) -> tuple[int, str]:
    """Probe a single TCP port.

    Returns (port, outcome) where outcome is one of:
      - "open"     — SYN-ACK received (device's TCP stack answered, service listening)
      - "refused"  — RST received (device's TCP stack answered, no listener on this port)
      - "none"     — timeout / unreachable / other; no evidence the device is alive

    "refused" is treated as strong proof-of-life by callers: a TCP RST can only
    originate from a real TCP stack at the target IP; ARP cache entries, proxy-ARP,
    and switch CAM forwarding cannot fabricate one.
    """
    try:
            payload = await tools_client.tcp_probe(
                ip,
                ports=[port],
                connect_timeout=timeout,
                concurrency=1,
                max_hosts=1,
                timeout=30,
                stop_on_first_open=True,
            )
    except Exception:
        return (port, "none")

    hosts = payload.get("hosts", []) if isinstance(payload, dict) else []
    host = hosts[0] if hosts and isinstance(hosts[0], dict) else {}
    for response in host.get("responses", []) if isinstance(host, dict) else []:
        if response.get("port") == port:
            return (port, response.get("state") or "none")
    return (port, "none")


async def probe_device_connectivity(
    ip: str,
    probe_ports: list[int] | None = None,
    tcp_timeout: float = 2.0,
    trust_icmp_only: bool = False,
) -> tuple[bool, str | None]:
    """Return whether the target is reachable via ICMP or a quick TCP probe.

    Runs ICMP and TCP probes in parallel for faster detection.

    Prefer reporting a TCP hit when one exists so callers that inspect the
    probe source can distinguish "host is up" from "host has a testable
    service port open".

    Set trust_icmp_only for in-run cable monitoring. Discovery keeps it false
    so stale ARP ghosts still need TCP or nmap corroboration.
    """
    ports = probe_ports or list(DEFAULT_CONNECTIVITY_PORTS[:MAX_PROBE_PORTS])

    # Run ICMP and TCP probes in parallel
    async def _icmp_probe():
        try:
            result = await tools_client.ping(ip, count=1)
            if result.get("exit_code") == 0:
                stdout = result.get("stdout", "")
                match = _PING_LATENCY_RE.search(stdout)
                if match:
                    try:
                        latency_ms = float(match.group(1))
                    except ValueError:
                        latency_ms = 0.0
                    if latency_ms >= _REAL_LAN_LATENCY_THRESHOLD_MS:
                        # Real LAN round-trip — trusted proof of life.
                        return (True, f"icmp:{latency_ms:.2f}ms")
                # Replied but either no latency parsed, or sub-ms (possible
                # loopback/self-hit). Flag as weak ICMP; caller may retry.
                return (True, "icmp")
        except Exception as exc:
            logger.debug("ICMP probe failed for %s: %s", ip, exc)
        return (False, None)

    async def _tcp_probes():
        try:
            payload = await tools_client.tcp_probe(
                ip,
                ports=ports,
                connect_timeout=tcp_timeout,
                concurrency=min(len(ports), MAX_PROBE_PORTS),
                max_hosts=1,
                timeout=30,
                stop_on_first_open=True,
            )
        except Exception as exc:
            logger.debug("TCP probe failed for %s via scanner agent: %s", ip, exc)
            return (False, None)

        hosts = payload.get("hosts", []) if isinstance(payload, dict) else []
        host = hosts[0] if hosts and isinstance(hosts[0], dict) else {}
        results = host.get("responses", []) if isinstance(host, dict) else []
        refused_port: int | None = None
        for result in results:
            if not isinstance(result, dict):
                continue
            port = result.get("port")
            outcome = result.get("state")
            if not isinstance(port, int):
                continue
            if outcome == "open":
                return (True, f"tcp:{port}")
            if outcome == "refused" and refused_port is None:
                refused_port = port
        # Prefer an "open" service when available; fall back to "refused" as
        # proof-of-life (the device's TCP stack sent a RST — un-spoofable by
        # ARP cache / proxy-ARP / CAM forwarding).
        if refused_port is not None:
            return (True, f"tcp_refused:{refused_port}")
        return (False, None)

    icmp_result, tcp_result = await asyncio.gather(_icmp_probe(), _tcp_probes())

    if tcp_result[0]:
        return tcp_result
    if icmp_result[0]:
        # Trust ICMP when latency >= _REAL_LAN_LATENCY_THRESHOLD_MS (50us).
        # Sub-50us replies are effectively loopback speeds — treat as
        # untrusted and fall through to the nmap tiebreaker.
        icmp_source = icmp_result[1] or ""
        if icmp_source.startswith("icmp:"):
            return icmp_result
        if trust_icmp_only:
            return icmp_result
        # ICMP answered but none of our DEFAULT_CONNECTIVITY_PORTS responded.
        # Could be (a) a real device with services on an obscure port, or
        # (b) an ARP-cache ghost (ICMP echo bouncing off a stale MAC entry
        # for 30-300s after a cable is pulled). Use nmap --top-ports 100
        # as an authoritative tiebreaker: if any port responds, the device's
        # TCP stack is alive (proof of life); if nothing responds, the ICMP
        # was almost certainly cached. The scanner agent owns the network
        # namespace and nmap privileges for this probe.
        tiebreaker_port = await _nmap_tiebreaker(ip)
        if tiebreaker_port is not None:
            return (True, f"tcp:{tiebreaker_port}")
        logger.info(
            "Probe for %s: ICMP responded but nmap top-100 found no open ports — treating as unreachable (likely stale ARP / ghost)",
            ip,
        )
        return (False, "icmp_only_untrusted")
    return (False, None)


async def _nmap_tiebreaker(ip: str) -> int | None:
    """Run a short nmap top-ports probe; return an open port number if any.

    Used when ICMP answers but our DEFAULT_CONNECTIVITY_PORTS list missed.
    Top-50 TCP services catch most real devices (printers on 9100, RDP on
    3389, obscure management UIs) while rejecting ARP-cache ghosts (their
    "host" has no real TCP stack to probe).

    Tuning rationale (worst-case per call):
      - `--top-ports 50`            — halved from 100; covers all smart-building
                                       categories without doubling dead-host cost
      - `--max-rate 400`            — cap so scans don't hammer fragile IoT
      - `--max-retries 1`           — fail fast; loss-sensitive caller
      - `--host-timeout 5s`         — ghost cap: dead host aborts in 5s, not 10s
      - outer `asyncio.wait_for 7s` — safety net if the scanner agent hangs
    Total: ~5s ceiling per ghost (was ~10-15s).

    Returns an int port number on success, None on failure/no open ports.
    """
    try:
        from app.services.parsers.nmap_parser import nmap_parser  # local import to avoid cycle
        result = await asyncio.wait_for(
            tools_client.nmap(
                ip,
                [
                    "-Pn",
                    "--top-ports", "50",
                    "--open",
                    "--max-rate", "400",
                    "--max-retries", "1",
                    "--host-timeout", "5s",
                    "-oX", "-",
                ],
                timeout=7,
            ),
            timeout=8.0,
        )
    except asyncio.TimeoutError:
        logger.debug("nmap tiebreaker for %s timed out", ip)
        return None
    except Exception as exc:
        logger.debug("nmap tiebreaker for %s failed: %s", ip, exc)
        return None

    try:
        parsed = nmap_parser.parse_xml(result.get("stdout", ""))
    except Exception as exc:
        logger.debug("nmap tiebreaker parse failed for %s: %s", ip, exc)
        return None

    for port_info in parsed.get("open_ports", []) or []:
        if isinstance(port_info, dict):
            port = port_info.get("port")
            if isinstance(port, int) and 1 <= port <= 65535:
                return port
    return None
