"""Test Execution Engine — orchestrates all tests for a run.

Sequences automatic tool-based tests and creates pending stubs for manual tests.
Streams progress via WebSocket and integrates the Wobbly Cable Handler.
"""

import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

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
from app.services.tools_client import tools_client
from app.services.parsers.nmap_parser import nmap_parser
from app.services.parsers.testssl_parser import testssl_parser
from app.services.parsers.ssh_audit_parser import ssh_audit_parser
from app.services.parsers.hydra_parser import hydra_parser
from app.services.evaluation import evaluate_result
from app.services.connectivity_probe import extract_probe_ports, probe_device_connectivity
from app.services.mac_vendor import resolve_mac_vendor
from app.services.run_readiness import (
    build_run_readiness_summary,
    merge_readiness_into_metadata,
)
from app.services.wobbly_cable import WobblyCableHandler
from app.services.test_library import get_test_by_id
from app.services.device_fingerprinter import fingerprinter, FingerprintResult
from app.services.discovery_service import guess_manufacturer, guess_model
from app.routes.websocket_routes import manager
from app.utils.datetime import utcnow_naive

logger = logging.getLogger("edq.test_engine")

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


def _infer_os_from_services(open_ports: list[dict[str, Any]]) -> str | None:
    """Infer OS from service banners when nmap -O fails."""
    from collections import Counter
    os_hints: list[str] = []
    for p in open_ports:
        version = (p.get("version", "") or "").lower()
        service = (p.get("service", "") or "").lower()
        product = (p.get("product", "") or "").lower()
        combined = f"{service} {version} {product}"
        if any(kw in combined for kw in ("microsoft", "windows", "iis", "msrpc", "netbios", "microsoft-ds")):
            os_hints.append("Windows")
        elif any(kw in combined for kw in ("ubuntu", "debian", "centos", "fedora", "red hat")):
            os_hints.append("Linux")
        elif "openssh" in combined and "windows" not in combined:
            os_hints.append("Linux/Unix")
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
            if run_metadata is not None:
                run_row.run_metadata = run_metadata
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

            if not device.ip_address:
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

            existing_meta = run.run_metadata or {}
            if isinstance(existing_meta, dict):
                existing_meta["tool_versions"] = tool_versions
            run.run_metadata = existing_meta
            await db.commit()

            # Eagerly load all device attributes then detach so they remain
            # accessible after this session closes without triggering lazy-load
            # errors (DetachedInstanceError).
            await db.refresh(device)
            db.expunge(device)

        probe_ports = extract_probe_ports(device.open_ports)
        cable_handler = WobblyCableHandler(
            device.ip_address,
            test_run_id,
            manager,
            probe_ports=probe_ports,
        )
        # Strict pre-flight: require at least one TCP service port to accept a
        # connection. ICMP alone isn't sufficient — a gateway/router on the
        # user's network may respond to ping at the target IP without actually
        # being the device under test. Tests need real services to exercise.
        initial_reachable, probe_method = await probe_device_connectivity(
            device.ip_address, probe_ports=probe_ports
        )
        has_tcp_service = bool(probe_method) and probe_method.startswith("tcp:")
        # For devices with no known open ports (manually added, never scanned),
        # accept ICMP as sufficient to start — the test engine will discover
        # actual ports during execution.
        can_start = has_tcp_service or (initial_reachable and not device.open_ports)
        cable_task = asyncio.create_task(cable_handler.monitor())
        run_started_broadcasted = False

        if can_start:
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
            if initial_reachable:
                logger.warning(
                    "Device %s responded to %s but has no open probeable service ports for run %s; pausing until it becomes testable",
                    device.ip_address,
                    probe_method or "ping",
                    test_run_id,
                )
                pause_message = (
                    f"Device {device.ip_address} is reachable but no supported service "
                    "ports are open yet. Testing is paused until a service port becomes reachable."
                )
            else:
                logger.warning(
                    "Device %s is unreachable for run %s; pausing until connectivity returns",
                    device.ip_address,
                    test_run_id,
                )
                pause_message = (
                    f"Target device {device.ip_address} is unreachable from this "
                    "network. Testing is paused until connectivity is restored."
                )
            await cable_handler.pause_for_disconnect(
                message=pause_message,
                kill_tools=False,
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

            # Scenario-based skipping: certain tests are not applicable in some scenarios
            connection_scenario = getattr(run, "connection_scenario", "direct") or "direct"
            if connection_scenario == "site_network":
                skip_test_ids.update({"U03", "U04"})
                skip_reasons["U03"] = (
                    "Skipped — Switch negotiation test not applicable in site network scenario."
                )
                skip_reasons["U04"] = (
                    "Skipped — DHCP behaviour test not applicable in site network scenario. "
                    "The device is already on an existing network with established DHCP. "
                    "To test DHCP, use the direct cable scenario."
                )
            elif connection_scenario == "test_lab":
                skip_test_ids.add("U03")
                skip_reasons["U03"] = (
                    "Skipped — Switch negotiation test not applicable in test lab scenario."
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

                if effective_tier == "guided_manual":
                    completed += 1
                    async with async_session() as db:
                        result_row = await db.get(TestResult, test_result.id)
                        if result_row and result_row.verdict == TestVerdict.PENDING:
                            result_row.comment = "Awaiting engineer input"
                            await db.commit()

                    await self._persist_run_progress(
                        test_run_id,
                        completed_tests=completed,
                        total_tests=total,
                        status=TestRunStatus.AWAITING_MANUAL,
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

                    # Pre-test connectivity check: verify device is reachable
                    # before starting the test. This catches cable disconnects
                    # that happened between the monitor's poll interval.
                    pre_reachable, _ = await probe_device_connectivity(
                        device.ip_address, probe_ports=probe_ports, tcp_timeout=2.0
                    )
                    if not pre_reachable:
                        logger.warning(
                            "Pre-test probe failed for %s before %s — waiting for cable handler",
                            device.ip_address,
                            test_result.test_id,
                        )
                        # Give the cable handler time to detect and pause
                        await asyncio.sleep(4)
                        if await self._is_run_paused_for_cable(test_run_id):
                            await self._wait_while_paused(test_run_id)
                            continue  # retry from top after cable resumes

                    await manager.broadcast(f"test-run:{test_run_id}", {
                        "type": "test_start",
                        "data": {
                            "test_id": test_result.test_id,
                            "test_name": test_result.test_name,
                            "status": "running",
                            "progress_pct": self._progress_for(total, completed),
                        },
                    })

                    test_started_at = utcnow_naive()
                    verdict, comment, parsed, raw_out, duration = await self._run_single_test(
                        test_def, device.ip_address, test_run_id, whitelist_entries
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

                # Use HTTP server header as model hint
                if service in ("http", "https") and version and not device_row.model and not guessed_model:
                    device_row.model = version
                    changed = True

                # Extract firmware from version strings (e.g. "EasyIO FW-14 v2.3")
                if version and not device_row.firmware_version:
                    fw_match = re.search(r'[Vv]?(\d+\.\d+[\.\d]*)', version)
                    if fw_match:
                        device_row.firmware_version = fw_match.group(0)
                        changed = True

                # Use product name as hostname fallback
                if product and not device_row.hostname:
                    device_row.hostname = product
                    changed = True

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
            # Banner grabbing — look for model/version info in banners
            for p in parsed.get("open_ports", []):
                version = (p.get("version") or "").strip()
                if version and not device_row.model:
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
    ) -> tuple[str, str, dict | None, str | None, float | None]:
        """Execute a single automatic test. Returns (verdict, comment, parsed, raw_output, duration)."""
        test_id = test_def["test_id"]
        start = time.monotonic()

        try:
            parsed, raw_out = await self._dispatch_test(test_id, device_ip, run_id)
            verdict, comment = evaluate_result(test_id, parsed, whitelist_entries)
        except Exception as exc:
            logger.warning("Test %s failed for run %s: %s", test_id, run_id, exc)
            elapsed = time.monotonic() - start
            return ("error", "Test execution failed due to an internal error", None, None, round(elapsed, 2))

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
            # Gather U08 data (service detection)
            u08_data = _PORT_SCAN_CACHE.get(f"{test_run_id}_u08", {})

            # Gather U02 data from the device record (already parsed)
            u02_data = {
                "oui_vendor": device.oui_vendor or "",
                "mac_address": device.mac_address or "",
            }

            async with async_session() as db:
                result = await fingerprinter.fingerprint(
                    db, device.id, u08_data, u02_data
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

    async def _dispatch_test(
        self, test_id: str, device_ip: str, run_id: str
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
                    arp_data = nmap_parser.parse_arp_cache(arp_result.get("stdout", ""))
                    if arp_data.get("mac_address"):
                        parsed["mac_address"] = arp_data["mac_address"]
                except Exception:
                    logger.debug("U02: ARP cache fallback failed for %s", device_ip)
            vendor = await resolve_mac_vendor(parsed.get("mac_address"), parsed.get("oui_vendor"))
            if vendor:
                parsed["oui_vendor"] = vendor
            return (parsed, raw.get("stdout"))

        if test_id == "U03":
            return ({"ethtool_available": False}, None)

        if test_id == "U04":
            try:
                raw = await tools_client.nmap_stream(
                    device_ip, ["-sU", "-p", "67", "--script", "dhcp-discover", "-oX", "-"],
                    timeout=30, on_line=on_line
                )
                parsed = nmap_parser.parse_dhcp_discover(raw.get("stdout", ""))
                return (parsed, raw.get("stdout"))
            except Exception:
                logger.debug("U04: DHCP discover failed for %s", device_ip)
                return ({"dhcp_detected": None}, None)

        if test_id == "U05":
            raw = await tools_client.nmap_stream(device_ip, ["-6", "-sn"], timeout=60, on_line=on_line)
            parsed = nmap_parser.parse_ipv6(raw)
            return (parsed, raw.get("stdout"))

        if test_id == "U06":
            raw = await tools_client.nmap_stream(
                device_ip, ["-sS", "-p-", "-T4", "--min-rate", "500", "--max-retries", "2", "--defeat-rst-ratelimit", "--open", "-oX", "-"], timeout=600, on_line=on_line
            )
            if raw.get("exit_code") not in (None, 0):
                logger.warning("U06 nmap exited %s: %s", raw.get("exit_code"), raw.get("stderr", ""))
            xml_out = raw.get("stdout", "")
            parsed = nmap_parser.parse_xml(xml_out)
            _PORT_SCAN_CACHE[run_id] = parsed
            # Hot-update the cable handler's probe ports with newly discovered ports
            from app.services.wobbly_cable import get_cable_handler
            _handler = get_cable_handler(run_id)
            if _handler and parsed.get("open_ports"):
                _handler.update_probe_ports(extract_probe_ports(parsed["open_ports"]))
            return (parsed, xml_out)

        if test_id == "U07":
            raw = await tools_client.nmap_stream(
                device_ip, ["-sU", "--top-ports", "100", "--open", "-oX", "-"], timeout=300, on_line=on_line
            )
            parsed = nmap_parser.parse_xml(raw.get("stdout", ""))
            return (parsed, raw.get("stdout"))

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
            parsed = nmap_parser.parse_xml(raw.get("stdout", ""))
            # Store U08 data as fallback for U09 when U06 cache is empty
            _PORT_SCAN_CACHE[f"{run_id}_u08"] = parsed
            return (parsed, raw.get("stdout"))

        if test_id == "U09":
            cached = _PORT_SCAN_CACHE.get(run_id)
            if cached and cached.get("open_ports"):
                return (cached, None)
            # Fallback: use U08 service detection data if U06 full scan was empty
            u08_cached = _PORT_SCAN_CACHE.get(f"{run_id}_u08")
            if u08_cached and u08_cached.get("open_ports"):
                logger.info("U09: using U08 service scan data as fallback (U06 cache empty)")
                return (u08_cached, None)
            raw = await tools_client.nmap(
                device_ip, ["-sS", "-p-", "-T4", "--open", "-oX", "-"], timeout=600
            )
            if raw.get("exit_code") not in (None, 0):
                logger.warning("U09 nmap exited %s: %s", raw.get("exit_code"), raw.get("stderr", ""))
            parsed = nmap_parser.parse_xml(raw.get("stdout", ""))
            _PORT_SCAN_CACHE[run_id] = parsed
            return (parsed, raw.get("stdout"))

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
            raw = await tools_client.testssl_stream(target, ["--ip", "one", "--fast"], timeout=300, on_line=on_line)
            output_file = raw.get("output_file", "")
            if output_file:
                parsed = testssl_parser.parse(output_file)
            else:
                parsed = testssl_parser.parse_from_stdout(raw.get("stdout", ""))
            _TESTSSL_CACHE[run_id] = parsed
            return (parsed, raw.get("stdout"))

        if test_id in ("U14", "U35"):
            # Auto-detect HTTP/HTTPS port from scan cache
            nikto_args = []
            port_cache = _PORT_SCAN_CACHE.get(run_id) or _PORT_SCAN_CACHE.get(f"{run_id}_u08") or {}
            open_ports = port_cache.get("open_ports", [])
            http_ports = [p["port"] for p in open_ports if p.get("service") in ("http", "https", "ssl/http", "ssl/https")]
            if http_ports:
                nikto_args.extend(["-p", str(http_ports[0])])
                if any(p.get("service") in ("https", "ssl/http", "ssl/https") for p in open_ports if p["port"] == http_ports[0]):
                    nikto_args.append("-ssl")
            raw = await tools_client.nikto_stream(device_ip, nikto_args, timeout=300, on_line=on_line)
            parsed = {"raw": raw.get("stdout", ""), "stdout": raw.get("stdout", "")}
            return (parsed, raw.get("stdout"))

        if test_id == "U15":
            raw = await tools_client.ssh_audit_stream(device_ip, ["-j"], timeout=120, on_line=on_line)
            parsed = ssh_audit_parser.parse(raw)
            return (parsed, raw.get("stdout"))

        if test_id == "U16":
            raw = await tools_client.hydra_stream(
                device_ip,
                ["-C", "/usr/share/wordlists/common.txt", "-f", device_ip, "http-get"],
                timeout=120,
                on_line=on_line,
            )
            parsed = hydra_parser.parse(raw)
            return (parsed, raw.get("stdout"))

        if test_id == "U17":
            parsed = await self._test_brute_force_protection(device_ip)
            return (parsed, None)

        if test_id == "U18":
            parsed = await self._test_http_redirect(device_ip)
            return (parsed, None)

        if test_id == "U19":
            raw = await tools_client.nmap_stream(device_ip, ["-O", "--osscan-guess", "-oX", "-"], timeout=120, on_line=on_line)
            parsed = nmap_parser.parse_os_fingerprint(raw.get("stdout", ""))
            # Fallback: infer OS from service versions if -O failed
            if not parsed.get("os_fingerprint"):
                svc_cache = _PORT_SCAN_CACHE.get(f"{run_id}_u08") or _PORT_SCAN_CACHE.get(run_id)
                if svc_cache and svc_cache.get("open_ports"):
                    inferred = _infer_os_from_services(svc_cache["open_ports"])
                    if inferred:
                        parsed["os_fingerprint"] = inferred
            return (parsed, raw.get("stdout"))

        if test_id == "U26":
            # NTP runs on UDP 123 — check TCP cache first, then run a quick UDP probe
            cached = _PORT_SCAN_CACHE.get(run_id)
            ntp_open = False
            if cached:
                ntp_open = any(p["port"] == 123 for p in cached.get("open_ports", []))
            if not ntp_open:
                raw = await tools_client.nmap_stream(
                    device_ip, ["-sU", "-p", "123", "--open", "-oX", "-"], timeout=30, on_line=on_line
                )
                udp_parsed = nmap_parser.parse_xml(raw.get("stdout", ""))
                ntp_open = any(p["port"] == 123 for p in udp_parsed.get("open_ports", []))
            return ({"ntp_open": ntp_open}, None)

        if test_id == "U28":
            # BACnet runs on UDP 47808 — check TCP cache first, then run a quick UDP probe
            cached = _PORT_SCAN_CACHE.get(run_id)
            bacnet = False
            if cached:
                bacnet = any(p["port"] == 47808 for p in cached.get("open_ports", []))
            if not bacnet:
                raw = await tools_client.nmap_stream(
                    device_ip, ["-sU", "-p", "47808", "--open", "-oX", "-"], timeout=30, on_line=on_line
                )
                udp_parsed = nmap_parser.parse_xml(raw.get("stdout", ""))
                bacnet = any(p["port"] == 47808 for p in udp_parsed.get("open_ports", []))
            return ({"bacnet_open": bacnet}, None)

        if test_id == "U29":
            cached = _PORT_SCAN_CACHE.get(run_id)
            dns = False
            if cached:
                dns = any(p["port"] == 53 for p in cached.get("open_ports", []))
            if not dns:
                raw = await tools_client.nmap_stream(
                    device_ip, ["-sU", "-p", "53", "--open", "-oX", "-"], timeout=30, on_line=on_line
                )
                udp_parsed = nmap_parser.parse_xml(raw.get("stdout", ""))
                dns = any(p["port"] == 53 for p in udp_parsed.get("open_ports", []))
            return ({"dns_open": dns}, None)

        if test_id == "U31":
            raw = await tools_client.nmap_stream(
                device_ip, ["-sU", "-p", "161,162", "-sV", "--script", "snmp-info", "-oX", "-"], timeout=120, on_line=on_line
            )
            parsed = nmap_parser.parse_xml(raw.get("stdout", ""))
            snmp_ports = [p for p in parsed.get("open_ports", []) if p.get("port") in (161, 162)]
            snmpwalk_output = ""
            if snmp_ports:
                for version in ["2c", "1"]:
                    try:
                        sw_raw = await tools_client.snmpwalk(
                            device_ip,
                            ["-v", version, "-c", "public", "-t", "5", "-r", "0", "-On", device_ip, "1.3.6.1.2.1.1.1.0"],
                            timeout=15,
                        )
                        sw_out = sw_raw.get("stdout", "")
                        if sw_out:
                            snmpwalk_output += f"\n--- snmpwalk v{version} ---\n{sw_out}"
                    except Exception:
                        pass
            combined_stdout = (raw.get("stdout", "") or "") + snmpwalk_output
            parsed["snmpwalk_output"] = snmpwalk_output
            return (parsed, combined_stdout)

        if test_id == "U32":
            raw = await tools_client.nmap_stream(
                device_ip, ["-sU", "-p", "1900", "-sV", "--script", "upnp-info", "-oX", "-"], timeout=120, on_line=on_line
            )
            parsed = nmap_parser.parse_xml(raw.get("stdout", ""))
            return (parsed, raw.get("stdout"))

        if test_id == "U33":
            raw = await tools_client.nmap_stream(
                device_ip, ["-sU", "-p", "5353", "-sV", "-oX", "-"], timeout=120, on_line=on_line
            )
            parsed = nmap_parser.parse_xml(raw.get("stdout", ""))
            return (parsed, raw.get("stdout"))

        if test_id == "U34":
            cached = _PORT_SCAN_CACHE.get(run_id)
            if cached:
                open_ports = {p["port"] for p in cached.get("open_ports", [])}
                telnet_open = 23 in open_ports
                ftp_open = 21 in open_ports
                return ({"telnet_open": telnet_open, "ftp_open": ftp_open, "insecure_ports": sorted(open_ports & {21, 23, 69, 110, 143})}, None)
            raw = await tools_client.nmap(
                device_ip, ["-sS", "-p", "21,23,69,110,143", "--open", "-oX", "-"], timeout=60
            )
            parsed = nmap_parser.parse_xml(raw.get("stdout", ""))
            open_ports = {p["port"] for p in parsed.get("open_ports", [])}
            return ({"telnet_open": 23 in open_ports, "ftp_open": 21 in open_ports, "insecure_ports": sorted(open_ports)}, raw.get("stdout"))

        if test_id == "U36":
            raw = await tools_client.nmap_stream(
                device_ip, ["-sV", "--script", "banner", "--open", "-oX", "-"], timeout=180, on_line=on_line
            )
            parsed = nmap_parser.parse_xml(raw.get("stdout", ""))
            return (parsed, raw.get("stdout"))

        if test_id == "U37":
            parsed = await self._test_rtsp_auth(device_ip)
            return (parsed, None)

        return ({}, None)

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
        except Exception as e:
            logger.debug("Auth type detection failed for %s: %s", device_ip, e)

        lockout_detected = False
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
        }

    async def _test_http_redirect(self, device_ip: str) -> dict[str, Any]:
        """Check if HTTP redirects to HTTPS."""
        import httpx

        redirects_to_https = False
        http_open = False

        try:
            async with httpx.AsyncClient(timeout=10, verify=settings.SSL_VERIFY_DEVICES, follow_redirects=False) as client:
                resp = await client.head(f"http://{device_ip}")
                http_open = True
                location = resp.headers.get("location", "")
                if resp.status_code in (301, 302, 307, 308) and "https" in location.lower():
                    redirects_to_https = True
        except httpx.ConnectError:
            http_open = False
        except Exception as e:
            logger.debug("HTTP redirect check failed for %s: %s", device_ip, e)

        return {"redirects_to_https": redirects_to_https, "http_open": http_open}

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
            errors = sum(1 for r in all_results if r.verdict == TestVerdict.ERROR)
            pending_manual = sum(
                1 for r in all_results
                if r.verdict == TestVerdict.PENDING and r.tier == TestTier.GUIDED_MANUAL
            )

            essential_failed = any(
                r for r in all_results
                if r.verdict == TestVerdict.FAIL and r.is_essential == "yes"
            )

            run = await db.get(TestRun, run_id)
            if run is None:
                return

            run.passed_tests = passed
            run.failed_tests = failed
            run.advisory_tests = advisory
            run.na_tests = na
            run.completed_tests = passed + failed + advisory + na + errors
            run.progress_pct = 100.0 if run.total_tests else 0.0
            metadata = run.run_metadata if isinstance(run.run_metadata, dict) else {}
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
