"""Network scan routes — subnet discovery and batch testing."""

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.database import get_db
from app.models.network_scan import NetworkScan, NetworkScanStatus
from app.models.device import Device, DeviceStatus, DeviceCategory
from app.models.test_run import TestRun, TestRunStatus
from app.models.test_result import TestResult, TestVerdict, TestTier
from app.models.test_template import TestTemplate
from app.models.user import User
from app.security.auth import get_current_active_user
from app.middleware.rate_limit import check_rate_limit
from app.services.discovery_service import build_device_display_name
from app.services.tools_client import tools_client
from app.services.test_library import get_test_by_id
from app.services.test_engine import test_engine
from app.services.parsers.nmap_parser import nmap_parser
from app.utils.audit import log_action
from app.models.authorized_network import AuthorizedNetwork
from app.models.user import UserRole
from app.routes.authorized_networks import get_active_networks, is_target_authorized, is_ip_authorized

logger = logging.getLogger("edq.routes.network_scan")

router = APIRouter()

CIDR_RE = re.compile(
    r"^(\d{1,3}\.){3}\d{1,3}/\d{1,2}$"
)

_running_scan_tasks: dict[str, asyncio.Task] = {}


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

    class Config:
        from_attributes = True


@router.get("/detect-networks")
async def detect_networks(
    _: User = Depends(get_current_active_user),
):
    """Auto-detect reachable networks from the tools sidecar.

    Returns discovered interfaces, host IP, and scan recommendations.
    Used by the frontend to pre-fill scan targets.
    """
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{tools_client.base_url}/detect-networks",
                headers=tools_client._headers,
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("Network detection failed: %s", exc)
        return {
            "interfaces": [],
            "host_ip": None,
            "in_docker": True,
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
    check_rate_limit(request, max_requests=3, window_seconds=60, action="network_discover")

    if not CIDR_RE.match(data.cidr):
        raise HTTPException(status_code=400, detail="Invalid CIDR format. Expected e.g. 192.168.1.0/24")

    parts = data.cidr.split("/")
    prefix = int(parts[1])
    if prefix < 16 or prefix > 30:
        raise HTTPException(status_code=400, detail="CIDR prefix must be between /16 and /30")

    # Validate against authorized networks — admins auto-authorize
    authorized = await get_active_networks(db)
    if not is_target_authorized(data.cidr, authorized):
        if user.role == UserRole.ADMIN:
            import ipaddress
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

    try:
        raw = await tools_client.nmap(
            data.cidr,
            ["-sn"],
            timeout=120,
        )
        hosts = nmap_parser.parse_host_discovery(raw.get("stdout", ""))

        # Enrich discovered hosts with service/OS info via quick scan
        if hosts:
            discovered_ips = [h["ip"] for h in hosts if h.get("ip")]
            if discovered_ips:
                try:
                    enrich_raw = await tools_client.nmap(
                        " ".join(discovered_ips),
                        ["-sV", "-O", "--top-ports", "20", "-T4", "-oX", "-"],
                        timeout=180,
                    )
                    enrich_xml = enrich_raw.get("stdout", "")
                    if enrich_xml and "<?xml" in enrich_xml:
                        enrich_data = nmap_parser.parse_xml(enrich_xml)
                        # Build IP -> enrichment map
                        enrich_map = {}
                        for ehost in enrich_data.get("hosts", []):
                            eip = ehost.get("ip")
                            if eip:
                                enrich_map[eip] = ehost
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
                                # Try to extract model/firmware from service banners
                                for p in ports:
                                    version = (p.get("version") or "").strip()
                                    service = (p.get("service") or "").strip()
                                    if version and not h.get("model"):
                                        # Common patterns: "EasyIO FW-14", "Axis M1065", etc
                                        h["model"] = version
                                    if service == "http" and version:
                                        h["http_server"] = version
                except Exception:
                    logger.warning("Enrichment scan failed, continuing with basic discovery")

        scan.devices_found = hosts
        scan.status = NetworkScanStatus.PENDING
        await db.flush()
        await db.refresh(scan)
    except Exception:
        logger.exception("Discovery failed for %s", data.cidr)
        scan.status = NetworkScanStatus.ERROR
        scan.error_message = "Discovery scan failed"
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
    check_rate_limit(request, max_requests=3, window_seconds=60, action="network_start")

    # Validate device IPs against authorized networks — admins auto-authorize
    authorized = await get_active_networks(db)
    unauthorized_ips = [ip for ip in data.device_ips if not is_ip_authorized(ip, authorized)]
    if unauthorized_ips:
        if user.role == UserRole.ADMIN:
            import ipaddress
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

    if scan.status == NetworkScanStatus.SCANNING:
        raise HTTPException(status_code=409, detail="Scan is already running")

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
    # Deduplicate while preserving order (guards against double-serialized or manually edited templates)
    seen: set[str] = set()
    test_ids: list[str] = []
    for tid in raw_test_ids:
        if tid not in seen:
            seen.add(tid)
            test_ids.append(tid)

    run_ids = []
    for ip in data.device_ips:
        dev_result = await db.execute(select(Device).where(Device.ip_address == ip))
        device = dev_result.scalar_one_or_none()
        if not device:
            device = Device(
                ip_address=ip,
                status=DeviceStatus.DISCOVERED,
                category=DeviceCategory.UNKNOWN,
            )
            db.add(device)
            await db.flush()

        test_run = TestRun(
            device_id=device.id,
            template_id=template_id,
            engineer_id=user.id,
            connection_scenario=data.connection_scenario or scan.connection_scenario,
            total_tests=len(test_ids),
            status=TestRunStatus.PENDING,
        )
        db.add(test_run)
        await db.flush()

        for tid in test_ids:
            test_def = get_test_by_id(tid)
            if test_def:
                tr = TestResult(
                    test_run_id=test_run.id,
                    test_id=tid,
                    test_name=test_def["name"],
                    tier=TestTier(test_def["tier"]),
                    tool=test_def.get("tool"),
                    verdict=TestVerdict.PENDING,
                    is_essential="yes" if test_def.get("is_essential") else "no",
                    compliance_map=test_def.get("compliance_map", []),
                )
                db.add(tr)

        await db.flush()
        run_ids.append(test_run.id)

    scan.run_ids = run_ids
    scan.status = NetworkScanStatus.SCANNING
    scan.selected_test_ids = test_ids
    await db.flush()
    await db.refresh(scan)

    scan_id = scan.id
    for rid in run_ids:
        task = asyncio.create_task(test_engine.run(rid))
        _running_scan_tasks[rid] = task

    asyncio.create_task(_monitor_batch(scan_id, run_ids))

    await log_action(db, user, "network_scan.start", "network_scan", scan.id,
                     {"device_count": len(data.device_ips), "test_count": len(test_ids)}, request)

    return scan


async def _monitor_batch(scan_id: str, run_ids: list[str]) -> None:
    """Wait for all batch runs to complete, then mark scan complete."""
    from app.models.database import async_session

    tasks = [_running_scan_tasks.get(rid) for rid in run_ids if rid in _running_scan_tasks]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    for rid in run_ids:
        _running_scan_tasks.pop(rid, None)

    async with async_session() as db:
        result = await db.execute(select(NetworkScan).where(NetworkScan.id == scan_id))
        scan = result.scalar_one_or_none()
        if scan and scan.status == NetworkScanStatus.SCANNING:
            scan.status = NetworkScanStatus.COMPLETE
            scan.completed_at = datetime.now(timezone.utc)
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
    _: User = Depends(get_current_active_user),
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
                "raw_output": tr.raw_output,
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
