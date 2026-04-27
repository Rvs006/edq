"""Test Execution Engine — orchestrates all tests for a run.

Sequences automatic tool-based tests and creates pending stubs for manual tests.
Streams progress via WebSocket and integrates the Wobbly Cable Handler.
"""

import asyncio
import hashlib
import ipaddress
import json
import logging
import os
import re
import socket
import ssl
import time
from datetime import datetime, timezone
from typing import Any
from xml.etree import ElementTree

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import async_session
from app.models.test_run import (
    TestRun,
    TestRunStatus,
    TestRunVerdict,
    is_paused_test_run_status,
    normalize_test_run_status,
)
from app.models.test_result import TestResult, TestVerdict, TestTier
from app.models.device import Device
from app.models.test_template import TestTemplate
from app.models.protocol_whitelist import ProtocolWhitelist
from app.config import settings
from app.services.tools_client import describe_tools_error, tools_client
from app.services.parsers.nmap_parser import nmap_parser
from app.services.parsers.testssl_parser import testssl_parser
from app.services.parsers.ssh_audit_parser import ssh_audit_parser
from app.services.parsers.hydra_parser import hydra_parser
from app.services.evaluation import evaluate_result
from app.services.connectivity_probe import (
    extract_known_probe_ports,
    extract_probe_ports,
    probe_device_connectivity,
)
from app.services.mac_vendor import normalize_mac, resolve_mac_vendor
from app.services.run_readiness import (
    build_run_readiness_summary,
    merge_readiness_into_metadata,
)
from app.services.test_run_connectivity import ensure_device_execution_readiness
from app.services.wobbly_cable import WobblyCableHandler
from app.services.test_library import get_test_by_id
from app.services.device_fingerprinter import fingerprinter, FingerprintResult
from app.services.discovery_service import guess_manufacturer, guess_model
from app.services.protocol_observer import (
    observe_dhcp_activity,
    observe_dns_queries,
    observe_ntp_queries,
)
from app.services.scenario_routing import (
    get_manual_routing_note,
    get_scenario_routing_decision,
    normalize_connection_scenario,
)
from app.routes.websocket_routes import manager
from app.utils.datetime import utcnow_naive

logger = logging.getLogger("edq.test_engine")

# Generic web-server / HTTP-stack product names. These describe the device's
# HOSTING SOFTWARE, not the device itself — e.g. an EasyIO controller runs
# nginx, an Axis camera runs its own embedded webserver, etc. Never write
# these into `device.hostname` or `device.model`.
_GENERIC_SERVER_PRODUCTS = frozenset({
    "nginx", "apache", "apache httpd", "httpd", "lighttpd",
    "microsoft-iis", "iis", "openresty", "caddy", "gunicorn",
    "cloudflare", "cloudfront", "akamai", "varnish",
    "microsoft-httpapi", "microsoft httpapi",
    "werkzeug", "tornado", "twisted",
})

# Regex matching any generic server name at the start of a string, followed
# by a word boundary (space, slash, end-of-string, etc.). Prevents false
# matches like "nginxcontroller" while catching "nginx/1.24 (Ubuntu)".
_GENERIC_SERVER_PREFIX_RE = re.compile(
    r"^\s*(?:" + "|".join(re.escape(p) for p in _GENERIC_SERVER_PRODUCTS) + r")\b",
    re.IGNORECASE,
)


def _is_generic_server(product: str, version: str) -> bool:
    """True if product/version describes a generic web stack (nginx, apache, ...)."""
    if product and product.strip().lower() in _GENERIC_SERVER_PRODUCTS:
        return True
    if version and _GENERIC_SERVER_PREFIX_RE.match(version):
        return True
    return False

# Bounded caches — max 50 entries each; old entries are evicted automatically.
# Cleaned per-run in the finally block, but bounded to prevent leaks from crashes.
_MAX_CACHE_SIZE = 50


class _BoundedDict(dict):
    """Dict that evicts the oldest entry when it exceeds max_size.

    Thread-safety note: asyncio is single-threaded, so no lock is needed
    for __setitem__. Callers that perform composite read-modify-write
    operations across await points should use their own synchronisation.
    """
    def __init__(self, max_size: int = 20):
        super().__init__()
        self._max_size = max_size

    def __setitem__(self, key, value):
        if len(self) >= self._max_size and key not in self:
            oldest = next(iter(self))
            del self[oldest]
        super().__setitem__(key, value)


_PORT_SCAN_CACHE: dict[str, dict[str, Any]] = _BoundedDict(_MAX_CACHE_SIZE)
_TESTSSL_CACHE: dict[str, dict[str, Any]] = _BoundedDict(_MAX_CACHE_SIZE)

_DOCKER_TCP_BASELINE_PORTS = (
    22, 23, 53, 80, 135, 137, 139, 443, 445, 502, 554, 1883, 47808,
    8000, 8008, 8080, 8081, 8443, 8883, 9100,
)
_COMMON_SERVICE_BY_PORT = {
    22: "ssh",
    23: "telnet",
    53: "domain",
    80: "http",
    135: "msrpc",
    137: "netbios-ns",
    139: "netbios-ssn",
    443: "https",
    445: "microsoft-ds",
    502: "modbus",
    554: "rtsp",
    1883: "mqtt",
    47808: "bacnet",
    8000: "http-alt",
    8008: "http",
    8080: "http-proxy",
    8081: "http",
    8443: "https-alt",
    8883: "secure-mqtt",
    9100: "jetdirect",
}


def _port_evidence_score(port: dict[str, Any]) -> int:
    """Score how much service detail a parsed port entry carries."""
    score = 0
    service = str(port.get("service") or "").strip().lower()
    if service and service != "unknown":
        score += 2
    for field in ("version", "product", "extra_info"):
        if str(port.get(field) or "").strip():
            score += 3
    if port.get("scripts"):
        score += 4
    return score


