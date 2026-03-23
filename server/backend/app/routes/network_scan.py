"""Network scan routes — subnet discovery and batch testing."""

import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
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
from app.services.tools_client import tools_client
from app.services.test_library import get_test_by_id
from app.services.test_engine import test_engine

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


class StartBatchRequest(BaseModel):
    scan_id: str
    device_ips: List[str]
    test_ids: Optional[List[str]] = None
    connection_scenario: str = "test_lab"
    template_id: Optional[str] = None


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


def _parse_nmap_host_discovery(stdout: str) -> list[dict]:
    """Parse nmap -sn output for discovered hosts."""
    hosts = []
    lines = stdout.splitlines()
    current_ip = None
    current_mac = None
    current_vendor = None
    current_hostname = None

    for line in lines:
        line = line.strip()
        if "Nmap scan report for" in line:
            if current_ip:
                hosts.append({
                    "ip": current_ip,
                    "mac": current_mac,
                    "vendor": current_vendor,
                    "hostname": current_hostname,
                })
            current_mac = None
            current_vendor = None
            current_hostname = None

            parts = line.replace("Nmap scan report for ", "")
            if "(" in parts and ")" in parts:
                hostname_part = parts.split("(")[0].strip()
                ip_part = parts.split("(")[1].rstrip(")")
                current_ip = ip_part
                current_hostname = hostname_part
            else:
                current_ip = parts.strip()
                current_hostname = None

        elif "MAC Address:" in line:
            mac_part = line.replace("MAC Address: ", "")
            if " " in mac_part:
                current_mac = mac_part.split(" ")[0].strip()
                current_vendor = mac_part.split("(", 1)[1].rstrip(")") if "(" in mac_part else None
            else:
                current_mac = mac_part.strip()

    if current_ip:
        hosts.append({
            "ip": current_ip,
            "mac": current_mac,
            "vendor": current_vendor,
            "hostname": current_hostname,
        })

    return hosts


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
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    if not CIDR_RE.match(data.cidr):
        raise HTTPException(status_code=400, detail="Invalid CIDR format. Expected e.g. 192.168.1.0/24")

    parts = data.cidr.split("/")
    prefix = int(parts[1])
    if prefix < 16 or prefix > 30:
        raise HTTPException(status_code=400, detail="CIDR prefix must be between /16 and /30")

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
        hosts = _parse_nmap_host_discovery(raw.get("stdout", ""))

        scan.devices_found = hosts
        scan.status = NetworkScanStatus.PENDING
        await db.flush()
        await db.refresh(scan)
    except Exception as exc:
        logger.exception("Discovery failed for %s: %s", data.cidr, exc)
        scan.status = NetworkScanStatus.ERROR
        scan.error_message = str(exc)[:500]
        await db.flush()
        await db.refresh(scan)

    return scan


@router.post("/start", response_model=NetworkScanResponse)
async def start_batch_scan(
    data: StartBatchRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
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

    test_ids = data.test_ids or scan.selected_test_ids or (template.test_ids if template else [])

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
    results = []
    for rid in run_ids:
        run_result = await db.execute(select(TestRun).where(TestRun.id == rid))
        run = run_result.scalar_one_or_none()
        if not run:
            continue

        dev_result = await db.execute(select(Device).where(Device.id == run.device_id))
        device = dev_result.scalar_one_or_none()

        results.append({
            "run_id": run.id,
            "device_ip": device.ip_address if device else "unknown",
            "device_id": run.device_id,
            "vendor": device.manufacturer or device.oui_vendor if device else None,
            "hostname": device.hostname if device else None,
            "status": run.status.value if hasattr(run.status, "value") else str(run.status),
            "progress_pct": run.progress_pct,
            "total_tests": run.total_tests,
            "completed_tests": run.completed_tests,
            "passed_tests": run.passed_tests,
            "failed_tests": run.failed_tests,
            "advisory_tests": run.advisory_tests,
            "overall_verdict": run.overall_verdict.value if run.overall_verdict and hasattr(run.overall_verdict, "value") else str(run.overall_verdict) if run.overall_verdict else None,
        })

    return {"scan_id": scan_id, "status": scan.status.value, "results": results}
