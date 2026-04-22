"""Network scan routes — subnet discovery and batch testing."""

import asyncio
import ipaddress
import logging
import os
import re
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.models.database import get_db
from app.models.network_scan import NetworkScan, NetworkScanStatus
from app.models.device import Device, DeviceStatus, DeviceCategory
from app.models.test_run import TestRun, TestRunStatus, normalize_test_run_status
from app.models.test_result import TestResult, TestVerdict, TestTier
from app.models.test_template import TestTemplate
from app.models.user import User
from app.security.auth import get_current_active_user
from app.middleware.rate_limit import check_rate_limit
from app.services.discovery_service import build_device_display_name
from app.services.device_ip_discovery import (
    enrich_hosts_with_neighbor_entries,
    get_neighbor_entries,
)
from app.services.connectivity_probe import probe_device_connectivity
from app.services.tools_client import describe_tools_error, tools_client
from app.services.test_library import get_test_by_id
from app.services.scenario_routing import (
    get_manual_routing_note,
    get_scenario_routing_decision,
    normalize_connection_scenario,
)
from app.services.test_run_launcher import launch_test_run
from app.services.parsers.nmap_parser import nmap_parser
from app.utils.audit import log_action
from app.models.authorized_network import AuthorizedNetwork
from app.models.user import UserRole
from app.routes.authorized_networks import get_active_networks, is_target_authorized, is_ip_authorized
from app.utils.collections import ordered_unique
from app.utils.datetime import utcnow_naive

logger = logging.getLogger("edq.routes.network_scan")

router = APIRouter()

# Track background monitor tasks so they aren't garbage-collected mid-flight.
# NOTE: This in-memory task registry is only valid in a single-process backend.
# If the application is deployed with multiple worker processes, each process
# maintains its own _monitor_tasks dict and duplicate or missing monitor
# sequencing can occur. Multi-worker deployments should replace this with a
# shared coordination mechanism (Redis, database locks, external scheduler, etc.).
_monitor_tasks: dict[str, asyncio.Task] = {}
_starting_scan_ids: set[str] = set()