def _merge_port_evidence(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Keep the richer port evidence while preserving non-empty existing fields."""
    primary, secondary = (
        (incoming, existing)
        if _port_evidence_score(incoming) > _port_evidence_score(existing)
        else (existing, incoming)
    )
    merged = dict(secondary)
    for key, value in primary.items():
        if value not in (None, "", [], {}):
            merged[key] = value
    return merged


def _merge_nmap_scan_data(*scans: dict[str, Any] | None) -> dict[str, Any]:
    """Merge parsed nmap results while preserving TCP/UDP protocol evidence."""
    merged: dict[str, Any] = {"hosts": [], "open_ports": [], "scan_info": {}}
    port_indexes: dict[tuple[str, int, str], int] = {}
    seen_hosts: set[tuple[str | None, str]] = set()

    for scan in scans:
        if not isinstance(scan, dict) or not scan:
            continue
        if scan.get("scan_info") and not merged.get("scan_info"):
            merged["scan_info"] = scan["scan_info"]
        for host in scan.get("hosts") or []:
            if not isinstance(host, dict):
                continue
            key = (host.get("ip"), host.get("status", ""))
            if key not in seen_hosts:
                seen_hosts.add(key)
                merged["hosts"].append(host)
        for port in scan.get("open_ports") or []:
            if not isinstance(port, dict) or port.get("port") is None:
                continue
            key = (
                str(port.get("protocol") or "tcp").lower(),
                int(port["port"]),
                str(port.get("state") or "open").lower(),
            )
            if key in port_indexes:
                idx = port_indexes[key]
                merged["open_ports"][idx] = _merge_port_evidence(merged["open_ports"][idx], port)
            else:
                port_indexes[key] = len(merged["open_ports"])
                merged["open_ports"].append(port)
    return merged


def _has_tcp_scan_evidence(scan_data: dict[str, Any] | None) -> bool:
    """True when scan data includes TCP/service evidence suitable for port skips."""
    if not isinstance(scan_data, dict) or not scan_data:
        return False
    scan_info = scan_data.get("scan_info") or {}
    protocol = str(scan_info.get("protocol") or "").lower()
    scan_type = str(scan_info.get("type") or "").lower()
    if protocol == "tcp" or scan_type in {"syn", "connect"}:
        return True
    return any(
        str(port.get("protocol") or "tcp").lower() == "tcp"
        for port in scan_data.get("open_ports") or []
        if isinstance(port, dict)
    )


def _filter_definite_open_ports(scan_data: dict[str, Any]) -> dict[str, Any]:
    """Return scan data with inconclusive open|filtered ports removed."""
    filtered = dict(scan_data)
    filtered["open_ports"] = [
        port for port in scan_data.get("open_ports", [])
        if isinstance(port, dict) and _is_definite_open_port(port)
    ]
    return filtered


def _is_definite_open_port(port: dict[str, Any], *, script_id: str | None = None) -> bool:
    """Treat UDP open|filtered as inconclusive unless script output proves service response."""
    state = str(port.get("state") or "").lower()
    if state == "open":
        return True
    if script_id and state == "open|filtered":
        return any(script.get("id") == script_id for script in port.get("scripts", []) or [])
    return False


def _is_http_service(port: dict[str, Any]) -> bool:
    service = str(port.get("service") or "").lower()
    port_num = int(port.get("port") or 0)
    return (
        "http" in service
        or "www" in service
        or port_num in {80, 443, 8000, 8008, 8080, 8081, 8443, 8888}
    )


def _is_https_service(port: dict[str, Any]) -> bool:
    service = str(port.get("service") or "").lower()
    port_num = int(port.get("port") or 0)
    return "https" in service or "ssl/http" in service or port_num in {443, 8443, 4443}


def _port_candidates_from_device(device: Device) -> list[int]:
    ports: list[int] = []
    seen: set[int] = set()

    def add_port(value: Any) -> None:
        try:
            port = int(value)
        except (TypeError, ValueError):
            return
        if 1 <= port <= 65535 and port not in seen:
            seen.add(port)
            ports.append(port)

    for item in getattr(device, "open_ports", None) or []:
        if isinstance(item, dict):
            add_port(item.get("port"))
        else:
            add_port(item)
    for port in _DOCKER_TCP_BASELINE_PORTS:
        add_port(port)
    return ports[:100]


def _tcp_probe_to_scan_data(
    device_ip: str,
    payload: dict[str, Any],
    probed_ports: list[int],
) -> dict[str, Any]:
    hosts = payload.get("hosts", []) if isinstance(payload, dict) else []
    host = hosts[0] if hosts and isinstance(hosts[0], dict) else {}
    open_ports = []
    for entry in host.get("open_ports", []) if isinstance(host, dict) else []:
        if not isinstance(entry, dict) or entry.get("port") is None:
            continue
        port = int(entry["port"])
        open_ports.append({
            "port": port,
            "protocol": "tcp",
            "state": "open",
            "service": entry.get("service") or _COMMON_SERVICE_BY_PORT.get(port, ""),
            "version": entry.get("version") or "",
            "product": entry.get("product") or "",
            "extra_info": entry.get("extra_info") or "",
            "scripts": entry.get("scripts") or [],
        })

    return {
        "hosts": [{
            "ip": host.get("ip") or device_ip,
            "status": "up" if host.get("reachable") or open_ports else "unknown",
            "ports": open_ports,
            "os": None,
            "hostname": None,
            "scripts": [],
        }],
        "open_ports": open_ports,
        "scan_info": {
            "type": "tcp-probe",
            "protocol": "tcp",
            "numservices": str(len(probed_ports)),
        },
        "scan_note": "Docker scanner fast TCP inventory; use host scanner mode for true all-65535 raw scans.",
    }


def _merge_tls_probe_fallback(parsed: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    merged = dict(parsed)
    for key, value in fallback.items():
        if key in {"tls_versions", "weak_versions", "ciphers", "weak_ciphers", "vulnerabilities"}:
            existing = list(merged.get(key) or [])
            for item in value or []:
                if item not in existing:
                    existing.append(item)
            merged[key] = existing
        elif value not in (None, "", [], {}) and not merged.get(key):
            merged[key] = value
    return merged


def _nmap_xml_or_raise(test_id: str, raw: dict[str, Any]) -> str:
    """Return nmap XML stdout, or raise so scanner failures cannot look like closed ports."""
    if not isinstance(raw, dict):
        raise RuntimeError(f"{test_id} nmap failed: invalid sidecar response")

    if raw.get("error"):
        raise RuntimeError(f"{test_id} nmap failed: {raw['error']}")

    stdout = raw.get("stdout") or ""
    exit_code = raw.get("exit_code")
    if exit_code not in (None, 0):
        if "<nmaprun" in stdout and "</nmaprun>" in stdout:
            try:
                ElementTree.fromstring(stdout)
            except ElementTree.ParseError as exc:
                raise RuntimeError(f"{test_id} nmap returned invalid XML: {exc}") from exc
            logger.warning(
                "%s nmap exited %s but returned parseable XML; preserving scan evidence",
                test_id,
                exit_code,
            )
            return stdout
        details = (raw.get("stderr") or raw.get("stdout") or "").strip()
        suffix = f": {details[:500]}" if details else ""
        raise RuntimeError(f"{test_id} nmap exited {exit_code}{suffix}")

    if not stdout.strip():
        raise RuntimeError(f"{test_id} nmap returned no XML output")
    try:
        ElementTree.fromstring(stdout)
    except ElementTree.ParseError as exc:
        raise RuntimeError(f"{test_id} nmap returned invalid XML: {exc}") from exc
    return stdout


def _udp_inconclusive_result(ports: list[int], reason: str) -> dict[str, Any]:
    return {
        "hosts": [],
        "open_ports": [
            {
                "port": port,
                "protocol": "udp",
                "state": "open|filtered",
                "service": _COMMON_SERVICE_BY_PORT.get(port, ""),
            }
            for port in ports
        ],
        "scan_info": {"type": "udp-probe", "protocol": "udp"},
        "scan_error": reason,
    }


def _has_nmap_scan_evidence(scan_data: dict[str, Any] | None) -> bool:
    """True when parsed nmap data came from a real scan, even if no ports were open."""
    if not isinstance(scan_data, dict) or not scan_data:
        return False
    return bool(
        scan_data.get("open_ports")
        or scan_data.get("hosts")
        or scan_data.get("scan_info")
    )


def _infer_os_from_services(open_ports: list[dict[str, Any]]) -> str | None:
    """Infer OS from service banners when nmap -O fails."""
    from collections import Counter
    os_hints: list[str] = []
    for p in open_ports:
        version = (p.get("version", "") or "").lower()
        service = (p.get("service", "") or "").lower()
        product = (p.get("product", "") or "").lower()
        combined = f"{service} {version} {product}"
        if any(kw in combined for kw in ("dropbear", "busybox", "samba", "uhttpd")):
            os_hints.append("Embedded Linux/Unix")
        elif any(kw in combined for kw in ("windows", "iis", "msrpc")):
            os_hints.append("Windows")
        elif any(kw in combined for kw in ("ubuntu", "debian", "centos", "fedora", "red hat")):
            os_hints.append("Linux")
        elif "openssh" in combined and "windows" not in combined:
            os_hints.append("Linux/Unix")
        elif "microsoft" in combined and "microsoft-ds" not in combined:
            os_hints.append("Windows")
        elif "cisco" in combined:
            os_hints.append("Cisco IOS")
        elif "apple" in combined or "macos" in combined:
            os_hints.append("macOS")
    if not os_hints:
        return None
    most_common = Counter(os_hints).most_common(1)[0][0]
    return f"{most_common} (inferred from service banners)"


class TestEngine:
    """Orchestrates the full test execution lifecycle for a test run."""

    @staticmethod
    def _progress_for(total: int, completed: int) -> float:
        if total <= 0:
            return 0.0
        return round((completed / total) * 100, 1)

    async def _persist_run_progress(
        self,
        run_id: str,
        *,
        completed_tests: int,
        total_tests: int,
        status: TestRunStatus | None = None,
        run_metadata: dict[str, Any] | None = None,
        started_at: datetime | None = None,
        current_test_id: str | None = None,
        current_test_name: str | None = None,
        current_test_started_at: datetime | None = None,
        clear_current_test: bool = False,
    ) -> None:
        async with async_session() as db:
            run_row = await db.get(TestRun, run_id)
            if not run_row:
                return
            run_row.completed_tests = completed_tests
            run_row.progress_pct = self._progress_for(total_tests, completed_tests)
            if status is not None:
                run_row.status = status
            if started_at is not None and not run_row.started_at:
                run_row.started_at = started_at
            if (
                run_metadata is not None
                or current_test_id is not None
                or clear_current_test
            ):
                existing_metadata = (
                    run_row.run_metadata if isinstance(run_row.run_metadata, dict) else {}
                )
                metadata = dict(run_metadata) if isinstance(run_metadata, dict) else dict(existing_metadata)
                if clear_current_test:
                    metadata.pop("current_test", None)
                if current_test_id is not None:
                    metadata["current_test"] = {
                        "test_id": current_test_id,
                        "test_name": current_test_name or current_test_id,
                        "status": "running",
                        "started_at": (
                            current_test_started_at or utcnow_naive()
                        ).isoformat(),
                    }
                run_row.run_metadata = metadata
            await db.commit()

    async def run(self, test_run_id: str, test_plan_id: str | None = None) -> None:
        """Execute all tests for a test run, streaming progress via WebSocket.

        Runs as a background asyncio task. Creates its own DB sessions.
        If test_plan_id is provided, filters/overrides tests per the plan.
        """
        logger.info("Starting test engine for run %s", test_run_id)

        plan_configs: dict[str, dict] = {}
        if test_plan_id:
            from app.models.test_plan import TestPlan
            async with async_session() as db:
                plan_result = await db.execute(select(TestPlan).where(TestPlan.id == test_plan_id))
                plan = plan_result.scalar_one_or_none()
                if plan and plan.test_configs:
                    for cfg in plan.test_configs:
                        plan_configs[cfg["test_id"]] = cfg

        tool_versions: dict[str, str] = {}
        try:
            ver_result = await tools_client.versions()
            tool_versions = ver_result.get("versions", {})
        except Exception as e:
            logger.debug("Could not fetch tool versions: %s", e)

        readiness = None
        async with async_session() as db:
            run = await self._load_run(db, test_run_id)
            if run is None:
                logger.error("Test run %s not found", test_run_id)
                return

            device = await self._load_device(db, run.device_id)
            if device is None:
                logger.error("Device %s not found for run %s", run.device_id, test_run_id)
                await self._set_run_error(db, run, "Device not found")
                return

            readiness = await ensure_device_execution_readiness(db, device, logger=logger)
            if readiness.missing_ip:
                logger.error(
                    "Device %s has no IP address (DHCP device awaiting assignment) — cannot run tests",
                    device.id,
                )
                await self._set_run_error(
                    db, run,
                    "Device has no IP address. Discover the IP first for DHCP devices.",
                )
                return

            template = await self._load_template(db, run.template_id)
            if template is None:
                logger.error("Template %s not found for run %s", run.template_id, test_run_id)
                await self._set_run_error(db, run, "Template not found")
                return

            whitelist_entries = await self._load_whitelist(db, template.whitelist_id)

            existing_meta = dict(run.run_metadata) if isinstance(run.run_metadata, dict) else {}
            existing_meta["tool_versions"] = tool_versions
            existing_meta.pop("current_test", None)
            run.run_metadata = existing_meta
            await db.commit()

            # Eagerly load all device attributes then detach so they remain
            # accessible after this session closes without triggering lazy-load
            # errors (DetachedInstanceError).
            await db.refresh(device)
            db.expunge(device)

        probe_ports = readiness.probe_ports
        cable_handler = WobblyCableHandler(
            device.ip_address,
            test_run_id,
            manager,
            probe_ports=probe_ports,
            known_service_ports=getattr(readiness, "known_probe_ports", None) or [],
        )
        # Apply the shared route/engine readiness decision before starting tests.
        # connection. ICMP alone isn't sufficient — a gateway/router on the
        # user's network may respond to ping at the target IP without actually
        # being the device under test. Tests need real services to exercise.
        # For devices with no known open ports (manually added, never scanned),
        # accept ICMP as sufficient to start — the test engine will discover
        # actual ports during execution.
        cable_task = asyncio.create_task(cable_handler.monitor())
        run_started_broadcasted = False

        if readiness.can_execute:
            async with async_session() as db:
                run = await db.get(TestRun, test_run_id)
                if run:
                    run.status = TestRunStatus.RUNNING
                    if not run.started_at:
                        run.started_at = utcnow_naive()
                    await db.commit()

            await manager.broadcast(f"test-run:{test_run_id}", {
                "type": "run_started",
                "data": {"run_id": test_run_id, "status": "running"},
            })
            run_started_broadcasted = True
        else:
            if readiness.reason == "service_unreachable":
                logger.warning(
                    "Device %s responded to %s but has no open probeable service ports for run %s; pausing until it becomes testable",
                    device.ip_address,
                    readiness.probe_method or "ping",
                    test_run_id,
                )
            else:
                logger.warning(
                    "Device %s is unreachable for run %s; pausing until connectivity returns",
                    device.ip_address,
                    test_run_id,
                )
            await cable_handler.pause_for_disconnect(
                message=readiness.pause_message or (
                    f"Target device {device.ip_address} is unreachable from this "
                    "network. Testing is paused until connectivity is restored."
                ),
                kill_tools=False,
                reason="service" if readiness.reason == "service_unreachable" else "cable",
            )

        try:
            run_cache_key = test_run_id
            _PORT_SCAN_CACHE.pop(run_cache_key, None)
            _TESTSSL_CACHE.pop(run_cache_key, None)

            async with async_session() as db:
                results_q = await db.execute(
                    select(TestResult)
                    .where(TestResult.test_run_id == test_run_id)
                    .order_by(TestResult.test_id)
                )
                test_results = list(results_q.scalars().all())

            total = len(test_results)
            completed = 0

            # Discovery test IDs — these run first, before fingerprinting
            DISCOVERY_TESTS = {"U01", "U02", "U03", "U04", "U05", "U06", "U07", "U08"}
            skip_test_ids: set[str] = set()
            skip_reasons: dict[str, str] = {}

            # Scenario routing still affects manual-vs-automatic handling below.
            connection_scenario = normalize_connection_scenario(
                getattr(run, "connection_scenario", "direct")
            )
            fingerprint_done = False
            fingerprint_result: FingerprintResult | None = None

            for i, test_result in enumerate(test_results):
                test_def = get_test_by_id(test_result.test_id)
                if test_def is None:
                    continue

                if plan_configs:
                    cfg = plan_configs.get(test_result.test_id)
                    if cfg is not None and not cfg.get("enabled", True):
                        continue

                # --- Fingerprint phase: runs once after U08 completes ---
                if not fingerprint_done and test_result.test_id not in DISCOVERY_TESTS:
                    fingerprint_done = True
                    fingerprint_result = await self._run_fingerprint_phase(
                        test_run_id, device
                    )
                    if fingerprint_result:
                        skip_test_ids.update(fingerprint_result.skip_test_ids)
                        skip_reasons.update(fingerprint_result.skip_reasons)
                        logger.info(
                            "Fingerprint phase complete for run %s: category=%s, skipping %s",
                            test_run_id, fingerprint_result.category, skip_test_ids,
                        )

                # --- Skip tests flagged by fingerprinter ---
                if test_result.test_id in skip_test_ids:
                    reason = skip_reasons.get(
                        test_result.test_id,
                        "Skipped — required service not detected on this device.",
                    )
                    async with async_session() as db:
                        result_row = await db.get(TestResult, test_result.id)
                        if result_row:
                            result_row.verdict = TestVerdict.NA
                            result_row.comment = reason
                            result_row.completed_at = utcnow_naive()
                            await db.commit()

                    completed += 1
                    await manager.broadcast(f"test-run:{test_run_id}", {
                        "type": "test_complete",
                        "data": {
                            "test_id": test_result.test_id,
                            "test_name": test_result.test_name,
                            "status": "completed",
                            "verdict": "na",
                            "comment": reason,
                            "progress_pct": round(((i + 1) / total) * 100, 1) if total else 0,
                        },
                    })

                    await self._persist_run_progress(
                        test_run_id,
                        completed_tests=completed,
                        total_tests=total,
                    )
                    continue

                await self._wait_while_paused(test_run_id)

                if not run_started_broadcasted:
                    run_started_broadcasted = True
                    await manager.broadcast(f"test-run:{test_run_id}", {
                        "type": "run_started",
                        "data": {"run_id": test_run_id, "status": "running"},
                    })

                effective_tier = test_def["tier"]
                if plan_configs:
                    cfg = plan_configs.get(test_result.test_id)
                    if cfg and cfg.get("tier_override"):
                        effective_tier = cfg["tier_override"]
                else:
                    effective_tier = get_scenario_routing_decision(
                        test_result.test_id,
                        effective_tier,
                        connection_scenario,
                    ).tier

                if effective_tier == "guided_manual":
                    async with async_session() as db:
                        result_row = await db.get(TestResult, test_result.id)
                        if result_row and result_row.verdict == TestVerdict.PENDING:
                            result_row.comment = (
                                get_manual_routing_note(test_result.test_id, connection_scenario)
                                or "Awaiting engineer input"
                            )
                            await db.commit()

                    await self._persist_run_progress(
                        test_run_id,
                        completed_tests=completed,
                        total_tests=total,
                    )

                    await manager.broadcast(f"test-run:{test_run_id}", {
                        "type": "test_complete",
                        "data": {
                            "test_id": test_result.test_id,
                            "test_name": test_result.test_name,
                            "status": TestRunStatus.AWAITING_MANUAL.value,
                            "verdict": "pending",
                            "tier": "guided_manual",
                            "progress_pct": self._progress_for(total, completed),
                        },
                    })
                    continue

                while True:
                    await self._wait_while_paused(test_run_id)
                    current_device_ip = cable_handler.ip
                    probe_ports = cable_handler.probe_ports

                    # Pre-test connectivity check: verify device is reachable
                    # before starting the test. This catches cable disconnects
                    # that happened between the monitor's poll interval.
                    pre_reachable, _ = await probe_device_connectivity(
                        current_device_ip,
                        probe_ports=probe_ports,
                        tcp_timeout=2.0,
                        trust_icmp_only=True,
                    )
                    if not pre_reachable:
                        logger.warning(
                            "Pre-test probe failed for %s before %s — waiting for cable handler",
                            current_device_ip,
                            test_result.test_id,
                        )
                        # Give the cable handler time to detect and pause
                        await asyncio.sleep(4)
                        if await self._is_run_paused_for_cable(test_run_id):
                            await self._wait_while_paused(test_run_id)
                            continue  # retry from top after cable resumes

                    test_started_at = utcnow_naive()
                    await self._persist_run_progress(
                        test_run_id,
                        completed_tests=completed,
                        total_tests=total,
                        status=TestRunStatus.RUNNING,
                        current_test_id=test_result.test_id,
                        current_test_name=test_result.test_name,
                        current_test_started_at=test_started_at,
                    )

                    await manager.broadcast(f"test-run:{test_run_id}", {
                        "type": "test_start",
                        "data": {
                            "test_id": test_result.test_id,
                            "test_name": test_result.test_name,
                            "status": "running",
                            "progress_pct": self._progress_for(total, completed),
                        },
                    })

                    verdict, comment, parsed, raw_out, duration = await self._run_single_test(
                        test_def,
                        current_device_ip,
                        test_run_id,
                        whitelist_entries,
                        device,
                        connection_scenario,
                    )

                    if not await self._is_run_paused_for_cable(test_run_id):
                        break

                    logger.info(
                        "Retrying test %s for run %s after cable reconnection",
                        test_result.test_id,
                        test_run_id,
                    )

                async with async_session() as db:
                    result_row = await db.get(TestResult, test_result.id)
                    if result_row:
                        try:
                            result_row.verdict = TestVerdict(verdict)
                        except ValueError:
                            result_row.verdict = TestVerdict.PENDING
                        result_row.comment = comment
                        result_row.parsed_data = parsed
                        result_row.raw_output = raw_out[:50000] if raw_out else None
                        result_row.duration_seconds = duration
                        result_row.started_at = test_started_at
                        result_row.completed_at = utcnow_naive()

                        # Auto-populate Device fields from test results as they complete
                        if parsed:
                            await self._enrich_device_from_result(
                                db, device.id, test_result.test_id, parsed, raw_out
                            )

                        await db.commit()

                completed += 1

                await manager.broadcast(f"test-run:{test_run_id}", {
                    "type": "test_complete",
                    "data": {
                        "test_id": test_result.test_id,
                        "test_name": test_result.test_name,
                        "status": "completed",
                        "verdict": verdict,
                        "comment": comment,
                        "progress_pct": self._progress_for(total, completed),
                    },
                })

                await self._persist_run_progress(
                    test_run_id,
                    completed_tests=completed,
                    total_tests=total,
                    status=TestRunStatus.RUNNING,
                    clear_current_test=True,
                )

        except asyncio.CancelledError:
            logger.info("Test engine cancelled for run %s", test_run_id)
            async with async_session() as db:
                run_row = await db.get(TestRun, test_run_id)
                if run_row:
                    run_row.status = TestRunStatus.CANCELLED
                    await db.commit()
            return
        except Exception as exc:
            logger.exception("Test engine error for run %s: %s", test_run_id, exc)
            async with async_session() as db:
                try:
                    await self._set_run_error(db, await db.get(TestRun, test_run_id), str(exc))
                except Exception as inner_exc:
                    logger.error("Failed to mark run %s as error: %s", test_run_id, inner_exc)
            return
        finally:
            cable_handler.stop()
            cable_task.cancel()
            try:
                await cable_task
            except asyncio.CancelledError:
                pass
            _PORT_SCAN_CACHE.pop(test_run_id, None)
            _PORT_SCAN_CACHE.pop(f"{test_run_id}_u08", None)
            _TESTSSL_CACHE.pop(test_run_id, None)

        await self._finalize_run(test_run_id)

    async def _enrich_device_from_result(
        self,
        db: "AsyncSession",
        device_id: str,
        test_id: str,
        parsed: dict,
        raw_out: str | None = None,
    ) -> None:
        """Auto-populate Device fields from parsed test data as each test completes."""
        device_row = await db.get(Device, device_id)
        if not device_row:
            return

        changed = False

        if test_id == "U01":
            # Ping — can extract hostname from reverse DNS
            for h in parsed.get("hosts", []):
                hostname = h.get("hostname") or h.get("name")
                if hostname and not device_row.hostname:
                    device_row.hostname = hostname
                    changed = True

        elif test_id == "U02":
            # MAC/Vendor lookup
            if parsed.get("mac_address") and not device_row.mac_address:
                device_row.mac_address = parsed["mac_address"]
                changed = True
            if parsed.get("oui_vendor") and not device_row.oui_vendor:
                device_row.oui_vendor = parsed["oui_vendor"]
                changed = True
            # Use OUI vendor as manufacturer if not set
            if parsed.get("oui_vendor") and not device_row.manufacturer:
                device_row.manufacturer = parsed["oui_vendor"]
                changed = True

        elif test_id == "U06":
            # TCP port scan — store open ports
            if parsed.get("open_ports") and not device_row.open_ports:
                device_row.open_ports = parsed["open_ports"]
                changed = True

        elif test_id == "U08":
            # Service version detection — extract model/firmware from banners
            ports = parsed.get("open_ports", [])
            guessed_manufacturer = guess_manufacturer(device_row.oui_vendor, ports)
            guessed_model = guess_model(ports, device_row.os_fingerprint)

            if guessed_manufacturer and not device_row.manufacturer:
                device_row.manufacturer = guessed_manufacturer
                changed = True

            if guessed_model and not device_row.model:
                device_row.model = guessed_model
                changed = True

            for p in ports:
                service = (p.get("service") or "").lower()
                version = (p.get("version") or "").strip()
                product = (p.get("product") or "").strip()

                is_generic_server = _is_generic_server(product, version)

                # Use HTTP server header as model hint (but never a generic
                # server like nginx/apache — that's a hosting stack, not a
                # device model)
                if (
                    service in ("http", "https")
                    and version
                    and not device_row.model
                    and not guessed_model
                    and not is_generic_server
                ):
                    device_row.model = version
                    changed = True

                # Extract firmware from version strings (e.g. "EasyIO FW-14 v2.3")
                if version and not device_row.firmware_version:
                    fw_match = re.search(r'[Vv]?(\d+\.\d+[\.\d]*)', version)
                    if fw_match:
                        device_row.firmware_version = fw_match.group(0)
                        changed = True

                # NOTE: we no longer copy `product` into `device.hostname`.
                # The previous behavior was writing "nginx" / "apache" /
                # "Microsoft-HTTPAPI" into hostname, which then got shown as
                # the device's display name. Hostname must come from nmap's
                # <hostname> element or reverse-DNS — not from an HTTP
                # Server: header.

            # Update open_ports with service info if we have richer data
            if ports:
                device_row.open_ports = ports
                changed = True

        elif test_id == "U19":
            # OS fingerprinting
            if parsed.get("os_fingerprint") and not device_row.os_fingerprint:
                device_row.os_fingerprint = parsed["os_fingerprint"]
                changed = True

        elif test_id == "U15":
            # SSH version — can reveal device info
            ssh_ver = parsed.get("ssh_version", "")
            if ssh_ver and not device_row.firmware_version:
                device_row.firmware_version = ssh_ver
                changed = True

        elif test_id == "U36":
            # Banner grabbing — look for model/version info in banners.
            # Skip generic web-server / proxy products (nginx, apache, etc.)
            # — they describe the hosting stack, not the device.
            for p in parsed.get("open_ports", []):
                version = (p.get("version") or "").strip()
                product = (p.get("product") or "").strip()

                if (
                    version
                    and not device_row.model
                    and not _is_generic_server(product, version)
                ):
                    device_row.model = version
                    changed = True
                    break

        if changed:
            await db.flush()
            logger.info("Device %s enriched from %s", device_id[:8], test_id)

    async def _run_single_test(
        self,
        test_def: dict,
        device_ip: str,
        run_id: str,
        whitelist_entries: list[dict],
        device: Device,
        connection_scenario: str,
    ) -> tuple[str, str, dict | None, str | None, float | None]:
        """Execute a single automatic test. Returns (verdict, comment, parsed, raw_output, duration)."""
        test_id = test_def["test_id"]
        start = time.monotonic()

        try:
            parsed, raw_out = await self._dispatch_test(
                test_id,
                device_ip,
                run_id,
                device,
                connection_scenario,
            )
            verdict, comment = evaluate_result(test_id, parsed, whitelist_entries)
        except Exception as exc:
            logger.warning("Test %s failed for run %s: %s", test_id, run_id, exc)
            elapsed = time.monotonic() - start
            return (
                "error",
                describe_tools_error(exc, fallback=f"{test_id} execution failed"),
                None,
                None,
                round(elapsed, 2),
            )

        elapsed = time.monotonic() - start
        return (verdict, comment, parsed, raw_out, round(elapsed, 2))

    async def _run_fingerprint_phase(
        self,
        test_run_id: str,
        device: Device,
    ) -> FingerprintResult | None:
        """Run device fingerprinting after discovery tests complete.

        Collects U02 + U08 cached results, runs the fingerprinter, stores
        the result in run metadata, and broadcasts a device_classified event.
        """
        try:
            # Prefer U08 service detection for fingerprinting, but fall back to
            # U06's port scan if service detection failed. Missing scan data
            # must not be interpreted as "all ports are closed".
            u08_data = _PORT_SCAN_CACHE.get(f"{test_run_id}_u08", {})
            u06_data = _PORT_SCAN_CACHE.get(test_run_id, {})
            u07_data = _PORT_SCAN_CACHE.get(f"{test_run_id}_u07", {})
            if _has_nmap_scan_evidence(u08_data):
                scan_data = _merge_nmap_scan_data(u08_data, u07_data)
                scan_source = "U08+U07" if _has_nmap_scan_evidence(u07_data) else "U08"
            elif _has_nmap_scan_evidence(u06_data):
                scan_data = _merge_nmap_scan_data(u06_data, u07_data)
                scan_source = "U06+U07" if _has_nmap_scan_evidence(u07_data) else "U06"
            elif _has_nmap_scan_evidence(u07_data):
                scan_data = u07_data
                scan_source = "U07"
            else:
                scan_data = {}
                scan_source = "none"
            allow_port_skips = _has_tcp_scan_evidence(scan_data)

            # Gather U02 data from the device record (already parsed)
            u02_data = {
                "oui_vendor": device.oui_vendor or "",
                "mac_address": device.mac_address or "",
            }

            async with async_session() as db:
                result = await fingerprinter.fingerprint(
                    db,
                    device.id,
                    scan_data,
                    u02_data,
                    allow_port_skips=allow_port_skips,
                )

                # Store fingerprint in run metadata
                run_row = await db.get(TestRun, test_run_id)
                if run_row:
                    meta = run_row.run_metadata or {}
                    meta["fingerprint"] = {
                        "category": result.category,
                        "confidence": result.confidence,
                        "vendor": result.vendor,
                        "matched_profile_id": result.matched_profile_id,
                        "matched_profile_name": result.matched_profile_name,
                        "skip_test_ids": result.skip_test_ids,
                        "reason": result.reason,
                        "port_scan_source": scan_source,
                    }
                    run_row.run_metadata = meta
                    await db.commit()

            # Broadcast classification event so the UI updates
            await manager.broadcast(f"test-run:{test_run_id}", {
                "type": "device_classified",
                "data": {
                    "category": result.category,
                    "confidence": result.confidence,
                    "vendor": result.vendor,
                    "matched_profile_name": result.matched_profile_name,
                    "skip_test_ids": result.skip_test_ids,
                },
            })

            return result

        except Exception as exc:
            logger.warning("Fingerprint phase failed for run %s: %s", test_run_id, exc)
            return None

    def _stdout_callback(self, run_id: str, test_id: str):
        """Create an async callback that broadcasts stdout lines via WebSocket."""
        async def on_line(line: str):
            await manager.broadcast(f"test-run:{run_id}", {
                "type": "stdout_line",
                "data": {"test_id": test_id, "stdout_line": line},
            })
        return on_line

    async def _docker_tcp_inventory(
        self,
        device_ip: str,
        device: Device,
    ) -> tuple[dict[str, Any], str]:
        """Fast TCP inventory for Docker Desktop/bridge scanner deployments.

        Docker connect scans across the WSL/bridge boundary can time out on
        `-p-` before reaching useful ports. This verifies known/common service
        ports quickly so U06 produces actionable values instead of a false
        empty result.
        """
        ports = _port_candidates_from_device(device)
        payload = await tools_client.tcp_probe(
            device_ip,
            ports=ports,
            connect_timeout=1.0,
            concurrency=min(len(ports), 64),
            max_hosts=1,
            timeout=30,
        )
        parsed = _tcp_probe_to_scan_data(device_ip, payload, ports)
        return parsed, json.dumps(payload, sort_keys=True)

    def _tls_probe_sync(self, host: str, port: int) -> dict[str, Any]:
        result: dict[str, Any] = {
            "tls_versions": [],
            "weak_versions": [],
            "ciphers": [],
            "weak_ciphers": [],
            "vulnerabilities": [],
            "cert_valid": False,
            "cert_not_before": None,
            "cert_not_after": None,
            "cert_expiry": None,
            "cert_subject": None,
            "cert_issuer": None,
            "hsts": None,
            "hsts_checked": False,
            "fallback_probe": "python-ssl",
            "target_port": port,
        }
        cert_der: bytes | None = None
        version_map = [
            ("TLSv1.0", getattr(ssl.TLSVersion, "TLSv1", None)),
            ("TLSv1.1", getattr(ssl.TLSVersion, "TLSv1_1", None)),
            ("TLSv1.2", getattr(ssl.TLSVersion, "TLSv1_2", None)),
            ("TLSv1.3", getattr(ssl.TLSVersion, "TLSv1_3", None)),
        ]
        for label, version in version_map:
            if version is None:
                continue
            try:
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                context.minimum_version = version
                context.maximum_version = version
                with socket.create_connection((host, port), timeout=4) as sock:
                    with context.wrap_socket(sock, server_hostname=host) as tls_sock:
                        negotiated = tls_sock.version() or label
                        if label not in result["tls_versions"]:
                            result["tls_versions"].append(label)
                        cipher = tls_sock.cipher()
                        if cipher:
                            name, protocol, bits = cipher
                            cipher_entry = {"name": name, "protocol": protocol, "bits": bits}
                            if cipher_entry not in result["ciphers"]:
                                result["ciphers"].append(cipher_entry)
                        if cert_der is None:
                            cert_der = tls_sock.getpeercert(binary_form=True)
            except Exception:
                continue

        result["weak_versions"] = [
            version for version in result["tls_versions"]
            if version in {"SSLv2", "SSLv3", "TLSv1.0", "TLSv1.1"}
        ]
        if cert_der:
            try:
                from cryptography import x509

                cert = x509.load_der_x509_certificate(cert_der)
                result["cert_subject"] = cert.subject.rfc4514_string()
                result["cert_issuer"] = cert.issuer.rfc4514_string()
                try:
                    not_before = cert.not_valid_before_utc
                    not_after = cert.not_valid_after_utc
                except AttributeError:
                    not_before = cert.not_valid_before
                    not_after = cert.not_valid_after
                result["cert_not_before"] = not_before.isoformat()
                result["cert_not_after"] = not_after.isoformat()
                result["cert_expiry"] = result["cert_not_after"]
                now = datetime.now(timezone.utc)
                if not_before.tzinfo is None:
                    not_before = not_before.replace(tzinfo=timezone.utc)
                if not_after.tzinfo is None:
                    not_after = not_after.replace(tzinfo=timezone.utc)
                result["cert_valid"] = not_before <= now <= not_after and cert.issuer != cert.subject
            except Exception as exc:
                logger.debug("TLS certificate fallback parse failed for %s:%s: %s", host, port, exc)
        return result

    async def _tls_probe_fallback(self, host: str, port: int) -> dict[str, Any]:
        return await asyncio.to_thread(self._tls_probe_sync, host, port)

    async def _dispatch_test(
        self,
        test_id: str,
        device_ip: str,
        run_id: str,
        device: Device,
        connection_scenario: str,
    ) -> tuple[dict[str, Any], str | None]:
        """Dispatch a test to the appropriate tool and parser.

        Returns (parsed_data, raw_stdout).
        Uses streaming tool calls to broadcast live stdout via WebSocket.
        """
        on_line = self._stdout_callback(run_id, test_id)

        if test_id == "U01":
            raw = await tools_client.ping(device_ip)
            parsed = nmap_parser.parse_ping(raw)
            return (parsed, raw.get("stdout"))

        if test_id == "U02":
            raw = await tools_client.nmap_stream(device_ip, ["-sn", "-oX", "-"], timeout=60, on_line=on_line)
            parsed = nmap_parser.parse_xml(raw.get("stdout", ""))
            # Fallback 1: if nmap couldn't see the MAC (Docker network hop), try with --send-ip
            if not parsed.get("mac_address"):
                try:
                    arp_raw = await tools_client._post(
                        "/scan/nmap",
                        {"target": device_ip, "args": ["-sn", "--send-ip", "-oX", "-"], "timeout": 30},
                        timeout=40,
                    )
                    arp_parsed = nmap_parser.parse_xml(arp_raw.get("stdout", ""))
                    if arp_parsed.get("mac_address"):
                        parsed["mac_address"] = arp_parsed["mac_address"]
                        parsed["oui_vendor"] = arp_parsed.get("oui_vendor", "")
                except Exception:
                    logger.debug("U02: ARP fallback 1 failed for %s", device_ip)
            # Fallback 2: ping then read ARP table (works when on same L2 segment)
            if not parsed.get("mac_address"):
                try:
                    arp_raw = await tools_client._post(
                        "/scan/nmap",
                        {"target": device_ip, "args": ["-sn", "-PR", "-oX", "-"], "timeout": 30},
                        timeout=40,
                    )
                    arp_parsed = nmap_parser.parse_xml(arp_raw.get("stdout", ""))
                    if arp_parsed.get("mac_address"):
                        parsed["mac_address"] = arp_parsed["mac_address"]
                        parsed["oui_vendor"] = arp_parsed.get("oui_vendor", "")
                except Exception:
                    logger.debug("U02: ARP fallback 2 failed for %s", device_ip)
            # Fallback 3: ping to populate ARP cache, then read it via ip neigh
            if not parsed.get("mac_address"):
                try:
                    await tools_client.ping(device_ip, count=1)
                    arp_result = await tools_client.arp_cache(device_ip)
                    for entry in arp_result.get("entries", []) if isinstance(arp_result, dict) else []:
                        if not isinstance(entry, dict):
                            continue
                        if str(entry.get("ip") or "") == device_ip and entry.get("mac"):
                            parsed["mac_address"] = entry["mac"]
                            if entry.get("vendor"):
                                parsed["oui_vendor"] = entry["vendor"]
                            break
                    arp_data = nmap_parser.parse_arp_cache(arp_result.get("stdout", ""))
                    if not parsed.get("mac_address") and arp_data.get("mac_address"):
                        parsed["mac_address"] = arp_data["mac_address"]
                except Exception:
                    logger.debug("U02: ARP cache fallback failed for %s", device_ip)
            device_mac = normalize_mac(getattr(device, "mac_address", None))
            if not parsed.get("mac_address") and device_mac:
                parsed["mac_address"] = device_mac
                if getattr(device, "oui_vendor", None):
                    parsed["oui_vendor"] = device.oui_vendor
                parsed["source"] = "device_record"
            vendor_hint = (
                parsed.get("oui_vendor")
                or getattr(device, "oui_vendor", None)
                or getattr(device, "manufacturer", None)
            )
            vendor = await resolve_mac_vendor(parsed.get("mac_address"), vendor_hint)
            if vendor:
                parsed["oui_vendor"] = vendor
            return (parsed, raw.get("stdout"))

        if test_id == "U03":
            return ({"ethtool_available": False}, None)

        if test_id == "U04":
            if (
                connection_scenario == "direct"
                and settings.PROTOCOL_OBSERVER_ENABLED
            ):
                mac = getattr(device, "mac_address", None)
                if not mac and getattr(device, "id", None):
                    async with async_session() as db:
                        fresh_device = await db.get(Device, device.id)
                        mac = getattr(fresh_device, "mac_address", None) if fresh_device else None
                stripped_mac = mac.strip() if mac else ""
                if stripped_mac:
                    try:
                        observed = await observe_dhcp_activity(expected_mac=stripped_mac)
                        if observed.get("observed"):
                            return (
                                {
                                    "dhcp_observed": True,
                                    "dhcp_lease_acknowledged": observed.get("lease_acknowledged", False),
                                    "dhcp_events": observed.get("events", []),
                                    "offer_capable": observed.get("offer_capable", False),
                                    "offered_ip": observed.get("offered_ip"),
                                    "dhcp_server": observed.get("server_identifier"),
                                },
                                None,
                            )
                    except Exception as exc:
                        logger.debug("U04 DHCP observer unavailable for %s: %s", device_ip, exc)
            try:
                raw = await tools_client.nmap_stream(
                    device_ip, ["-sU", "-p", "67", "--script", "dhcp-discover", "-oX", "-"],
                    timeout=30, on_line=on_line
                )
                xml_out = _nmap_xml_or_raise("U04", raw)
                parsed = nmap_parser.parse_dhcp_discover(xml_out)
                return (parsed, xml_out)
            except Exception as exc:
                logger.debug("U04: DHCP discover failed for %s", device_ip)
                return (
                    {
                        "dhcp_detected": None,
                        "error": describe_tools_error(exc, fallback="DHCP discovery failed"),
                    },
                    None,
                )

        if test_id == "U05":
            try:
                target_ip = ipaddress.ip_address(device_ip)
            except ValueError:
                target_ip = None
            if target_ip and target_ip.version == 4:
                return (
                    {
                        "ipv6_supported": False,
                        "ipv6_assessed": False,
                        "reason": "No IPv6 address is recorded for this device; the current test run target is IPv4.",
                    },
                    None,
                )
            raw = await tools_client.nmap_stream(device_ip, ["-6", "-sn"], timeout=60, on_line=on_line)
            parsed = nmap_parser.parse_ipv6(raw)
            parsed["ipv6_assessed"] = True
            return (parsed, raw.get("stdout"))

        if test_id == "U06":
            if (
                getattr(tools_client, "scanner_in_docker", False)
                and getattr(tools_client, "backend_in_docker", False)
            ):
                try:
                    parsed, raw_out = await self._docker_tcp_inventory(device_ip, device)
                    _PORT_SCAN_CACHE[run_id] = parsed
                    from app.services.wobbly_cable import get_cable_handler
                    _handler = get_cable_handler(run_id)
                    if _handler and parsed.get("open_ports"):
                        _handler.update_probe_ports(
                            extract_probe_ports(parsed["open_ports"]),
                            known_service_ports=extract_known_probe_ports(parsed["open_ports"]),
                        )
                    return (parsed, raw_out)
                except Exception as exc:
                    logger.warning("U06 Docker TCP inventory failed for %s; falling back to nmap -p-: %s", device_ip, exc)

            raw = await tools_client.nmap_stream(
                device_ip,
                [
                    "-sS", "-p-", "-T4", "--min-rate", "500",
                    "--max-retries", "1", "--host-timeout", "180s",
                    "--stats-every", "15s", "--defeat-rst-ratelimit",
                    "--open", "-n", "-oX", "-",
                ],
                timeout=240,
                on_line=on_line,
            )
            xml_out = _nmap_xml_or_raise("U06", raw)
            parsed = nmap_parser.parse_xml(xml_out)
            if not parsed.get("open_ports"):
                try:
                    fallback, fallback_raw = await self._docker_tcp_inventory(device_ip, device)
                    if fallback.get("open_ports"):
                        parsed = _merge_nmap_scan_data(parsed, fallback)
                        parsed["scan_note"] = (
                            "Full scan returned no open ports; known/common ports were verified "
                            "with TCP connect fallback."
                        )
                        xml_out = f"{xml_out}\n\nTCP probe fallback:\n{fallback_raw}"
                except Exception as exc:
                    logger.debug("U06 TCP fallback found no ports for %s: %s", device_ip, exc)
            _PORT_SCAN_CACHE[run_id] = parsed
            # Hot-update the cable handler's probe ports with newly discovered ports
            from app.services.wobbly_cable import get_cable_handler
            _handler = get_cable_handler(run_id)
            if _handler and parsed.get("open_ports"):
                _handler.update_probe_ports(
                    extract_probe_ports(parsed["open_ports"]),
                    known_service_ports=extract_known_probe_ports(parsed["open_ports"]),
                )
            return (parsed, xml_out)

        if test_id == "U07":
            raw = await tools_client.nmap_stream(
                device_ip,
                ["-sU", "--top-ports", "100", "--max-retries", "1", "--host-timeout", "60s", "--open", "-n", "-oX", "-"],
                timeout=90,
                on_line=on_line,
            )
            xml_out = _nmap_xml_or_raise("U07", raw)
            parsed = nmap_parser.parse_xml(xml_out)
            _PORT_SCAN_CACHE[f"{run_id}_u07"] = parsed
            return (parsed, xml_out)

        if test_id == "U08":
            # Use U06's discovered ports if available for consistency
            u08_args = ["-sV", "--open", "-oX", "-"]
            u06_cached = _PORT_SCAN_CACHE.get(run_id)
            if u06_cached and u06_cached.get("open_ports"):
                port_list = ",".join(
                    str(p["port"]) for p in u06_cached["open_ports"] if "port" in p
                )
                if port_list:
                    u08_args = ["-sV", "-p", port_list, "--open", "-oX", "-"]
                    logger.info("U08: targeting %d ports from U06 scan", len(u06_cached["open_ports"]))
            raw = await tools_client.nmap_stream(
                device_ip, u08_args, timeout=300, on_line=on_line
            )
            xml_out = _nmap_xml_or_raise("U08", raw)
            parsed = nmap_parser.parse_xml(xml_out)
            # Store U08 data as fallback for U09 when U06 cache is empty
            _PORT_SCAN_CACHE[f"{run_id}_u08"] = parsed
            return (parsed, xml_out)

        if test_id == "U09":
            cached = _merge_nmap_scan_data(
                _PORT_SCAN_CACHE.get(run_id),
                _PORT_SCAN_CACHE.get(f"{run_id}_u07"),
                _PORT_SCAN_CACHE.get(f"{run_id}_u08"),
            )
            if _has_nmap_scan_evidence(cached):
                return (_filter_definite_open_ports(cached), None)
            # Fallback: use U08 service detection data if U06 full scan was empty
            u08_cached = _PORT_SCAN_CACHE.get(f"{run_id}_u08")
            if u08_cached and u08_cached.get("open_ports"):
                logger.info("U09: using U08 service scan data as fallback (U06 cache empty)")
                return (u08_cached, None)
            raw = await tools_client.nmap(
                device_ip,
                [
                    "-sS", "-p-", "-T4", "--min-rate", "500",
                    "--max-retries", "1", "--host-timeout", "180s",
                    "--stats-every", "15s", "--defeat-rst-ratelimit",
                    "--open", "-n", "-oX", "-",
                ],
                timeout=240,
            )
            xml_out = _nmap_xml_or_raise("U09", raw)
            parsed = nmap_parser.parse_xml(xml_out)
            _PORT_SCAN_CACHE[run_id] = parsed
            return (parsed, xml_out)

        if test_id in ("U10", "U11", "U12", "U13"):
            cached = _TESTSSL_CACHE.get(run_id)
            if cached:
                return (cached, None)
            # Determine TLS port from port scan cache (prefer 443, fallback to other HTTPS ports)
            tls_port = 443
            port_cache = _PORT_SCAN_CACHE.get(run_id) or _PORT_SCAN_CACHE.get(f"{run_id}_u08") or {}
            open_ports = port_cache.get("open_ports", [])
            https_ports = [p["port"] for p in open_ports if p.get("service") in ("https", "ssl/http", "ssl/https")]
            if 443 not in [p["port"] for p in open_ports] and https_ports:
                tls_port = https_ports[0]
            elif 443 not in [p["port"] for p in open_ports] and not https_ports:
                # Check if any common TLS ports are open
                common_tls = [443, 8443, 8080, 4443]
                found = [p["port"] for p in open_ports if p["port"] in common_tls]
                if found:
                    tls_port = found[0]
            target = f"{device_ip}:{tls_port}" if tls_port != 443 else device_ip
            fast_tls_probe = os.environ.get("EDQ_FAST_TLS_PROBE", "true").strip().lower() not in {
                "0", "false", "no", "off"
            }
            if fast_tls_probe:
                try:
                    parsed = await self._tls_probe_fallback(device_ip, tls_port)
                    if parsed.get("tls_versions"):
                        _TESTSSL_CACHE[run_id] = parsed
                        return (parsed, None)
                except Exception as exc:
                    logger.debug("Fast TLS probe failed for %s:%s: %s", device_ip, tls_port, exc)

            raw = await tools_client.testssl_stream(target, ["--ip", "one", "--fast"], timeout=300, on_line=on_line)
            output_file = raw.get("output_file", "")
            if output_file:
                parsed = testssl_parser.parse(output_file)
            else:
                parsed = testssl_parser.parse_from_stdout(raw.get("stdout", ""))
            if not parsed.get("tls_versions"):
                try:
                    parsed = _merge_tls_probe_fallback(
                        parsed,
                        await self._tls_probe_fallback(device_ip, tls_port),
                    )
                except Exception as exc:
                    logger.debug("TLS fallback probe failed for %s:%s: %s", device_ip, tls_port, exc)
            _TESTSSL_CACHE[run_id] = parsed
            return (parsed, raw.get("stdout"))

        if test_id == "U14":
            parsed = await self._capture_http_security_headers(device_ip, run_id)
            return (parsed, parsed.get("raw_headers"))

        if test_id == "U35":
            # Auto-detect HTTP/HTTPS port from scan cache
            nikto_args = []
            port_cache = _PORT_SCAN_CACHE.get(run_id) or _PORT_SCAN_CACHE.get(f"{run_id}_u08") or {}
            open_ports = port_cache.get("open_ports", [])
            http_candidates = [
                p for p in open_ports
                if p.get("port") is not None and _is_definite_open_port(p) and _is_http_service(p)
            ]
            http_ports = [int(p["port"]) for p in http_candidates]
            if http_ports:
                nikto_args.extend(["-p", str(http_ports[0])])
                if any(_is_https_service(p) for p in http_candidates if int(p["port"]) == http_ports[0]):
                    nikto_args.append("-ssl")
            raw = await tools_client.nikto_stream(device_ip, nikto_args, timeout=300, on_line=on_line)
            parsed = {"raw": raw.get("stdout", ""), "stdout": raw.get("stdout", "")}
            return (parsed, raw.get("stdout"))

        if test_id == "U15":
            port_cache = _merge_nmap_scan_data(
                _PORT_SCAN_CACHE.get(run_id),
                _PORT_SCAN_CACHE.get(f"{run_id}_u08"),
            )
            ssh_ports = [
                int(p["port"]) for p in port_cache.get("open_ports", [])
                if p.get("port") is not None
                and _is_definite_open_port(p)
                and (int(p["port"]) == 22 or str(p.get("service") or "").lower() == "ssh")
            ]
            ssh_port = ssh_ports[0] if ssh_ports else 22
            args = ["-j"] if ssh_port == 22 else ["-p", str(ssh_port), "-j"]
            raw = await tools_client.ssh_audit_stream(device_ip, args, timeout=120, on_line=on_line)
            parsed = ssh_audit_parser.parse(raw)
            parsed["target_port"] = ssh_port
            return (parsed, raw.get("stdout"))

        if test_id == "U16":
            port_cache = _merge_nmap_scan_data(
                _PORT_SCAN_CACHE.get(run_id),
                _PORT_SCAN_CACHE.get(f"{run_id}_u08"),
            )
            web_ports = [
                p for p in port_cache.get("open_ports", [])
                if _is_definite_open_port(p) and _is_http_service(p)
            ]
            if _has_nmap_scan_evidence(port_cache) and not web_ports:
                return (
                    {
                        "found_credentials": [],
                        "services_tested": [],
                        "check_ran": False,
                        "reason": "No HTTP/HTTPS service detected for default credential testing.",
                    },
                    None,
                )
            ordered_web_ports = sorted(
                web_ports,
                key=lambda p: (0 if int(p.get("port") or 0) == 80 else 1, int(p.get("port") or 0)),
            )
            for candidate in ordered_web_ports or [{"port": 80, "service": "http"}]:
                candidate_port = int(candidate.get("port") or 80)
                candidate_service = "https-get" if _is_https_service(candidate) else "http-get"
                easyio_result = await self._check_easyio_default_credentials(
                    device_ip,
                    candidate_port,
                    candidate_service,
                )
                if easyio_result is not None:
                    return (easyio_result, json.dumps(easyio_result, sort_keys=True))

            selected = ordered_web_ports[0] if ordered_web_ports else {"port": 80, "service": "http"}
            selected_port = int(selected.get("port") or 80)
            service = "https-get" if _is_https_service(selected) else "http-get"
            auth_surface = await self._detect_http_auth_surface(device_ip, selected_port, service)
            if not auth_surface.get("auth_required"):
                return (
                    {
                        "found_credentials": [],
                        "services_tested": [
                            {
                                "service": service,
                                "port": selected_port,
                                "protocol": "tcp",
                            }
                        ],
                        "check_ran": False,
                        "reason": auth_surface.get("reason") or "No HTTP authentication challenge or login form detected.",
                    },
                    None,
                )
            args = ["-C", "/usr/share/wordlists/common.txt", "-f"]
            if (service == "http-get" and selected_port != 80) or (service == "https-get" and selected_port != 443):
                args.extend(["-s", str(selected_port)])
            args.extend([device_ip, service])
            raw = await tools_client.hydra_stream(
                device_ip,
                args,
                timeout=120,
                on_line=on_line,
            )
            parsed = hydra_parser.parse(raw)
            parsed["services_tested"] = [
                {
                    "service": service,
                    "port": selected_port,
                    "protocol": "tcp",
                }
            ]
            parsed["check_ran"] = bool((raw.get("stdout") or "").strip())
            return (parsed, raw.get("stdout"))

        if test_id == "U17":
            parsed = await self._test_brute_force_protection(device_ip)
            return (parsed, None)

        if test_id == "U18":
            parsed = await self._test_http_redirect(device_ip)
            return (parsed, None)

        if test_id == "U19":
            try:
                raw = await tools_client.nmap_stream(
                    device_ip,
                    ["-O", "--osscan-guess", "--host-timeout", "75s", "-oX", "-"],
                    timeout=90,
                    on_line=on_line,
                )
                xml_out = _nmap_xml_or_raise("U19", raw)
                parsed = nmap_parser.parse_xml(xml_out)
            except Exception as exc:
                logger.debug("U19 OS scan failed for %s: %s", device_ip, exc)
                parsed = {"os_scan_inconclusive": True, "os_scan_error": str(exc)}
                xml_out = str(exc)
            # Fallback: infer OS from service versions if -O failed
            if not parsed.get("os_fingerprint"):
                svc_cache = _PORT_SCAN_CACHE.get(f"{run_id}_u08") or _PORT_SCAN_CACHE.get(run_id)
                if svc_cache and svc_cache.get("open_ports"):
                    inferred = _infer_os_from_services(svc_cache["open_ports"])
                    if inferred:
                        parsed["os_fingerprint"] = inferred
            return (parsed, xml_out)

        if test_id == "U26":
            if connection_scenario == "direct" and settings.PROTOCOL_OBSERVER_ENABLED:
                try:
                    observed = await observe_ntp_queries(expected_device_ip=device_ip)
                    if observed.get("observed"):
                        return (
                            {
                                "ntp_open": True,
                                "ntp_version": observed.get("version"),
                                "ntp_observed_sync": True,
                                "ntp_script_output": "\n".join(
                                    f"{event.get('source_ip')} version {event.get('version')} mode {event.get('mode')}"
                                    for event in observed.get("events", [])
                                ),
                            },
                            None,
                        )
                except Exception as exc:
                    logger.debug("U26 NTP observer unavailable for %s: %s", device_ip, exc)
            udp_cache = _PORT_SCAN_CACHE.get(f"{run_id}_u07") or {}
            ntp_port = next(
                (
                    p for p in udp_cache.get("open_ports", [])
                    if p.get("port") == 123 and _is_definite_open_port(p, script_id="ntp-info")
                ),
                None,
            )
            ntp_inconclusive = any(
                p.get("port") == 123 and str(p.get("state") or "").lower() == "open|filtered"
                for p in udp_cache.get("open_ports", [])
            )
            raw_out = None
            if ntp_port is None:
                raw = await tools_client.nmap_stream(
                    device_ip,
                    ["-sU", "-p", "123", "--script", "ntp-info", "--host-timeout", "30s", "--open", "-oX", "-"],
                    timeout=60,
                    on_line=on_line,
                )
                raw_out = _nmap_xml_or_raise("U26", raw)
                udp_parsed = nmap_parser.parse_xml(raw_out)
                ntp_port = next(
                    (
                        p for p in udp_parsed.get("open_ports", [])
                        if p.get("port") == 123 and _is_definite_open_port(p, script_id="ntp-info")
                    ),
                    None,
                )
                ntp_inconclusive = ntp_inconclusive or any(
                    p.get("port") == 123 and str(p.get("state") or "").lower() == "open|filtered"
                    for p in udp_parsed.get("open_ports", [])
                )

            script_output = ""
            ntp_version = None
            if ntp_port:
                for script in ntp_port.get("scripts", []) or []:
                    if script.get("id") == "ntp-info":
                        script_output = script.get("output", "") or ""
                        match = re.search(r"\b(?:version|v)\s*([0-9]+)\b", script_output, re.IGNORECASE)
                        if match:
                            ntp_version = match.group(1)
                        break

            return (
                {
                    "ntp_open": ntp_port is not None,
                    "ntp_service": ntp_port.get("service") if ntp_port else None,
                    "ntp_version": ntp_version or (ntp_port.get("version") if ntp_port else None),
                    "ntp_script_output": script_output,
                    "ntp_observed_sync": False,
                    "ntp_inconclusive": ntp_port is None and ntp_inconclusive,
                },
                raw_out,
            )

        if test_id == "U28":
            udp_cache = _PORT_SCAN_CACHE.get(f"{run_id}_u07") or {}
            bacnet_port = next(
                (
                    p for p in udp_cache.get("open_ports", [])
                    if p.get("port") == 47808 and _is_definite_open_port(p, script_id="bacnet-info")
                ),
                None,
            )
            bacnet_inconclusive = any(
                p.get("port") == 47808 and str(p.get("state") or "").lower() == "open|filtered"
                for p in udp_cache.get("open_ports", [])
            )
            raw_out = None
            if bacnet_port is None:
                raw = await tools_client.nmap_stream(
                    device_ip,
                    ["-sU", "-p", "47808", "--script", "bacnet-info", "--host-timeout", "30s", "--open", "-oX", "-"],
                    timeout=60,
                    on_line=on_line,
                )
                raw_out = _nmap_xml_or_raise("U28", raw)
                udp_parsed = nmap_parser.parse_xml(raw_out)
                bacnet_port = next(
                    (
                        p for p in udp_parsed.get("open_ports", [])
                        if p.get("port") == 47808 and _is_definite_open_port(p, script_id="bacnet-info")
                    ),
                    None,
                )
                bacnet_inconclusive = bacnet_inconclusive or any(
                    p.get("port") == 47808 and str(p.get("state") or "").lower() == "open|filtered"
                    for p in udp_parsed.get("open_ports", [])
                )

            bacnet_script = None
            for script in (bacnet_port.get("scripts", []) if bacnet_port else []) or []:
                if script.get("id") == "bacnet-info":
                    bacnet_script = script
                    break

            return (
                {
                    "bacnet_open": bacnet_port is not None,
                    "bacnet_service": bacnet_port.get("service") if bacnet_port else None,
                    "bacnet_version": bacnet_port.get("version") if bacnet_port else None,
                    "bacnet_details": (bacnet_script or {}).get("details") or {},
                    "bacnet_script_output": (bacnet_script or {}).get("output") or "",
                    "bacnet_inconclusive": bacnet_port is None and bacnet_inconclusive,
                },
                raw_out,
            )

        if test_id == "U29":
            if connection_scenario == "direct" and settings.PROTOCOL_OBSERVER_ENABLED:
                try:
                    observed = await observe_dns_queries(expected_device_ip=device_ip)
                    if observed.get("observed"):
                        queries = observed.get("events", [])
                        return (
                            {
                                "dns_open": True,
                                "dns_observed_requests": True,
                                "dns_service": "dns-observer",
                                "dns_version": None,
                                "dns_queries": queries,
                            },
                            None,
                        )
                except Exception as exc:
                    logger.debug("U29 DNS observer unavailable for %s: %s", device_ip, exc)
            udp_cache = _PORT_SCAN_CACHE.get(f"{run_id}_u07") or {}
            dns_port = next(
                (p for p in udp_cache.get("open_ports", []) if p.get("port") == 53 and _is_definite_open_port(p)),
                None,
            )
            dns_inconclusive = any(
                p.get("port") == 53 and str(p.get("state") or "").lower() == "open|filtered"
                for p in udp_cache.get("open_ports", [])
            )
            raw_out = None
            if dns_port is None:
                try:
                    raw = await tools_client.nmap_stream(
                        device_ip,
                        ["-sU", "-p", "53", "--max-retries", "1", "--host-timeout", "30s", "--open", "-n", "-oX", "-"],
                        timeout=45,
                        on_line=on_line,
                    )
                    raw_out = _nmap_xml_or_raise("U29", raw)
                    udp_parsed = nmap_parser.parse_xml(raw_out)
                except Exception as exc:
                    udp_parsed = _udp_inconclusive_result([53], str(exc))
                    raw_out = str(exc)
                dns_port = next(
                    (p for p in udp_parsed.get("open_ports", []) if p.get("port") == 53 and _is_definite_open_port(p)),
                    None,
                )
                dns_inconclusive = dns_inconclusive or any(
                    p.get("port") == 53 and str(p.get("state") or "").lower() == "open|filtered"
                    for p in udp_parsed.get("open_ports", [])
                )
            return (
                {
                    "dns_open": dns_port is not None,
                    "dns_service": dns_port.get("service") if dns_port else None,
                    "dns_version": dns_port.get("version") if dns_port else None,
                    "dns_observed_requests": False,
                    "dns_inconclusive": dns_port is None and dns_inconclusive,
                },
                raw_out,
            )

        if test_id == "U31":
            try:
                raw = await tools_client.nmap_stream(
                    device_ip,
                    ["-sU", "-p", "161,162", "--max-retries", "1", "--host-timeout", "30s", "--open", "-n", "-oX", "-"],
                    timeout=45,
                    on_line=on_line,
                )
                xml_out = _nmap_xml_or_raise("U31", raw)
                parsed = nmap_parser.parse_xml(xml_out)
            except Exception as exc:
                parsed = _udp_inconclusive_result([161, 162], str(exc))
                xml_out = str(exc)
            snmp_ports = [
                p for p in parsed.get("open_ports", [])
                if p.get("port") in (161, 162) and _is_definite_open_port(p, script_id="snmp-info")
            ]
            snmpwalk_output = ""
            if snmp_ports:
                for version in ["2c", "1"]:
                    try:
                        sw_raw = await tools_client.snmpwalk(
                            device_ip,
                            ["-v", version, "-c", "public", "-t", "5", "-r", "0", "-On"],
                            timeout=15,
                        )
                        sw_out = sw_raw.get("stdout", "")
                        if sw_out:
                            snmpwalk_output += f"\n--- snmpwalk v{version} ---\n{sw_out}"
                    except Exception:
                        pass
            combined_stdout = xml_out + snmpwalk_output
            parsed["snmpwalk_output"] = snmpwalk_output
            return (parsed, combined_stdout)

        if test_id == "U32":
            try:
                raw = await tools_client.nmap_stream(
                    device_ip,
                    ["-sU", "-p", "1900", "--max-retries", "1", "--host-timeout", "30s", "--open", "-n", "-oX", "-"],
                    timeout=45,
                    on_line=on_line,
                )
                xml_out = _nmap_xml_or_raise("U32", raw)
                parsed = nmap_parser.parse_xml(xml_out)
            except Exception as exc:
                parsed = _udp_inconclusive_result([1900], str(exc))
                xml_out = str(exc)
            return (parsed, xml_out)

        if test_id == "U33":
            try:
                raw = await tools_client.nmap_stream(
                    device_ip,
                    ["-sU", "-p", "5353", "--max-retries", "1", "--host-timeout", "30s", "--open", "-n", "-oX", "-"],
                    timeout=45,
                    on_line=on_line,
                )
                xml_out = _nmap_xml_or_raise("U33", raw)
                parsed = nmap_parser.parse_xml(xml_out)
            except Exception as exc:
                parsed = _udp_inconclusive_result([5353], str(exc))
                xml_out = str(exc)
            return (parsed, xml_out)

        if test_id == "U34":
            cached = _merge_nmap_scan_data(
                _PORT_SCAN_CACHE.get(run_id),
                _PORT_SCAN_CACHE.get(f"{run_id}_u07"),
                _PORT_SCAN_CACHE.get(f"{run_id}_u08"),
            )
            if _has_nmap_scan_evidence(cached):
                open_pairs = {
                    (str(p.get("protocol") or "tcp").lower(), int(p["port"]))
                    for p in cached.get("open_ports", [])
                    if p.get("port") is not None and _is_definite_open_port(p)
                }
                insecure_ports = sorted(
                    port for protocol, port in open_pairs
                    if (protocol, port) in {("tcp", 21), ("tcp", 23), ("tcp", 110), ("tcp", 143), ("udp", 69)}
                )
                return (
                    {
                        "telnet_open": ("tcp", 23) in open_pairs,
                        "ftp_open": ("tcp", 21) in open_pairs,
                        "insecure_ports": insecure_ports,
                    },
                    None,
                )
            raw = await tools_client.nmap(
                device_ip, ["-sS", "-p", "21,23,69,110,143", "--open", "-oX", "-"], timeout=60
            )
            xml_out = _nmap_xml_or_raise("U34", raw)
            parsed = nmap_parser.parse_xml(xml_out)
            udp_raw = await tools_client.nmap(
                device_ip, ["-sU", "-p", "69", "--open", "-oX", "-"], timeout=60
            )
            udp_xml_out = _nmap_xml_or_raise("U34", udp_raw)
            udp_parsed = nmap_parser.parse_xml(udp_xml_out)
            combined = _merge_nmap_scan_data(parsed, udp_parsed)
            open_pairs = {
                (str(p.get("protocol") or "tcp").lower(), int(p["port"]))
                for p in combined.get("open_ports", [])
                if p.get("port") is not None and _is_definite_open_port(p)
            }
            insecure_ports = sorted(
                port for protocol, port in open_pairs
                if (protocol, port) in {("tcp", 21), ("tcp", 23), ("tcp", 110), ("tcp", 143), ("udp", 69)}
            )
            return (
                {
                    "telnet_open": ("tcp", 23) in open_pairs,
                    "ftp_open": ("tcp", 21) in open_pairs,
                    "insecure_ports": insecure_ports,
                },
                xml_out + "\n" + udp_xml_out,
            )

        if test_id == "U36":
            try:
                raw = await tools_client.nmap_stream(
                    device_ip, ["-sV", "--script", "banner", "--open", "-oX", "-"], timeout=180, on_line=on_line
                )
                xml_out = _nmap_xml_or_raise("U36", raw)
                parsed = nmap_parser.parse_xml(xml_out)
                if parsed.get("open_ports"):
                    return (parsed, xml_out)
            except Exception as exc:
                logger.debug("U36 banner scan failed for %s: %s", device_ip, exc)
            u08_cached = _PORT_SCAN_CACHE.get(f"{run_id}_u08")
            if u08_cached and u08_cached.get("open_ports"):
                return (u08_cached, None)
            return ({"open_ports": []}, None)

        if test_id == "U37":
            parsed = await self._test_rtsp_auth(device_ip)
            return (parsed, None)

        return ({}, None)

    async def _detect_http_auth_surface(
        self,
        device_ip: str,
        port: int,
        service: str,
    ) -> dict[str, Any]:
        """Detect whether a web endpoint actually presents an auth surface."""
        import httpx

        scheme = "https" if service.startswith("https") or port == 443 else "http"
        url = f"{scheme}://{device_ip}:{port}" if port not in (80, 443) else f"{scheme}://{device_ip}"
        try:
            async with httpx.AsyncClient(timeout=10, verify=False, follow_redirects=True) as client:
                resp = await client.get(url)
        except Exception as exc:
            return {"auth_required": False, "reason": f"HTTP auth surface probe failed: {exc}"}

        if resp.status_code == 401 or resp.headers.get("www-authenticate"):
            return {"auth_required": True, "auth_type": "basic", "url": url}

        body = (resp.text or "").lower()
        if "<form" in body and ("password" in body or "passwd" in body or "login" in body):
            if "authtoken" in body or "user[authhash]" in body:
                return {
                    "auth_required": False,
                    "auth_type": "tokenized_form",
                    "url": str(resp.url),
                    "reason": "Tokenized web login detected; generic Hydra form check is not applicable.",
                }
            return {"auth_required": True, "auth_type": "form", "url": str(resp.url)}

        return {
            "auth_required": False,
            "url": str(resp.url),
            "reason": f"Endpoint returned HTTP {resp.status_code} without an authentication challenge.",
        }

    async def _check_easyio_default_credentials(
        self,
        device_ip: str,
        port: int,
        service: str,
    ) -> dict[str, Any] | None:
        """Check EasyIO CPT tokenized login without treating public pages as auth success."""
        import httpx

        scheme = "https" if service.startswith("https") or port == 443 else "http"
        base = f"{scheme}://{device_ip}:{port}" if port not in (80, 443) else f"{scheme}://{device_ip}"
        signin_url = f"{base}/sdcard/cpt/app/signin.php"
        headers = {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}
        common_pairs = [
            ("admin", "admin"),
            ("admin", "password"),
            ("admin", "1234"),
            ("admin", "12345"),
            ("admin", "123456"),
            ("admin", "admin123"),
            ("admin", "Password1"),
            ("admin", "changeme"),
            ("admin", "default"),
            ("admin", "welcome"),
            ("root", "root"),
            ("root", "password"),
            ("root", "toor"),
            ("root", "1234"),
            ("root", "changeme"),
            ("user", "user"),
            ("user", "password"),
            ("user", "1234"),
            ("guest", "guest"),
            ("guest", "password"),
            ("operator", "operator"),
            ("service", "service"),
            ("test", "test"),
            ("demo", "demo"),
            ("support", "support"),
            ("monitor", "monitor"),
            ("manager", "manager"),
        ]

        try:
            async with httpx.AsyncClient(timeout=8, verify=False, follow_redirects=True) as client:
                landing = await client.get(f"{base}/sdcard/cpt/app/signin.php")
                if "signin cpt graphics" not in (landing.text or "").lower():
                    return None
                for username, password in common_pairs:
                    try:
                        token_resp = await client.get(
                            signin_url,
                            params={"user[name]": username},
                            headers=headers,
                        )
                        content_type = token_resp.headers.get("content-type", "")
                        if "json" not in content_type.lower() and not token_resp.text.strip().startswith("{"):
                            continue
                        token = (token_resp.json().get("authToken") or "").strip()
                        if "_" not in token:
                            continue
                        token1, token2 = token.split("_", 1)
                        hash1 = hashlib.sha1(f"{password}{token1}".encode()).hexdigest()
                        auth_hash = hashlib.sha1(f"{hash1}{token2}".encode()).hexdigest()
                        login_resp = await client.post(
                            signin_url,
                            data={
                                "user[name]": username,
                                "user[authHash]": auth_hash,
                                "remember_me": "false",
                            },
                            headers=headers,
                        )
                        try:
                            payload = login_resp.json()
                        except Exception:
                            payload = {}
                    except Exception as exc:
                        logger.debug("EasyIO credential attempt failed for %s: %s", username, exc)
                        continue
                    if payload.get("redirectUrl") and not payload.get("error"):
                        return {
                            "found_credentials": [
                                {
                                    "login": username,
                                    "password": password,
                                    "service": "easyio-cpt-form",
                                    "host": device_ip,
                                }
                            ],
                            "services_tested": [
                                {
                                    "service": "easyio-cpt-form",
                                    "port": port,
                                    "protocol": "tcp",
                                    "path": "/sdcard/cpt/app/signin.php",
                                }
                            ],
                            "check_ran": True,
                            "method": "easyio-cpt-token",
                        }

            return {
                "found_credentials": [],
                "services_tested": [
                    {
                        "service": "easyio-cpt-form",
                        "port": port,
                        "protocol": "tcp",
                        "path": "/sdcard/cpt/app/signin.php",
                    }
                ],
                "check_ran": True,
                "method": "easyio-cpt-token",
            }
        except Exception as exc:
            logger.debug("EasyIO default credential probe failed for %s: %s", device_ip, exc)
            return None

    async def _test_brute_force_protection(self, device_ip: str) -> dict[str, Any]:
        """Test brute force protection by sending rapid login attempts.

        First detects whether the device uses form-based or HTTP basic auth,
        then runs Hydra with the appropriate module.  Tries HTTPS if HTTP is
        not available.
        """
        import ipaddress as _ipaddress
        import httpx

        # Validate IP address to prevent argument injection via device_ip
        try:
            _ipaddress.ip_address(device_ip)
        except ValueError:
            logger.error("Invalid device IP address for brute force test: %r", device_ip)
            return {"lockout_detected": False, "auth_type": "http-get", "error": "Invalid device IP address"}

        auth_type = "http-get"
        form_path = "/"
        form_fields = ""
        use_ssl = False

        # Detect auth type by checking for a login form (try HTTP, then HTTPS)
        try:
            async with httpx.AsyncClient(timeout=10, verify=False, follow_redirects=True) as client:
                resp = None
                for scheme in ("http", "https"):
                    try:
                        resp = await client.get(f"{scheme}://{device_ip}/")
                        if scheme == "https":
                            use_ssl = True
                        break
                    except Exception:
                        continue
                if resp is not None:
                    body = resp.text.lower()
                    # Look for common login form patterns
                    if "<form" in body and ("password" in body or "passwd" in body or "login" in body):
                        if "authtoken" in body or "user[authhash]" in body:
                            return {
                                "lockout_detected": False,
                                "auth_type": "tokenized_form",
                                "attempts": 0,
                                "error": "",
                                "lockout_duration_seconds": None,
                                "check_ran": False,
                                "reason": "Tokenized web login detected; generic lockout probing is not applicable without a device-specific authenticator.",
                            }
                        auth_type = "http-post-form"
                        # Try common login paths
                        scheme = "https" if use_ssl else "http"
                        for path in ["/login", "/auth", "/user/login", "/api/login", "/"]:
                            try:
                                r = await client.get(f"{scheme}://{device_ip}{path}")
                                if "<form" in r.text.lower() and "password" in r.text.lower():
                                    form_path = path
                                    break
                            except Exception:
                                continue
                        form_fields = f"{form_path}:username=^USER^&password=^PASS^:F=incorrect:H=Content-Type: application/x-www-form-urlencoded"
                    elif resp.status_code == 401:
                        auth_type = "http-get"
                    else:
                        signin_url = f"{resp.url.scheme}://{device_ip}/sdcard/cpt/app/signin.php"
                        try:
                            signin = await client.get(signin_url)
                            if "signin cpt graphics" in (signin.text or "").lower():
                                return {
                                    "lockout_detected": False,
                                    "auth_type": "tokenized_form",
                                    "attempts": 0,
                                    "error": "",
                                    "lockout_duration_seconds": None,
                                    "check_ran": False,
                                    "reason": "EasyIO tokenized web login detected; generic lockout probing is not applicable without the EasyIO authenticator.",
                                }
                        except Exception:
                            pass
                        return {
                            "lockout_detected": False,
                            "auth_type": "none",
                            "attempts": 0,
                            "error": "",
                            "lockout_duration_seconds": None,
                            "check_ran": False,
                            "reason": f"HTTP endpoint returned {resp.status_code} without an authentication challenge.",
                        }
        except Exception as e:
            logger.debug("Auth type detection failed for %s: %s", device_ip, e)

        lockout_detected = False
        lockout_duration_seconds: int | None = None
        error_msg = ""
        attempts_made = 0

        def _text_indicates_lockout(text: str) -> bool:
            lowered = (text or "").lower()
            return any(
                marker in lowered
                for marker in (
                    "blocked",
                    "locked",
                    "lockout",
                    "too many",
                    "rate limit",
                    "rate-limit",
                    "temporarily unavailable",
                    "retry later",
                )
            )

        try:
            base_args = ["-C", "/usr/share/wordlists/common.txt", "-t", "8", "-V"]
            if use_ssl:
                base_args.extend(["-s", "443"])
            base_args.append(device_ip)
            if auth_type == "http-post-form":
                svc = "https-post-form" if use_ssl else "http-post-form"
                base_args.append(svc)
                if form_fields:
                    base_args.append(form_fields)
            else:
                base_args.append("https-get" if use_ssl else "http-get")

            raw = await tools_client.hydra(device_ip, base_args, timeout=90)
            stdout = raw.get("stdout", "")
            error_msg = stdout
            attempts_made += 27
            lockout_duration_seconds = self._extract_lockout_duration_seconds(stdout)

            if _text_indicates_lockout(stdout):
                lockout_detected = True
            elif raw.get("exit_code", 1) != 0 and (
                "connection refused" in stdout.lower()
                or "timeout" in stdout.lower()
            ):
                lockout_detected = True

            if not lockout_detected:
                try:
                    async with httpx.AsyncClient(timeout=10, verify=False, follow_redirects=False) as client:
                        scheme = "https" if use_ssl else "http"
                        for attempt in range(10):
                            if auth_type == "http-post-form":
                                verify_resp = await client.post(
                                    f"{scheme}://{device_ip}{form_path or '/'}",
                                    data={
                                        "username": f"invalid{attempt}",
                                        "password": f"invalid{attempt}",
                                    },
                                )
                            else:
                                verify_resp = await client.get(
                                    f"{scheme}://{device_ip}/",
                                    auth=(f"invalid{attempt}", f"invalid{attempt}"),
                                )

                            attempts_made += 1
                            retry_after = verify_resp.headers.get("Retry-After")
                            if retry_after and retry_after.isdigit():
                                lockout_duration_seconds = int(retry_after)
                            elif lockout_duration_seconds is None:
                                lockout_duration_seconds = self._extract_lockout_duration_seconds(
                                    verify_resp.text
                                )
                            if verify_resp.status_code in (403, 423, 429):
                                lockout_detected = True
                                break
                            if _text_indicates_lockout(verify_resp.text):
                                lockout_detected = True
                                break
                            if attempt < 9:
                                await asyncio.sleep(3)
                except (httpx.ConnectError, httpx.ConnectTimeout):
                    lockout_detected = True
                except Exception as e:
                    logger.debug("Unexpected error during hydra probe: %s", e)

        except Exception as exc:
            error_msg = str(exc)
            if "refused" in error_msg.lower() or "timeout" in error_msg.lower():
                lockout_detected = True

        return {
            "lockout_detected": lockout_detected,
            "auth_type": auth_type,
            "attempts": attempts_made,
            "error": error_msg,
            "lockout_duration_seconds": lockout_duration_seconds,
        }

    async def _test_http_redirect(self, device_ip: str) -> dict[str, Any]:
        """Check if HTTP redirects to HTTPS."""
        import httpx

        redirects_to_https = False
        http_open = False
        redirect_location = ""
        redirect_status_code: int | None = None

        try:
            async with httpx.AsyncClient(timeout=10, verify=settings.SSL_VERIFY_DEVICES, follow_redirects=False) as client:
                try:
                    resp = await client.head(f"http://{device_ip}")
                except httpx.HTTPError:
                    resp = await client.get(f"http://{device_ip}")
                http_open = True
                redirect_status_code = resp.status_code
                redirect_location = resp.headers.get("location", "")
                if resp.status_code in (301, 302, 307, 308) and "https" in redirect_location.lower():
                    redirects_to_https = True
        except httpx.ConnectError:
            http_open = False
        except Exception as e:
            logger.debug("HTTP redirect check failed for %s: %s", device_ip, e)

        return {
            "redirects_to_https": redirects_to_https,
            "http_open": http_open,
            "redirect_location": redirect_location,
            "redirect_status_code": redirect_status_code,
        }

    @staticmethod
    def _extract_lockout_duration_seconds(text: str | None) -> int | None:
        lowered = (text or "").lower()
        if not lowered:
            return None
        match = re.search(
            r"(\d+)\s*(second|seconds|sec|secs|minute|minutes|min|mins)\b",
            lowered,
        )
        if not match:
            return None
        value = int(match.group(1))
        unit = match.group(2)
        if unit.startswith("min"):
            return value * 60
        return value

    async def _capture_http_security_headers(self, device_ip: str, run_id: str) -> dict[str, Any]:
        """Capture HTTP response headers so U14 can report exact header output."""
        import httpx

        port_cache = _PORT_SCAN_CACHE.get(run_id) or _PORT_SCAN_CACHE.get(f"{run_id}_u08") or {}
        open_ports = port_cache.get("open_ports", [])
        candidate_ports = [
            p for p in open_ports
            if p.get("port") is not None and _is_definite_open_port(p) and _is_http_service(p)
        ]
        if not candidate_ports:
            return {
                "http_service_detected": False,
                "status_line": None,
                "headers": {},
                "header_lines": [],
                "raw_headers": "",
                "response_url": None,
            }

        https_candidates = [
            p for p in candidate_ports
            if _is_https_service(p)
        ]
        target_port = (https_candidates or candidate_ports)[0]["port"]
        target_service = (https_candidates or candidate_ports)[0].get("service") or "http"
        scheme = "https" if _is_https_service(https_candidates[0] if https_candidates else {"port": target_port, "service": target_service}) else "http"
        url = f"{scheme}://{device_ip}:{target_port}" if target_port not in (80, 443) else f"{scheme}://{device_ip}"

        verify_attempts = [settings.SSL_VERIFY_DEVICES]
        if scheme == "https" and settings.SSL_VERIFY_DEVICES:
            verify_attempts.append(False)

        last_error: Exception | None = None
        for verify in verify_attempts:
            try:
                async with httpx.AsyncClient(
                    timeout=15,
                    verify=verify,
                    follow_redirects=True,
                ) as client:
                    try:
                        resp = await client.head(url)
                    except httpx.HTTPError:
                        resp = await client.get(url)
                break
            except Exception as exc:
                last_error = exc
        else:
            exc = last_error or RuntimeError("No HTTP response")
            logger.debug("HTTP header capture failed for %s: %s", device_ip, exc)
            return {
                "http_service_detected": True,
                "status_line": None,
                "headers": {},
                "header_lines": [],
                "raw_headers": "",
                "response_url": url,
                "error": str(exc),
            }

        http_version = resp.http_version
        if not http_version.upper().startswith("HTTP/"):
            http_version = f"HTTP/{http_version}"
        status_line = f"{http_version} {resp.status_code} {resp.reason_phrase}"
        header_lines = [f"{name}: {value}" for name, value in resp.headers.items()]
        return {
            "http_service_detected": True,
            "status_line": status_line,
            "headers": dict(resp.headers),
            "header_lines": header_lines,
            "raw_headers": "\n".join([status_line, *header_lines]).strip(),
            "response_url": str(resp.url),
        }

    async def _test_rtsp_auth(self, device_ip: str) -> dict[str, Any]:
        """Check if RTSP streams require authentication using raw TCP."""
        rtsp_open = False
        auth_required = False

        writer = None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(device_ip, 554), timeout=10
            )
            rtsp_open = True

            request = (
                f"DESCRIBE rtsp://{device_ip}:554/ RTSP/1.0\r\n"
                f"CSeq: 1\r\n"
                f"Accept: application/sdp\r\n"
                f"\r\n"
            )
            writer.write(request.encode())
            await writer.drain()

            response = await asyncio.wait_for(reader.read(4096), timeout=10)
            response_str = response.decode(errors='replace')

            if '401' in response_str:
                auth_required = True
            elif '200' in response_str:
                auth_required = False

        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            rtsp_open = False
        except Exception as e:
            logger.warning("RTSP check error: %s", e)
        finally:
            if writer:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass

        return {"rtsp_open": rtsp_open, "auth_required": auth_required}

    async def _wait_while_paused(self, run_id: str) -> None:
        """Block while the test run is paused (e.g. by wobbly cable)."""
        while True:
            async with async_session() as db:
                run = await db.get(TestRun, run_id)
                if run is None or not is_paused_test_run_status(run.status):
                    return
            await asyncio.sleep(2)

    async def _is_run_paused_for_cable(self, run_id: str) -> bool:
        async with async_session() as db:
            run = await db.get(TestRun, run_id)
            if run is None:
                return False
            return normalize_test_run_status(run.status) == TestRunStatus.PAUSED_CABLE.value

    async def _finalize_run(self, run_id: str) -> None:
        """Calculate overall verdict and update the test run."""
        async with async_session() as db:
            results_q = await db.execute(
                select(TestResult).where(TestResult.test_run_id == run_id)
            )
            all_results = list(results_q.scalars().all())

            passed = sum(1 for r in all_results if r.verdict == TestVerdict.PASS)
            failed = sum(1 for r in all_results if r.verdict == TestVerdict.FAIL)
            advisory = sum(1 for r in all_results if r.verdict == TestVerdict.ADVISORY)
            na = sum(1 for r in all_results if r.verdict == TestVerdict.NA)
            info = sum(1 for r in all_results if r.verdict == TestVerdict.INFO)
            errors = sum(1 for r in all_results if r.verdict == TestVerdict.ERROR)
            skipped = sum(1 for r in all_results if r.verdict == TestVerdict.SKIPPED_SAFE_MODE)
            pending_manual = sum(
                1 for r in all_results
                if r.verdict == TestVerdict.PENDING and r.tier == TestTier.GUIDED_MANUAL
            )

            essential_failed = any(
                r for r in all_results
                if r.verdict == TestVerdict.FAIL and r.is_essential == "yes"
            )
            completed_count = passed + failed + advisory + na + info + errors + skipped

            run = await db.get(TestRun, run_id)
            if run is None:
                return

            run.passed_tests = passed
            run.failed_tests = failed + errors
            run.advisory_tests = advisory
            run.na_tests = na
            run.completed_tests = completed_count
            run.progress_pct = self._progress_for(run.total_tests, completed_count)
            metadata = dict(run.run_metadata) if isinstance(run.run_metadata, dict) else {}
            metadata.pop("current_test", None)
            metadata["trust_tier_counts"] = {
                "release_blocking": sum(
                    1
                    for r in all_results
                    if (get_test_by_id(r.test_id) or {}).get("trust_level") == "release_blocking"
                ),
                "review_required": sum(
                    1
                    for r in all_results
                    if (get_test_by_id(r.test_id) or {}).get("trust_level") == "review_required"
                ),
                "advisory": sum(
                    1
                    for r in all_results
                    if (get_test_by_id(r.test_id) or {}).get("trust_level") == "advisory"
                ),
                "manual_evidence": sum(
                    1
                    for r in all_results
                    if (get_test_by_id(r.test_id) or {}).get("trust_level") == "manual_evidence"
                ),
            }
            metadata["pending_manual_count"] = pending_manual
            metadata["completed_result_count"] = run.completed_tests
            metadata["info_count"] = info
            metadata["error_count"] = errors
            metadata["skipped_safe_mode_count"] = skipped
            run.run_metadata = metadata

            if pending_manual > 0:
                run.status = TestRunStatus.AWAITING_MANUAL
                run.overall_verdict = None
                run.completed_at = None
            else:
                run.status = TestRunStatus.COMPLETED
                run.completed_at = utcnow_naive()
                if essential_failed:
                    run.overall_verdict = TestRunVerdict.FAIL
                elif failed > 0:
                    run.overall_verdict = TestRunVerdict.FAIL
                elif errors > 0:
                    run.overall_verdict = TestRunVerdict.INCOMPLETE
                elif advisory > 0:
                    run.overall_verdict = TestRunVerdict.QUALIFIED_PASS
                else:
                    run.overall_verdict = TestRunVerdict.PASS

            run.run_metadata = merge_readiness_into_metadata(
                run.run_metadata,
                build_run_readiness_summary(run, all_results),
            )

            await db.commit()

            # Capture values while the ORM object is still bound to the session
            overall_verdict = run.overall_verdict
            run_status = run.status

        await manager.broadcast(f"test-run:{run_id}", {
            "type": "run_complete",
            "data": {
                "run_id": run_id,
                "status": normalize_test_run_status(run_status),
                "overall_verdict": overall_verdict,
                "passed": passed,
                "failed": failed,
                "advisory": advisory,
                "na": na,
                "info": info,
                "errors": errors,
                "pending_manual": pending_manual,
            },
        })

        logger.info(
            "Test run %s finalized: %s (pass=%d fail=%d advisory=%d na=%d pending=%d)",
            run_id,
            overall_verdict or "awaiting_manual",
            passed,
            failed,
            advisory,
            na,
            pending_manual,
        )

        # Auto-learn: offer to save a new DeviceProfile if none matched
        try:
            async with async_session() as db:
                run_row = await db.get(TestRun, run_id)
                if run_row and run_row.run_metadata and run_row.run_metadata.get("fingerprint"):
                    profile = await fingerprinter.learn_from_run(
                        db, run_row.device_id, run_row.run_metadata
                    )
                    if profile:
                        await db.commit()
                        await manager.broadcast(f"test-run:{run_id}", {
                            "type": "profile_learned",
                            "data": {
                                "profile_id": profile.id,
                                "profile_name": profile.name,
                                "category": profile.category,
                            },
                        })
        except Exception as exc:
            logger.warning("Auto-learn failed for run %s: %s", run_id, exc)

    async def _load_run(self, db: AsyncSession, run_id: str) -> TestRun | None:
        result = await db.execute(select(TestRun).where(TestRun.id == run_id))
        return result.scalar_one_or_none()

    async def _load_device(self, db: AsyncSession, device_id: str) -> Device | None:
        result = await db.execute(select(Device).where(Device.id == device_id))
        return result.scalar_one_or_none()

    async def _load_template(self, db: AsyncSession, template_id: str) -> TestTemplate | None:
        result = await db.execute(select(TestTemplate).where(TestTemplate.id == template_id))
        return result.scalar_one_or_none()

    async def _load_whitelist(self, db: AsyncSession, whitelist_id: str | None) -> list[dict]:
        if not whitelist_id:
            return []
        result = await db.execute(
            select(ProtocolWhitelist).where(ProtocolWhitelist.id == whitelist_id)
        )
        wl = result.scalar_one_or_none()
        if wl and wl.entries:
            return wl.entries if isinstance(wl.entries, list) else []
        return []

    async def _set_run_error(self, db: AsyncSession, run: TestRun | None, message: str) -> None:
        if run:
            run.status = TestRunStatus.FAILED
            run.completed_at = utcnow_naive()
            metadata = dict(run.run_metadata) if isinstance(run.run_metadata, dict) else {}
            metadata.pop("current_test", None)
            run.run_metadata = metadata
            await db.commit()

        await manager.broadcast(f"test-run:{run.id if run else 'unknown'}", {
            "type": "run_error",
            "data": {"message": message, "status": TestRunStatus.FAILED.value},
        })


test_engine = TestEngine()


async def recover_orphaned_runs() -> None:
    """On startup, reset any runs left in 'running' state from a crash/restart.

    Also kills any lingering tool processes on the sidecar to prevent
    resource waste from previous runs.
    """
    from app.services.tools_client import tools_client

    # Kill all lingering sidecar processes from previous server instance
    try:
        kill_result = await tools_client.kill_all()
        killed = kill_result.get("killed", 0)
        if killed:
            logger.info("Killed %d orphaned sidecar process(es) on startup", killed)
    except Exception as exc:
        logger.warning("Could not clean sidecar processes on startup: %s", exc)

    async with async_session() as db:
        result = await db.execute(
            select(TestRun).where(TestRun.status.in_([
                TestRunStatus.SELECTING_INTERFACE,
                TestRunStatus.SYNCING,
                TestRunStatus.RUNNING,
                TestRunStatus.PAUSED_CABLE,
                TestRunStatus.PAUSED_MANUAL,
            ]))
        )
        orphans = result.scalars().all()
        for run in orphans:
            run.status = TestRunStatus.FAILED
            run.completed_at = utcnow_naive()
            run.synopsis = (
                (run.synopsis or "")
                + "\n[Auto-reset: server restarted during execution]"
            ).lstrip("\n")
        if orphans:
            await db.commit()
            logger.info("Reset %d orphaned running test run(s) to failed", len(orphans))
