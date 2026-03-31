"""Test Execution Engine — orchestrates all tests for a run.

Sequences automatic tool-based tests and creates pending stubs for manual tests.
Streams progress via WebSocket and integrates the Wobbly Cable Handler.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import async_session
from app.models.test_run import TestRun, TestRunStatus
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
from app.services.wobbly_cable import WobblyCableHandler
from app.services.test_library import get_test_by_id
from app.services.device_fingerprinter import fingerprinter, FingerprintResult
from app.routes.websocket_routes import manager

logger = logging.getLogger("edq.test_engine")

_PORT_SCAN_CACHE: dict[str, dict[str, Any]] = {}
_TESTSSL_CACHE: dict[str, dict[str, Any]] = {}


class TestEngine:
    """Orchestrates the full test execution lifecycle for a test run."""

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
        except Exception:
            pass

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

            template = await self._load_template(db, run.template_id)
            if template is None:
                logger.error("Template %s not found for run %s", run.template_id, test_run_id)
                await self._set_run_error(db, run, "Template not found")
                return

            whitelist_entries = await self._load_whitelist(db, template.whitelist_id)

            run.status = TestRunStatus.RUNNING
            run.started_at = datetime.now(timezone.utc)
            existing_meta = run.run_metadata or {}
            if isinstance(existing_meta, dict):
                existing_meta["tool_versions"] = tool_versions
            run.run_metadata = existing_meta
            await db.commit()

        await manager.broadcast(f"test-run:{test_run_id}", {
            "type": "run_started",
            "data": {"run_id": test_run_id, "status": "running"},
        })

        cable_handler = WobblyCableHandler(device.ip_address, test_run_id, manager)
        cable_task = asyncio.create_task(cable_handler.monitor())

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
                        skip_test_ids = set(fingerprint_result.skip_test_ids)
                        skip_reasons = dict(fingerprint_result.skip_reasons)
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
                            result_row.completed_at = datetime.now(timezone.utc)
                            await db.commit()

                    completed += 1
                    await manager.broadcast(f"test-run:{test_run_id}", {
                        "type": "test_complete",
                        "data": {
                            "test_id": test_result.test_id,
                            "test_name": test_result.test_name,
                            "verdict": "na",
                            "comment": reason,
                            "progress_pct": round(((i + 1) / total) * 100, 1) if total else 0,
                        },
                    })

                    async with async_session() as db:
                        run_row = await db.get(TestRun, test_run_id)
                        if run_row:
                            run_row.completed_tests = completed
                            run_row.progress_pct = round(((i + 1) / total) * 100, 1) if total else 0
                            await db.commit()
                    continue

                await self._wait_while_paused(test_run_id)

                effective_tier = test_def["tier"]
                if plan_configs:
                    cfg = plan_configs.get(test_result.test_id)
                    if cfg and cfg.get("tier_override"):
                        effective_tier = cfg["tier_override"]

                await manager.broadcast(f"test-run:{test_run_id}", {
                    "type": "test_start",
                    "data": {
                        "test_id": test_result.test_id,
                        "test_name": test_result.test_name,
                        "progress_pct": round((i / total) * 100, 1) if total else 0,
                    },
                })

                if effective_tier == "guided_manual":
                    async with async_session() as db:
                        result_row = await db.get(TestResult, test_result.id)
                        if result_row and result_row.verdict == TestVerdict.PENDING:
                            result_row.comment = "Awaiting engineer input"
                            await db.commit()

                    await manager.broadcast(f"test-run:{test_run_id}", {
                        "type": "test_complete",
                        "data": {
                            "test_id": test_result.test_id,
                            "test_name": test_result.test_name,
                            "verdict": "pending",
                            "tier": "guided_manual",
                            "progress_pct": round(((i + 1) / total) * 100, 1) if total else 0,
                        },
                    })
                    continue

                verdict, comment, parsed, raw_out, duration = await self._run_single_test(
                    test_def, device.ip_address, test_run_id, whitelist_entries
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
                        result_row.started_at = datetime.now(timezone.utc)
                        result_row.completed_at = datetime.now(timezone.utc)

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
                        "verdict": verdict,
                        "comment": comment,
                        "progress_pct": round(((i + 1) / total) * 100, 1) if total else 0,
                    },
                })

                async with async_session() as db:
                    run_row = await db.get(TestRun, test_run_id)
                    if run_row:
                        run_row.completed_tests = completed
                        run_row.progress_pct = round(((i + 1) / total) * 100, 1) if total else 0
                        await db.commit()

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
                await self._set_run_error(db, await db.get(TestRun, test_run_id), str(exc))
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
            for p in ports:
                service = (p.get("service") or "").lower()
                version = (p.get("version") or "").strip()
                product = (p.get("product") or "").strip()

                # Use HTTP server header as model hint
                if service in ("http", "https") and version and not device_row.model:
                    device_row.model = version
                    changed = True

                # Extract firmware from version strings (e.g. "EasyIO FW-14 v2.3")
                if version and not device_row.firmware_version:
                    import re
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
                "data": {"test_number": test_id, "stdout_line": line},
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
            # Fallback: if nmap couldn't see the MAC (Docker network hop), try ARP table
            if not parsed.get("mac_address"):
                try:
                    arp_raw = await tools_client._post(
                        "/scan/nmap",
                        {"target": device_ip, "args": ["-sn", "--send-ip"], "timeout": 30},
                        timeout=40,
                    )
                    arp_parsed = nmap_parser.parse_xml(arp_raw.get("stdout", ""))
                    if arp_parsed.get("mac_address"):
                        parsed["mac_address"] = arp_parsed["mac_address"]
                        parsed["oui_vendor"] = arp_parsed.get("oui_vendor", "")
                except Exception:
                    logger.debug("U02: ARP fallback failed for %s", device_ip)
            return (parsed, raw.get("stdout"))

        if test_id == "U03":
            return ({"ethtool_available": False}, None)

        if test_id == "U04":
            return ({"dhcp_enabled": None}, None)

        if test_id == "U05":
            raw = await tools_client.nmap_stream(device_ip, ["-6", "-sn"], timeout=60, on_line=on_line)
            parsed = nmap_parser.parse_ipv6(raw)
            return (parsed, raw.get("stdout"))

        if test_id == "U06":
            raw = await tools_client.nmap_stream(
                device_ip, ["-sS", "-p-", "-T4", "--open", "-oX", "-"], timeout=600, on_line=on_line
            )
            if raw.get("exit_code") not in (None, 0):
                logger.warning("U06 nmap exited %s: %s", raw.get("exit_code"), raw.get("stderr", ""))
            xml_out = raw.get("stdout", "")
            parsed = nmap_parser.parse_xml(xml_out)
            _PORT_SCAN_CACHE[run_id] = parsed
            return (parsed, xml_out)

        if test_id == "U07":
            raw = await tools_client.nmap_stream(
                device_ip, ["-sU", "--top-ports", "100", "--open", "-oX", "-"], timeout=300, on_line=on_line
            )
            parsed = nmap_parser.parse_xml(raw.get("stdout", ""))
            return (parsed, raw.get("stdout"))

        if test_id == "U08":
            raw = await tools_client.nmap_stream(
                device_ip, ["-sV", "--open", "-oX", "-"], timeout=300, on_line=on_line
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
            raw = await tools_client.testssl_stream(device_ip, [], timeout=300, on_line=on_line)
            output_file = raw.get("output_file", "")
            if output_file:
                parsed = testssl_parser.parse(output_file)
            else:
                parsed = testssl_parser.parse_from_stdout(raw.get("stdout", ""))
            _TESTSSL_CACHE[run_id] = parsed
            return (parsed, raw.get("stdout"))

        if test_id == "U14":
            raw = await tools_client.nikto_stream(device_ip, ["-host", device_ip], timeout=300, on_line=on_line)
            parsed = {"raw": raw.get("stdout", ""), "stdout": raw.get("stdout", "")}
            return (parsed, raw.get("stdout"))

        if test_id == "U15":
            raw = await tools_client.ssh_audit_stream(device_ip, [], timeout=120, on_line=on_line)
            parsed = ssh_audit_parser.parse(raw)
            return (parsed, raw.get("stdout"))

        if test_id == "U16":
            raw = await tools_client.hydra_stream(
                device_ip,
                ["-l", "admin", "-P", "/usr/share/wordlists/common.txt", device_ip, "http-get"],
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
            raw = await tools_client.nmap_stream(device_ip, ["-O", "-oX", "-"], timeout=120, on_line=on_line)
            parsed = nmap_parser.parse_os_fingerprint(raw.get("stdout", ""))
            return (parsed, raw.get("stdout"))

        if test_id == "U26":
            cached = _PORT_SCAN_CACHE.get(run_id)
            if cached:
                ntp_open = any(p["port"] == 123 for p in cached.get("open_ports", []))
                return ({"ntp_open": ntp_open}, None)
            return ({"ntp_open": False}, None)

        if test_id == "U28":
            cached = _PORT_SCAN_CACHE.get(run_id)
            if cached:
                bacnet = any(p["port"] == 47808 for p in cached.get("open_ports", []))
                return ({"bacnet_open": bacnet}, None)
            return ({"bacnet_open": False}, None)

        if test_id == "U29":
            cached = _PORT_SCAN_CACHE.get(run_id)
            if cached:
                dns = any(p["port"] == 53 for p in cached.get("open_ports", []))
                return ({"dns_open": dns}, None)
            return ({"dns_open": False}, None)

        if test_id == "U31":
            raw = await tools_client.nmap_stream(
                device_ip, ["-sU", "-p", "161,162", "-sV", "--script", "snmp-info", "-oX", "-"], timeout=120, on_line=on_line
            )
            parsed = nmap_parser.parse_xml(raw.get("stdout", ""))
            return (parsed, raw.get("stdout"))

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

        if test_id == "U35":
            raw = await tools_client.nikto_stream(device_ip, ["-host", device_ip], timeout=300, on_line=on_line)
            parsed = {"raw": raw.get("stdout", ""), "stdout": raw.get("stdout", "")}
            return (parsed, raw.get("stdout"))

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
        then runs Hydra with the appropriate module.
        """
        import httpx

        auth_type = "http-get"
        form_path = "/"
        form_fields = ""

        # Detect auth type by checking for a login form
        try:
            async with httpx.AsyncClient(timeout=10, verify=False, follow_redirects=True) as client:
                resp = await client.get(f"http://{device_ip}/")
                body = resp.text.lower()
                # Look for common login form patterns
                if "<form" in body and ("password" in body or "passwd" in body or "login" in body):
                    auth_type = "http-post-form"
                    # Try common login paths
                    for path in ["/login", "/auth", "/user/login", "/api/login", "/"]:
                        try:
                            r = await client.get(f"http://{device_ip}{path}")
                            if "<form" in r.text.lower() and "password" in r.text.lower():
                                form_path = path
                                break
                        except Exception:
                            continue
                    form_fields = f"{form_path}:username=^USER^&password=^PASS^:F=incorrect:H=Content-Type: application/x-www-form-urlencoded"
                elif resp.status_code == 401:
                    auth_type = "http-get"
        except Exception:
            pass

        lockout_detected = False
        error_msg = ""
        try:
            if auth_type == "http-post-form":
                args = [
                    "-l", "admin",
                    "-p", "wrongpassword",
                    "-t", "16",
                    "-f",
                    device_ip,
                    "http-post-form",
                ]
                # Hydra http-post-form needs the form spec as the last positional arg
                # Format: /path:user=^USER^&pass=^PASS^:F=failure_string
                if form_fields:
                    args[-1] = "http-post-form"
                    args.append(form_fields)
            else:
                args = [
                    "-l", "admin",
                    "-p", "wrongpassword",
                    "-t", "16",
                    "-f",
                    device_ip,
                    "http-get",
                ]

            raw = await tools_client.hydra(device_ip, args, timeout=60)
            stdout = raw.get("stdout", "")
            exit_code = raw.get("exit_code", 1)

            if "blocked" in stdout.lower() or "locked" in stdout.lower():
                lockout_detected = True
            elif exit_code != 0 and ("connection refused" in stdout.lower() or "timeout" in stdout.lower()):
                lockout_detected = True

            error_msg = stdout
        except Exception as exc:
            error_msg = str(exc)
            if "refused" in error_msg.lower() or "timeout" in error_msg.lower():
                lockout_detected = True

        return {"lockout_detected": lockout_detected, "auth_type": auth_type, "error": error_msg}

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
        except Exception:
            pass

        return {"redirects_to_https": redirects_to_https, "http_open": http_open}

    async def _test_rtsp_auth(self, device_ip: str) -> dict[str, Any]:
        """Check if RTSP streams require authentication using raw TCP."""
        rtsp_open = False
        auth_required = False

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

            writer.close()
            await writer.wait_closed()
        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            rtsp_open = False
        except Exception:
            pass

        return {"rtsp_open": rtsp_open, "auth_required": auth_required}

    async def _wait_while_paused(self, run_id: str) -> None:
        """Block while the test run is paused (e.g. by wobbly cable)."""
        while True:
            async with async_session() as db:
                run = await db.get(TestRun, run_id)
                if run is None or run.status != TestRunStatus.PAUSED:
                    return
            await asyncio.sleep(2)

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

            if pending_manual > 0:
                run.status = TestRunStatus.AWAITING_MANUAL
                run.overall_verdict = None
            else:
                run.status = TestRunStatus.COMPLETED
                run.completed_at = datetime.now(timezone.utc)
                if essential_failed:
                    run.overall_verdict = "fail"
                elif failed > 0:
                    run.overall_verdict = "fail"
                elif advisory > 0:
                    run.overall_verdict = "qualified_pass"
                else:
                    run.overall_verdict = "pass"

            run.progress_pct = 100.0
            await db.commit()

        await manager.broadcast(f"test-run:{run_id}", {
            "type": "run_complete",
            "data": {
                "run_id": run_id,
                "status": run.status.value if hasattr(run.status, "value") else str(run.status),
                "overall_verdict": run.overall_verdict,
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
            run.overall_verdict or "awaiting_manual",
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
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()

        await manager.broadcast(f"test-run:{run.id if run else 'unknown'}", {
            "type": "run_error",
            "data": {"message": message},
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
            select(TestRun).where(TestRun.status == TestRunStatus.RUNNING)
        )
        orphans = result.scalars().all()
        for run in orphans:
            run.status = TestRunStatus.FAILED
            run.completed_at = datetime.now(timezone.utc)
            run.synopsis = (
                (run.synopsis or "")
                + "\n[Auto-reset: server restarted during execution]"
            ).lstrip("\n")
        if orphans:
            await db.commit()
            logger.info("Reset %d orphaned running test run(s) to failed", len(orphans))