def _parse_bool_env(value: str | None, env_name: str | None = None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in ("1", "true", "yes", "on"):
        return True
    if normalized in ("0", "false", "no", "off"):
        return False

    if value.strip() != "":
        var_name = f" for {env_name}" if env_name else ""
        logger.warning("Unrecognized boolean env value: '%s'%s", value, var_name)
    return None


def _current_process_cmdline() -> list[str]:
    try:
        with open("/proc/self/cmdline", "rb") as fp:
            raw = fp.read().strip(b"\x00")
        return [part.decode(errors="ignore") for part in raw.split(b"\x00") if part]
    except OSError:
        return []


def _current_process_name() -> str | None:
    try:
        with open("/proc/self/comm", "r", encoding="utf-8") as fp:
            return fp.read().strip()
    except OSError:
        return None


def _is_multi_worker_mode() -> bool:
    """Detect whether this process is running in a multi-worker backend.

    Detection order:
    1. Explicit override via EDQ_SINGLE_WORKER_MODE or EDQ_MULTI_WORKERS.
    2. Gunicorn-specific runtime signals such as GUNICORN_ARBITER_PID.
    3. Process inspection of /proc/self/comm and /proc/self/cmdline for "gunicorn".
    4. WEB_CONCURRENCY heuristic as a fallback.
    """
    explicit_single = _parse_bool_env(os.getenv("EDQ_SINGLE_WORKER_MODE"), "EDQ_SINGLE_WORKER_MODE")
    if explicit_single is not None:
        return not explicit_single

    explicit_multi = _parse_bool_env(os.getenv("EDQ_MULTI_WORKERS"), "EDQ_MULTI_WORKERS")
    if explicit_multi is not None:
        return explicit_multi

    if os.getenv("GUNICORN_ARBITER_PID") is not None:
        return True

    process_name = _current_process_name()
    if process_name and "gunicorn" in process_name.lower():
        return True

    cmdline = _current_process_cmdline()
    if any("gunicorn" in part.lower() for part in cmdline):
        return True

    web_concurrency = os.getenv("WEB_CONCURRENCY")
    if web_concurrency:
        try:
            return int(web_concurrency) > 1
        except ValueError:
            pass

    return False


def _reserve_batch_scan_start(scan_id: str) -> bool:
    existing_monitor_task = _monitor_tasks.get(scan_id)
    if existing_monitor_task is not None and not existing_monitor_task.done():
        return False
    if scan_id in _starting_scan_ids:
        return False
    _starting_scan_ids.add(scan_id)
    return True


def _release_batch_scan_start(scan_id: str) -> None:
    _starting_scan_ids.discard(scan_id)

CIDR_RE = re.compile(
    r"^(\d{1,3}\.){3}\d{1,3}/\d{1,2}$"
)

_SETTLED_BATCH_RUN_STATUSES = {
    TestRunStatus.AWAITING_MANUAL.value,
    TestRunStatus.AWAITING_REVIEW.value,
    TestRunStatus.COMPLETED.value,
    TestRunStatus.FAILED.value,
    TestRunStatus.CANCELLED.value,
}


class DiscoverRequest(BaseModel):
    cidr: str = Field(..., max_length=43, description="CIDR range, e.g. 192.168.1.0/24")
    connection_scenario: str = Field("test_lab", max_length=32)
    test_ids: Optional[List[str]] = None


_IP_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")


class StartBatchRequest(BaseModel):
    scan_id: str
    device_ips: List[str]
    test_ids: Optional[List[str]] = None
    connection_scenario: str = "test_lab"
    template_id: Optional[str] = None

    @field_validator("device_ips")
    @classmethod
    def validate_device_ips(cls, v: List[str]) -> List[str]:
        import ipaddress
        for ip in v:
            if not _IP_RE.match(ip):
                raise ValueError(f"Invalid IPv4 address: {ip}")
            try:
                ipaddress.ip_address(ip)
            except ValueError:
                raise ValueError(f"Invalid IPv4 address: {ip}")
        return v


class NetworkScanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    cidr: str
    connection_scenario: str
    selected_test_ids: Optional[list] = None
    status: str
    devices_found: Optional[list] = None
    run_ids: Optional[list] = None
    error_message: Optional[str] = None
    created_by: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    skipped_unreachable: Optional[List[str]] = None


def _batch_runs_are_settled(run_ids: list[str], run_statuses: dict[str, str]) -> bool:
    return len(run_statuses) == len(run_ids) and all(
        status in _SETTLED_BATCH_RUN_STATUSES
        for status in run_statuses.values()
    )

@router.get("/detect-networks")
async def detect_networks(
    _: User = Depends(get_current_active_user),
):
    """Auto-detect reachable networks from the tools sidecar.

    Returns discovered interfaces, host IP, and scan recommendations.
    Used by the frontend to pre-fill scan targets.
    """
    try:
        return await tools_client.detect_networks()
    except Exception as exc:
        logger.warning("Network detection failed: %s", exc)
        return {
            "interfaces": [],
            "host_ip": None,
            "in_docker": tools_client.in_docker,
            "scan_recommendation": None,
            "debug": {"error": str(exc)},
        }


@router.get("/", response_model=List[NetworkScanResponse])
async def list_network_scans(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(NetworkScan).order_by(NetworkScan.created_at.desc()).offset(skip).limit(limit)
    )
    return result.scalars().all()


@router.post("/discover", response_model=NetworkScanResponse)
async def discover_devices(
    data: DiscoverRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    if not CIDR_RE.match(data.cidr):
        raise HTTPException(status_code=400, detail="Invalid CIDR format. Expected e.g. 192.168.1.0/24")
    check_rate_limit(
        request,
        max_requests=settings.DISCOVERY_GLOBAL_RATE_LIMIT_PER_MINUTE,
        window_seconds=60,
        action="network_discover_global",
    )
    check_rate_limit(
        request,
        max_requests=settings.DISCOVERY_RATE_LIMIT_PER_MINUTE,
        window_seconds=60,
        action="network_discover",
        scope=data.cidr,
    )

    try:
        ipaddress.ip_network(data.cidr, strict=False)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid CIDR notation")

    parts = data.cidr.split("/")
    prefix = int(parts[1])
    if prefix < 16 or prefix > 30:
        raise HTTPException(status_code=400, detail="CIDR prefix must be between /16 and /30")

    # Validate against authorized networks — admins auto-authorize
    authorized = await get_active_networks(db)
    if not is_target_authorized(data.cidr, authorized):
        if user.role == UserRole.ADMIN:
            net = ipaddress.ip_network(data.cidr, strict=False)
            new_auth = AuthorizedNetwork(
                cidr=str(net),
                label=f"Auto-authorized ({data.connection_scenario or 'scan'})",
                description=f"Automatically authorized by {user.username} during network scan",
                is_active=True,
                created_by=user.id,
            )
            db.add(new_auth)
            await db.flush()
            logger.info("Auto-authorized network %s for admin %s", data.cidr, user.username)
        else:
            raise HTTPException(
                status_code=403,
                detail=f"Network {data.cidr} is not authorized. Contact your admin to authorize this network.",
            )

    scan = NetworkScan(
        cidr=data.cidr,
        connection_scenario=data.connection_scenario,
        selected_test_ids=data.test_ids,
        status=NetworkScanStatus.DISCOVERING,
        created_by=user.id,
    )
    db.add(scan)
    await db.flush()
    await db.refresh(scan)
    scan_id = scan.id
    # Release SQLite write locks before the potentially long-running discovery scan.
    await db.commit()
    await db.refresh(scan)

    try:
        raw = await tools_client.nmap(
            data.cidr,
            ["-sn", "-PR"],
            timeout=120,
        )
        hosts = nmap_parser.parse_host_discovery(raw.get("stdout", ""))
        neighbor_entries = await get_neighbor_entries(data.cidr)
        hosts = enrich_hosts_with_neighbor_entries(hosts, neighbor_entries)

        # Enrich discovered hosts with service/OS info via quick scan (batched)
        if hosts:
            discovered_ips = [h["ip"] for h in hosts if h.get("ip")]
            if discovered_ips:
                _ENRICH_BATCH_SIZE = 20
                enrich_map = {}
                for batch_start in range(0, len(discovered_ips), _ENRICH_BATCH_SIZE):
                    batch_ips = discovered_ips[batch_start:batch_start + _ENRICH_BATCH_SIZE]
                    try:
                        enrich_raw = await tools_client.nmap(
                            " ".join(batch_ips),
                            ["-sV", "-O", "--top-ports", "20", "-T4", "-oX", "-"],
                            timeout=max(180, len(batch_ips) * 15),
                        )
                        enrich_xml = enrich_raw.get("stdout", "")
                        if enrich_xml and "<?xml" in enrich_xml:
                            enrich_data = nmap_parser.parse_xml(enrich_xml)
                            for ehost in enrich_data.get("hosts", []):
                                eip = ehost.get("ip")
                                if eip:
                                    enrich_map[eip] = ehost
                    except Exception as exc:
                        logger.warning("Enrichment scan failed for batch starting at %d: %s", batch_start, exc)
                        continue

                # Merge enrichment into discovered hosts
                for h in hosts:
                    einfo = enrich_map.get(h.get("ip"))
                    if einfo:
                        # Extract services list
                        ports = einfo.get("ports", [])
                        h["services"] = [
                            f"{p.get('service', '?')}/{p.get('port', '?')}"
                            for p in ports if p.get("state") == "open"
                        ]
                        h["open_ports"] = [
                            {"port": p.get("port"), "service": p.get("service", ""), "version": p.get("version", "")}
                            for p in ports if p.get("state") == "open"
                        ]
                        h["os"] = einfo.get("os")
                        if not h.get("mac") and einfo.get("mac_address"):
                            h["mac"] = einfo["mac_address"]
                        if not h.get("vendor") and einfo.get("oui_vendor"):
                            h["vendor"] = einfo["oui_vendor"]
                        for p in ports:
                            version = (p.get("version") or "").strip()
                            service = (p.get("service") or "").strip()
                            if version and not h.get("model"):
                                h["model"] = version
                            if service == "http" and version:
                                h["http_server"] = version

        scan.devices_found = hosts
        scan.status = NetworkScanStatus.PENDING
        await db.flush()
        await db.refresh(scan)
    except Exception as exc:
        logger.exception("Discovery failed for %s", data.cidr)
        scan.status = NetworkScanStatus.ERROR
        scan.error_message = describe_tools_error(exc, fallback="Discovery scan failed")
        await db.flush()
        await db.refresh(scan)

    await log_action(db, user, "network_scan.discover", "network_scan", scan.id,
                     {"cidr": data.cidr, "status": scan.status.value}, request)

    return scan


@router.post("/start", response_model=NetworkScanResponse)
async def start_batch_scan(
    data: StartBatchRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    check_rate_limit(
        request,
        max_requests=settings.DISCOVERY_GLOBAL_RATE_LIMIT_PER_MINUTE,
        window_seconds=60,
        action="network_scan_start_global",
    )
    check_rate_limit(
        request,
        max_requests=settings.DISCOVERY_RATE_LIMIT_PER_MINUTE,
        window_seconds=60,
        action="network_scan_start",
        scope=data.scan_id,
    )

    if _is_multi_worker_mode():
        raise HTTPException(
            status_code=500,
            detail=(
                "Bulk network scan monitoring requires a single backend worker process. "
                "Multi-worker deployments are not supported with in-memory task tracking."
            ),
        )

    # Validate device IPs against authorized networks — admins auto-authorize
    authorized = await get_active_networks(db)
    unauthorized_ips = [ip for ip in data.device_ips if not is_ip_authorized(ip, authorized)]
    if unauthorized_ips:
        if user.role == UserRole.ADMIN:
            # Auto-authorize each unique /24 subnet containing unauthorized IPs
            auto_subnets: set[str] = set()
            for ip in unauthorized_ips:
                try:
                    net = ipaddress.ip_network(f"{ip}/24", strict=False)
                    auto_subnets.add(str(net))
                except ValueError:
                    pass
            for subnet in auto_subnets:
                existing = await db.execute(
                    select(AuthorizedNetwork).where(AuthorizedNetwork.cidr == subnet)
                )
                if not existing.scalar_one_or_none():
                    db.add(AuthorizedNetwork(
                        cidr=subnet,
                        label="Auto-authorized (batch scan)",
                        description=f"Automatically authorized by {user.username} during batch scan",
                        is_active=True,
                        created_by=user.id,
                    ))
            await db.flush()
            logger.info("Auto-authorized %d subnets for admin %s", len(auto_subnets), user.username)
        else:
            raise HTTPException(
                status_code=403,
                detail=f"IPs not within authorized scan ranges: {', '.join(unauthorized_ips[:5])}. Contact your admin.",
            )

    result = await db.execute(select(NetworkScan).where(NetworkScan.id == data.scan_id))
    scan = result.scalar_one_or_none()
    if not scan:
        raise HTTPException(status_code=404, detail="Network scan not found")

    scan_id = scan.id
    if scan.status == NetworkScanStatus.SCANNING:
        raise HTTPException(status_code=409, detail="Scan is already running")
    if not _reserve_batch_scan_start(scan_id):
        raise HTTPException(
            status_code=409,
            detail=(
                "A batch scan monitor is already active for this scan. "
                "Duplicate start requests are not allowed while the scan is in progress."
            ),
        )

    try:
        template = None
        template_id = data.template_id
        if template_id:
            t_result = await db.execute(select(TestTemplate).where(TestTemplate.id == template_id))
            template = t_result.scalar_one_or_none()
            if not template:
                raise HTTPException(status_code=404, detail="Template not found")
        else:
            t_result = await db.execute(
                select(TestTemplate).where(TestTemplate.is_default == True).limit(1)
            )
            template = t_result.scalar_one_or_none()
            if not template:
                t_result = await db.execute(select(TestTemplate).limit(1))
                template = t_result.scalar_one_or_none()
                if not template:
                    raise HTTPException(status_code=400, detail="No test template available")
            template_id = template.id

        raw_test_ids = data.test_ids or scan.selected_test_ids or (template.test_ids if template else [])
        test_ids = ordered_unique(raw_test_ids)

        # Build IP -> discovery data map for enriching new Device records
        _discovered_map = {}
        if scan.devices_found:
            for dh in scan.devices_found:
                if dh.get("ip"):
                    _discovered_map[dh["ip"]] = dh

        probe_semaphore = asyncio.Semaphore(8)

        async def _probe_one(ip: str) -> tuple[str, bool]:
            async with probe_semaphore:
                reachable, _source = await probe_device_connectivity(ip)
                return (ip, reachable)

        probe_results = await asyncio.gather(
            *(_probe_one(ip) for ip in data.device_ips),
            return_exceptions=True,
        )
        reachable_ips: set[str] = set()
        skipped_unreachable: list[str] = []
        for idx, result in enumerate(probe_results):
            ip = data.device_ips[idx]
            if isinstance(result, tuple) and result[1]:
                reachable_ips.add(result[0])
            elif isinstance(result, BaseException):
                logger.warning(
                    "Batch scan %s probe for %s crashed: %r",
                    scan.id, ip, result,
                )
                skipped_unreachable.append(ip)
            else:
                skipped_unreachable.append(ip)

        if skipped_unreachable:
            logger.info(
                "Batch scan %s skipping %d unreachable IP(s): %s",
                scan.id,
                len(skipped_unreachable),
                skipped_unreachable,
            )

        run_ids = []
        for ip in data.device_ips:
            if ip not in reachable_ips:
                continue
            dev_result = await db.execute(select(Device).where(Device.ip_address == ip))
            device = dev_result.scalar_one_or_none()
            if not device:
                disc = _discovered_map.get(ip, {})
                device = Device(
                    ip_address=ip,
                    mac_address=disc.get("mac"),
                    manufacturer=disc.get("vendor"),
                    hostname=disc.get("hostname"),
                    status=DeviceStatus.DISCOVERED,
                    category=DeviceCategory.UNKNOWN,
                    last_seen_at=utcnow_naive(),
                )
                db.add(device)
                await db.flush()
            else:
                # Update existing device with MAC if discovered
                disc = _discovered_map.get(ip, {})
                if not device.mac_address and disc.get("mac"):
                    device.mac_address = disc["mac"]
                if disc.get("vendor") and not device.manufacturer:
                    device.manufacturer = disc["vendor"]
                if disc.get("hostname") and not device.hostname:
                    device.hostname = disc["hostname"]
                device.last_seen_at = utcnow_naive()
                await db.flush()

            test_run = TestRun(
                device_id=device.id,
                template_id=template_id,
                engineer_id=user.id,
                project_id=device.project_id,
                connection_scenario=normalize_connection_scenario(data.connection_scenario or scan.connection_scenario),
                total_tests=len(test_ids),
                status=TestRunStatus.PENDING,
            )
            db.add(test_run)
            await db.flush()

            for tid in test_ids:
                test_def = get_test_by_id(tid)
                if test_def:
                    decision = get_scenario_routing_decision(
                        tid,
                        test_def["tier"],
                        test_run.connection_scenario,
                    )
                    tr = TestResult(
                        test_run_id=test_run.id,
                        test_id=tid,
                        test_name=test_def["name"],
                        tier=TestTier(decision.tier),
                        tool=test_def.get("tool"),
                        verdict=TestVerdict.PENDING,
                        is_essential="yes" if test_def.get("is_essential") else "no",
                        compliance_map=test_def.get("compliance_map", []),
                    )
                    manual_note = get_manual_routing_note(tid, test_run.connection_scenario)
                    if manual_note:
                        tr.comment = manual_note
                    db.add(tr)

            await db.flush()
            run_ids.append(test_run.id)

        scan.run_ids = run_ids
        scan.status = NetworkScanStatus.SCANNING
        scan.selected_test_ids = test_ids
        await db.flush()
        await db.refresh(scan)
        # Persist the batch before launching background tasks so SQLite does not
        # hold an open writer transaction across asynchronous test execution.
        await db.commit()
        await db.refresh(scan)

        launched_tasks: list[asyncio.Task] = []
        for rid in run_ids:
            task = launch_test_run(rid)
            if task is None:
                logger.warning(
                    "Batch scan %s could not launch run %s because it is already executing",
                    scan_id,
                    rid,
                )
                continue
            launched_tasks.append(task)

        def _on_monitor_done(task: asyncio.Task, *, _scan_id: str = scan_id) -> None:
            _monitor_tasks.pop(_scan_id, None)
            if task.cancelled():
                return
            exc = task.exception()
            if exc:
                logger.error("Batch monitor for scan %s failed: %s", _scan_id, exc)

        monitor_task = asyncio.create_task(_monitor_batch(scan_id, run_ids, launched_tasks))
        monitor_task.add_done_callback(_on_monitor_done)
        _monitor_tasks[scan_id] = monitor_task

        await log_action(db, user, "network_scan.start", "network_scan", scan.id,
                         {"device_count": len(data.device_ips), "test_count": len(test_ids)}, request)

        response = NetworkScanResponse.model_validate(scan).model_dump()
        response["skipped_unreachable"] = skipped_unreachable
        return response
    finally:
        _release_batch_scan_start(scan_id)


async def _monitor_batch(
    scan_id: str,
    run_ids: list[str],
    launched_tasks: list[asyncio.Task] | None = None,
) -> None:
    """Wait for all batch runs to settle, then update the aggregate scan status."""
    from app.models.database import async_session

    if launched_tasks:
        await asyncio.gather(*launched_tasks, return_exceptions=True)

    async with async_session() as db:
        result = await db.execute(select(NetworkScan).where(NetworkScan.id == scan_id))
        scan = result.scalar_one_or_none()
        if scan and scan.status == NetworkScanStatus.SCANNING:
            run_status_result = await db.execute(
                select(TestRun.id, TestRun.status).where(TestRun.id.in_(run_ids))
            )
            run_statuses = {
                row.id: normalize_test_run_status(row.status)
                for row in run_status_result.all()
            }
            if run_statuses and _batch_runs_are_settled(run_ids, run_statuses):
                scan.status = NetworkScanStatus.COMPLETE
                scan.completed_at = utcnow_naive()
            else:
                scan.status = NetworkScanStatus.PENDING
                scan.completed_at = None
            await db.commit()


@router.get("/{scan_id}", response_model=NetworkScanResponse)
async def get_network_scan(
    scan_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    result = await db.execute(select(NetworkScan).where(NetworkScan.id == scan_id))
    scan = result.scalar_one_or_none()
    if not scan:
        raise HTTPException(status_code=404, detail="Network scan not found")
    return scan


@router.get("/{scan_id}/results")
async def get_scan_results(
    scan_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    result = await db.execute(select(NetworkScan).where(NetworkScan.id == scan_id))
    scan = result.scalar_one_or_none()
    if not scan:
        raise HTTPException(status_code=404, detail="Network scan not found")

    run_ids = scan.run_ids or []
    if not run_ids:
        return {"scan_id": scan_id, "status": scan.status.value, "results": []}

    # Batch-load all test runs, devices, and test results in three queries instead of N+1
    runs_result = await db.execute(select(TestRun).where(TestRun.id.in_(run_ids)))
    runs = {r.id: r for r in runs_result.scalars().all()}

    device_ids = [r.device_id for r in runs.values() if r.device_id]
    devices_map: dict = {}
    if device_ids:
        devs_result = await db.execute(select(Device).where(Device.id.in_(device_ids)))
        devices_map = {d.id: d for d in devs_result.scalars().all()}

    # Batch-load all test results for all runs
    test_results_result = await db.execute(
        select(TestResult).where(TestResult.test_run_id.in_(list(runs.keys())))
    )
    all_test_results = test_results_result.scalars().all()
    # Group by test_run_id
    results_by_run: dict = {}
    for tr in all_test_results:
        results_by_run.setdefault(tr.test_run_id, []).append(tr)

    results = []
    for rid in run_ids:
        run = runs.get(rid)
        if not run:
            continue
        device = devices_map.get(run.device_id)

        # Build per-test detail list
        run_test_results = results_by_run.get(rid, [])
        test_details = []
        for tr in run_test_results:
            test_details.append({
                "test_id": tr.test_id,
                "test_name": tr.test_name,
                "verdict": tr.verdict.value if hasattr(tr.verdict, "value") else str(tr.verdict),
                "tool": tr.tool,
                "duration_seconds": tr.duration_seconds,
                "is_essential": tr.is_essential,
                "tier": tr.tier.value if hasattr(tr.tier, "value") else str(tr.tier),
                "comment": tr.comment,
                "raw_output": tr.raw_output if user.role == UserRole.ADMIN else None,
                "started_at": tr.started_at.isoformat() if tr.started_at else None,
                "completed_at": tr.completed_at.isoformat() if tr.completed_at else None,
            })
        # Sort by test_id for consistent ordering
        test_details.sort(key=lambda t: t["test_id"])

        results.append({
            "run_id": run.id,
            "device_ip": device.ip_address if device else "unknown",
            "device_id": run.device_id,
            "device_name": build_device_display_name(
                device.ip_address if device else None,
                device.hostname if device else None,
                device.manufacturer if device else None,
                device.model if device else None,
            ) if device else None,
            "device_category": device.category.value if device and device.category and hasattr(device.category, "value") else str(device.category) if device and device.category else None,
            "vendor": device.manufacturer or device.oui_vendor if device else None,
            "hostname": device.hostname if device else None,
            "model": device.model if device else None,
            "status": run.status.value if hasattr(run.status, "value") else str(run.status),
            "progress_pct": run.progress_pct,
            "total_tests": run.total_tests,
            "completed_tests": run.completed_tests,
            "passed_tests": run.passed_tests,
            "failed_tests": run.failed_tests,
            "advisory_tests": run.advisory_tests,
            "overall_verdict": run.overall_verdict.value if run.overall_verdict and hasattr(run.overall_verdict, "value") else str(run.overall_verdict) if run.overall_verdict else None,
            "test_details": test_details,
        })

    return {"scan_id": scan_id, "status": scan.status.value, "results": results}
