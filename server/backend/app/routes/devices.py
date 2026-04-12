"""Device management routes."""

import csv
import io
import ipaddress
import logging
import re
import xml.etree.ElementTree as ET
from datetime import timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, case
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, Field

from app.models.database import get_db
from app.models.device import Device
from app.models.project import Project
from app.models.user import User
from app.models.test_run import TestRun, TestRunStatus
from app.models.test_result import TestResult, TestVerdict
from app.schemas.device import DeviceCreate, DeviceUpdate, DeviceResponse
from app.security.auth import get_current_active_user, require_role
from app.utils.sanitize import sanitize_dict, strip_html
from app.utils.audit import log_action
from app.utils.datetime import as_utc
from app.services.parsers.nmap_parser import nmap_parser
from app.services.tools_client import describe_tools_error, get_tools_error_status, tools_client
from app.middleware.rate_limit import check_rate_limit
from app.routes.authorized_networks import get_active_networks

logger = logging.getLogger("edq.routes.devices")

router = APIRouter()

_DEFAULT_DHCP_SCAN_SUBNETS = (
    "192.168.1.0/24",
    "192.168.0.0/24",
    "10.0.0.0/24",
    "172.16.0.0/24",
)


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


def _build_discovery_scan_ranges(authorized_cidrs: list[str], detection: dict | None) -> list[str]:
    candidates: list[str] = []
    detection = detection or {}
    host_ip = detection.get("host_ip")
    interfaces = detection.get("interfaces") or []

    sample_hosts: list[str] = []
    for interface in interfaces:
        for host in interface.get("sample_hosts") or []:
            if isinstance(host, str):
                sample_hosts.append(host)

    if isinstance(host_ip, str):
        sample_hosts.append(host_ip)

    for interface in interfaces:
        cidr = interface.get("cidr")
        if not isinstance(cidr, str):
            continue
        try:
            network = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            continue
        if network.prefixlen >= 24 or network.network_address.is_link_local:
            _append_scan_cidr(candidates, str(network))
        for host in interface.get("sample_hosts") or []:
            if isinstance(host, str):
                _append_anchor_subnet(candidates, host)

    for cidr in authorized_cidrs:
        try:
            network = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            continue
        if network.prefixlen >= 24 or network.network_address.is_link_local:
            _append_scan_cidr(candidates, str(network))
            continue
        anchored = False
        for host in sample_hosts:
            try:
                host_ip_addr = ipaddress.ip_address(host)
            except ValueError:
                continue
            if host_ip_addr in network:
                _append_anchor_subnet(candidates, host)
                anchored = True
        if not anchored and isinstance(host_ip, str):
            try:
                host_addr = ipaddress.ip_address(host_ip)
            except ValueError:
                host_addr = None
            if host_addr and host_addr in network:
                _append_anchor_subnet(candidates, host_ip)

    if not candidates:
        for subnet in _DEFAULT_DHCP_SCAN_SUBNETS:
            _append_scan_cidr(candidates, subnet)

    return candidates


@router.get("/", response_model=List[DeviceResponse])
async def list_devices(
    category: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = Query(None, max_length=200),
    project_id: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    query = select(Device)
    if category:
        query = query.where(Device.category == category)
    if status:
        query = query.where(Device.status == status)
    if project_id:
        query = query.where(Device.project_id == project_id)
    if search:
        term = f"%{search}%"
        query = query.where(
            or_(
                Device.ip_address.ilike(term),
                Device.mac_address.ilike(term),
                Device.hostname.ilike(term),
                Device.manufacturer.ilike(term),
                Device.model.ilike(term),
            )
        )
    query = query.order_by(Device.updated_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/stats")
async def device_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """Get device statistics for the dashboard."""
    total = await db.execute(select(func.count(Device.id)))
    by_status = await db.execute(
        select(Device.status, func.count(Device.id)).group_by(Device.status)
    )
    by_category = await db.execute(
        select(Device.category, func.count(Device.id)).group_by(Device.category)
    )
    return {
        "total": total.scalar() or 0,
        "by_status": {row[0]: row[1] for row in by_status.all()},
        "by_category": {row[0]: row[1] for row in by_category.all()},
    }


@router.get("/compare")
async def compare_devices(
    ids: str = Query(..., description="Comma-separated device IDs (2-5)"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """Compare up to 5 devices side by side with test summaries and port analysis."""
    device_ids = [did.strip() for did in ids.split(",") if did.strip()]
    if len(device_ids) < 2:
        raise HTTPException(status_code=400, detail="At least 2 device IDs are required")
    if len(device_ids) > 5:
        raise HTTPException(status_code=400, detail="At most 5 devices can be compared")

    # Fetch all requested devices
    result = await db.execute(select(Device).where(Device.id.in_(device_ids)))
    devices = result.scalars().all()
    devices_by_id = {d.id: d for d in devices}

    missing = set(device_ids) - set(devices_by_id.keys())
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Devices not found: {', '.join(sorted(missing))}",
        )

    # For each device, get the latest completed TestRun.
    # Subquery: max created_at per device among completed runs.
    latest_ts_subq = (
        select(
            TestRun.device_id,
            func.max(TestRun.created_at).label("max_created"),
        )
        .where(
            TestRun.device_id.in_(device_ids),
            TestRun.status == TestRunStatus.COMPLETED,
        )
        .group_by(TestRun.device_id)
        .subquery()
    )
    runs_query = (
        select(TestRun)
        .join(
            latest_ts_subq,
            (TestRun.device_id == latest_ts_subq.c.device_id)
            & (TestRun.created_at == latest_ts_subq.c.max_created),
        )
        .where(TestRun.status == TestRunStatus.COMPLETED)
    )
    runs_result = await db.execute(runs_query)
    latest_runs = {r.device_id: r for r in runs_result.scalars().all()}

    # Build per-device response
    verdict_severity = {"pass": 0, "qualified_pass": 1, "advisory": 2, "incomplete": 3, "fail": 4}
    device_entries = []
    all_port_sets: dict[str, set[int]] = {}
    verdicts: list[str] = []

    for did in device_ids:
        device = devices_by_id[did]
        run = latest_runs.get(did)

        # Extract port numbers from open_ports JSON (list of dicts with "port" key, or list of ints)
        port_numbers: list[int] = []
        if device.open_ports:
            for entry in device.open_ports:
                if isinstance(entry, dict) and "port" in entry:
                    port_numbers.append(int(entry["port"]))
                elif isinstance(entry, (int, float)):
                    port_numbers.append(int(entry))
        all_port_sets[did] = set(port_numbers)

        # Determine last verdict from the latest run
        last_verdict = None
        if run and run.overall_verdict:
            last_verdict = run.overall_verdict.value
            verdicts.append(last_verdict)

        # Build test summary from the run's precomputed counters
        test_summary = None
        if run:
            test_summary = {
                "total": run.total_tests or 0,
                "passed": run.passed_tests or 0,
                "failed": run.failed_tests or 0,
                "advisory": run.advisory_tests or 0,
            }

        category_val = device.category.value if device.category else None

        device_entries.append({
            "id": device.id,
            "name": device.hostname,
            "ip_address": device.ip_address,
            "manufacturer": device.manufacturer,
            "model": device.model,
            "category": category_val,
            "open_ports": port_numbers,
            "os_fingerprint": device.os_fingerprint,
            "last_verdict": last_verdict,
            "test_summary": test_summary,
        })

    # Compute comparison fields
    if all_port_sets:
        port_sets_list = list(all_port_sets.values())
        common_open_ports = sorted(set.intersection(*port_sets_list)) if port_sets_list else []
    else:
        common_open_ports = []

    common_set = set(common_open_ports)
    unique_ports = {
        did: sorted(ports - common_set)
        for did, ports in all_port_sets.items()
        if ports - common_set
    }

    all_pass = bool(verdicts) and all(v == "pass" for v in verdicts)
    worst_verdict = None
    if verdicts:
        worst_verdict = max(verdicts, key=lambda v: verdict_severity.get(v, -1))

    return {
        "devices": device_entries,
        "comparison": {
            "common_open_ports": common_open_ports,
            "unique_ports": unique_ports,
            "all_pass": all_pass,
            "worst_verdict": worst_verdict,
        },
    }


@router.post("/", response_model=DeviceResponse, status_code=201)
async def create_device(
    data: DeviceCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    is_dhcp = data.addressing_mode == "dhcp"
    project_id = await _validate_project_id(db, data.project_id)

    # Validate profile_id exists if provided
    if data.profile_id:
        from app.models.device_profile import DeviceProfile
        profile_check = await db.execute(select(DeviceProfile.id).where(DeviceProfile.id == data.profile_id))
        if profile_check.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Device profile not found")

    # DHCP devices require a MAC address instead of IP
    if is_dhcp:
        if not data.mac_address:
            raise HTTPException(
                status_code=422,
                detail="MAC address is required for DHCP devices",
            )
        # Check for duplicate MAC address
        existing_mac = await db.execute(
            select(Device).where(Device.mac_address == data.mac_address)
        )
        if existing_mac.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail=f"A device with MAC address {data.mac_address} already exists",
            )
    else:
        # Static devices require an IP address
        if not data.ip_address:
            raise HTTPException(
                status_code=422,
                detail="IP address is required for static devices",
            )
        # Check for duplicate IP address
        existing = await db.execute(
            select(Device).where(Device.ip_address == data.ip_address)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail=f"A device with IP address {data.ip_address} already exists",
            )

    clean = sanitize_dict(
        data.model_dump(exclude_none=True),
        [
            "hostname",
            "manufacturer",
            "model",
            "firmware_version",
            "serial_number",
            "location",
            "notes",
        ],
    )
    allowed_fields = {
        "ip_address",
        "mac_address",
        "addressing_mode",
        "hostname",
        "manufacturer",
        "model",
        "firmware_version",
        "serial_number",
        "category",
        "location",
        "notes",
        "profile_id",
    }
    payload = {field: clean[field] for field in allowed_fields if field in clean}
    if project_id is not None:
        payload["project_id"] = project_id

    device = Device(**payload)
    db.add(device)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A device with this IP or MAC address already exists")
    await db.refresh(device)
    await log_action(db, user, "create", "device", device.id, {"ip": device.ip_address, "mac": device.mac_address, "addressing_mode": data.addressing_mode}, request)
    return device


# ---------------------------------------------------------------------------
# Bulk CSV import
# ---------------------------------------------------------------------------

_MAX_IMPORT_ROWS = 500

_MAC_RE_IMPORT = re.compile(r"^([0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}$")

_VALID_CATEGORIES = {
    "camera", "controller", "intercom", "access_panel",
    "lighting", "hvac", "iot_sensor", "meter", "unknown",
}


async def _validate_project_id(
    db: AsyncSession,
    project_id: Optional[str],
) -> Optional[str]:
    if not project_id:
        return None
    result = await db.execute(select(Project.id).where(Project.id == project_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project_id


def _validate_ip(value: str) -> bool:
    """Return True if *value* is a valid IPv4 address."""
    try:
        ipaddress.IPv4Address(value)
        return True
    except ValueError:
        return False


@router.post("/import")
async def import_devices_csv(
    request: Request,
    file: UploadFile = File(...),
    project_id: Optional[str] = Query(None, max_length=36),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Bulk-import devices from a CSV file.

    The CSV must contain a header row.  Recognised columns:
    ip_address (required), name, hostname, manufacturer, model,
    firmware_version, category, location, mac_address, notes.

    Devices whose ip_address already exists in the database are skipped.
    A maximum of 500 data rows is accepted per upload.
    """
    check_rate_limit(request, max_requests=5, window_seconds=60, action="device_import")
    # Validate content type loosely — allow text/csv and application/octet-stream
    if file.content_type and file.content_type not in (
        "text/csv",
        "application/csv",
        "application/vnd.ms-excel",
        "application/octet-stream",
        "text/plain",
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{file.content_type}'. Please upload a CSV file.",
        )

    # Read the entire upload into memory (capped at ~2 MB to be safe)
    raw = await file.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="CSV file exceeds 2 MB limit")

    try:
        text = raw.decode("utf-8-sig")  # handle BOM from Excel
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File is not valid UTF-8 text")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV file has no header row")

    validated_project_id = await _validate_project_id(db, project_id)

    # Normalise header names (strip whitespace, lowercase)
    normalised_fields = [f.strip().lower().replace(" ", "_") for f in reader.fieldnames]
    if "ip_address" not in normalised_fields:
        raise HTTPException(
            status_code=400,
            detail="CSV must contain an 'ip_address' column",
        )

    # Re-create the reader with normalised fieldnames so row keys are clean
    reader = csv.DictReader(io.StringIO(text))
    reader.fieldnames = normalised_fields  # type: ignore[assignment]
    # Skip the original header line that DictReader already consumed
    next(reader, None)

    # Pre-load existing IP addresses for duplicate detection
    existing_result = await db.execute(
        select(Device.ip_address).where(Device.ip_address.isnot(None))
    )
    existing_ips: set[str] = {row[0] for row in existing_result.all()}

    imported = 0
    skipped = 0
    errors: list[dict] = []

    for row_num, row in enumerate(reader, start=2):  # row 1 is the header
        if row_num - 1 >= _MAX_IMPORT_ROWS:
            errors.append({
                "row": row_num,
                "error": f"Row limit of {_MAX_IMPORT_ROWS} exceeded; remaining rows ignored",
            })
            break

        ip_raw = (row.get("ip_address") or "").strip()
        if not ip_raw:
            errors.append({"row": row_num, "error": "Missing ip_address"})
            continue

        if not _validate_ip(ip_raw):
            errors.append({"row": row_num, "ip_address": ip_raw, "error": "Invalid IPv4 address"})
            continue

        # Duplicate check (in-memory set includes both DB and already-imported)
        if ip_raw in existing_ips:
            skipped += 1
            continue

        # Validate optional MAC address
        mac_raw = (row.get("mac_address") or "").strip() or None
        if mac_raw and not _MAC_RE_IMPORT.match(mac_raw):
            errors.append({
                "row": row_num,
                "ip_address": ip_raw,
                "error": f"Invalid MAC address: {mac_raw}",
            })
            continue

        # Validate category
        category_raw = (row.get("category") or "").strip().lower() or "unknown"
        if category_raw not in _VALID_CATEGORIES:
            category_raw = "unknown"

        # Sanitize text fields — "name" column maps to hostname
        hostname = strip_html(
            (row.get("hostname") or row.get("name") or "").strip() or None
        )
        manufacturer = strip_html((row.get("manufacturer") or "").strip() or None)
        model_val = strip_html((row.get("model") or "").strip() or None)
        firmware_version = strip_html((row.get("firmware_version") or "").strip() or None)
        location = strip_html((row.get("location") or "").strip() or None)
        notes = strip_html((row.get("notes") or "").strip() or None)

        device = Device(
            ip_address=ip_raw,
            mac_address=mac_raw,
            hostname=hostname,
            manufacturer=manufacturer,
            model=model_val,
            firmware_version=firmware_version,
            category=category_raw,
            location=location,
            notes=notes,
            project_id=validated_project_id,
        )
        db.add(device)
        existing_ips.add(ip_raw)
        imported += 1

    if imported:
        try:
            await db.flush()
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(status_code=409, detail="A device with this IP or MAC address already exists")

    await log_action(
        db, user, "bulk_import", "device", None,
        {
            "imported": imported,
            "skipped": skipped,
            "errors": len(errors),
            "file": file.filename,
        },
        request,
    )

    return {"imported": imported, "skipped": skipped, "errors": errors}


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

@router.get("/export")
async def export_devices_csv(
    category: Optional[str] = None,
    status: Optional[str] = None,
    project_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """Export all devices as a downloadable CSV file (streaming)."""
    query = select(Device)
    if category:
        query = query.where(Device.category == category)
    if status:
        query = query.where(Device.status == status)
    if project_id:
        query = query.where(Device.project_id == project_id)
    query = query.order_by(Device.created_at.desc())

    result = await db.execute(query)
    devices = result.scalars().all()

    _csv_headers = [
        "ip_address", "mac_address", "hostname", "manufacturer", "model",
        "firmware_version", "category", "status", "addressing_mode",
        "notes", "project_id", "id", "created_at", "updated_at",
    ]

    def generate_csv():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(_csv_headers)
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)
        for d in devices:
            writer.writerow([
                d.ip_address or "",
                d.mac_address or "",
                d.hostname or "",
                d.manufacturer or "",
                d.model or "",
                d.firmware_version or "",
                d.category.value if hasattr(d.category, "value") else (d.category or ""),
                d.status.value if hasattr(d.status, "value") else (d.status or ""),
                d.addressing_mode.value if hasattr(d.addressing_mode, "value") else (d.addressing_mode or ""),
                d.notes or "",
                d.project_id or "",
                d.id,
                d.created_at.isoformat() if d.created_at else "",
                d.updated_at.isoformat() if d.updated_at else "",
            ])
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    return StreamingResponse(
        generate_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=devices.csv"},
    )


class TrendRunSummary(BaseModel):
    run_id: str
    date: str
    verdict: Optional[str] = None
    passed: int = 0
    failed: int = 0
    advisory: int = 0
    total: int = 0
    pass_rate: float = 0.0


class DeviceTrendResponse(BaseModel):
    device_id: str
    device_name: Optional[str] = None
    runs: List[TrendRunSummary] = Field(default_factory=list)
    trend: str = "stable"
    total_runs: int = 0
    best_pass_rate: float = 0.0
    worst_pass_rate: float = 0.0
    latest_pass_rate: float = 0.0


def _compute_trend(pass_rates: List[float]) -> str:
    """Determine trend from the most recent 3 pass rates (newest-first order)."""
    if len(pass_rates) < 2:
        return "stable"
    recent = pass_rates[:3]
    # recent[0] is the newest run
    improving = all(recent[i] >= recent[i + 1] for i in range(len(recent) - 1))
    degrading = all(recent[i] <= recent[i + 1] for i in range(len(recent) - 1))
    # Strict: require at least one inequality to avoid marking flat lines as improving/degrading
    if improving and recent[0] != recent[-1]:
        return "improving"
    if degrading and recent[0] != recent[-1]:
        return "degrading"
    return "stable"


@router.get("/{device_id}/trends", response_model=DeviceTrendResponse)
async def device_trends(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """Return historical test results over time for a device."""
    # Verify device exists
    device_result = await db.execute(select(Device).where(Device.id == device_id))
    device = device_result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Fetch the last 20 completed runs ordered by created_at desc
    runs_query = (
        select(TestRun)
        .where(
            TestRun.device_id == device_id,
            TestRun.status == TestRunStatus.COMPLETED,
        )
        .order_by(TestRun.created_at.desc())
        .limit(20)
    )
    runs_result = await db.execute(runs_query)
    runs = runs_result.scalars().all()

    if not runs:
        return DeviceTrendResponse(
            device_id=device_id,
            device_name=device.hostname,
            runs=[],
            trend="stable",
            total_runs=0,
            best_pass_rate=0.0,
            worst_pass_rate=0.0,
            latest_pass_rate=0.0,
        )

    run_ids = [r.id for r in runs]

    # Count verdicts per run in a single query
    verdict_counts_query = (
        select(
            TestResult.test_run_id,
            func.count().label("total"),
            func.sum(case((TestResult.verdict == TestVerdict.PASS, 1), else_=0)).label("passed"),
            func.sum(case((TestResult.verdict == TestVerdict.FAIL, 1), else_=0)).label("failed"),
            func.sum(case((TestResult.verdict == TestVerdict.ADVISORY, 1), else_=0)).label("advisory"),
        )
        .where(TestResult.test_run_id.in_(run_ids))
        .group_by(TestResult.test_run_id)
    )
    verdict_result = await db.execute(verdict_counts_query)
    counts_by_run = {row.test_run_id: row for row in verdict_result.all()}

    run_summaries: List[TrendRunSummary] = []
    pass_rates: List[float] = []

    for run in runs:
        counts = counts_by_run.get(run.id)
        total = int(counts.total) if counts else 0
        passed = int(counts.passed) if counts else 0
        failed = int(counts.failed) if counts else 0
        advisory = int(counts.advisory) if counts else 0
        pass_rate = round((passed / total) * 100, 1) if total > 0 else 0.0

        verdict_str = run.overall_verdict.value if run.overall_verdict else None

        run_summaries.append(TrendRunSummary(
            run_id=run.id,
            date=(
                as_utc(run.created_at).isoformat().replace("+00:00", "Z")
                if run.created_at else ""
            ),
            verdict=verdict_str,
            passed=passed,
            failed=failed,
            advisory=advisory,
            total=total,
            pass_rate=pass_rate,
        ))
        pass_rates.append(pass_rate)

    all_rates = [s.pass_rate for s in run_summaries if s.total > 0]

    return DeviceTrendResponse(
        device_id=device_id,
        device_name=device.hostname,
        runs=run_summaries,
        trend=_compute_trend(pass_rates),
        total_runs=len(run_summaries),
        best_pass_rate=max(all_rates) if all_rates else 0.0,
        worst_pass_rate=min(all_rates) if all_rates else 0.0,
        latest_pass_rate=pass_rates[0] if pass_rates else 0.0,
    )


# ---------------------------------------------------------------------------
# Latency (ping) and traceroute
# ---------------------------------------------------------------------------


def _parse_ping_samples(stdout: str) -> List[dict]:
    """Parse individual ping response lines into latency samples."""
    samples = []
    for line in stdout.splitlines():
        match = re.search(r"icmp_seq=(\d+).*time=([\d.]+)\s*ms", line)
        if match:
            samples.append({
                "seq": int(match.group(1)),
                "time_ms": round(float(match.group(2)), 2),
            })
    return samples


def _parse_ping_summary(stdout: str) -> dict:
    """Parse the summary line from ping output."""
    summary: dict = {
        "packets_sent": 0,
        "packets_received": 0,
        "packet_loss": 100.0,
        "min_ms": None,
        "avg_ms": None,
        "max_ms": None,
    }
    for line in stdout.splitlines():
        loss_match = re.search(
            r"(\d+) packets? transmitted, (\d+) received.*?([\d.]+)% packet loss",
            line,
        )
        if loss_match:
            summary["packets_sent"] = int(loss_match.group(1))
            summary["packets_received"] = int(loss_match.group(2))
            summary["packet_loss"] = float(loss_match.group(3))

        rtt_match = re.search(
            r"(?:rtt|round-trip)\s+min/avg/max(?:/\w+)?\s*=\s*([\d.]+)/([\d.]+)/([\d.]+)",
            line,
        )
        if rtt_match:
            summary["min_ms"] = round(float(rtt_match.group(1)), 2)
            summary["avg_ms"] = round(float(rtt_match.group(2)), 2)
            summary["max_ms"] = round(float(rtt_match.group(3)), 2)

    return summary


def _parse_traceroute_xml(xml_str: str) -> List[dict]:
    """Parse nmap XML output to extract traceroute hop data."""
    hops = []
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return hops

    for trace in root.iter("trace"):
        for hop in trace.iter("hop"):
            ttl = hop.get("ttl")
            ipaddr = hop.get("ipaddr", "")
            rtt = hop.get("rtt")
            host = hop.get("host", "")
            hops.append({
                "ttl": int(ttl) if ttl else 0,
                "ip": ipaddr,
                "hostname": host if host and host != ipaddr else None,
                "rtt_ms": round(float(rtt), 2) if rtt else None,
            })

    hops.sort(key=lambda h: h["ttl"])
    return hops


@router.get("/{device_id}/ping")
async def ping_device(
    device_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """Ping a device and return latency measurements."""
    check_rate_limit(request, max_requests=30, window_seconds=60, action="device_ping")

    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if not device.ip_address:
        raise HTTPException(status_code=422, detail="Device has no IP address")

    try:
        ping_result = await tools_client.ping(device.ip_address, count=5)
    except Exception as exc:
        logger.warning("Ping failed for %s: %s", device.ip_address, exc)
        raise HTTPException(
            status_code=get_tools_error_status(exc),
            detail=describe_tools_error(exc, fallback="Ping failed"),
        )

    stdout = ping_result.get("stdout", "")
    return {
        "device_id": device_id,
        "ip_address": device.ip_address,
        "reachable": ping_result.get("exit_code") == 0,
        "samples": _parse_ping_samples(stdout),
        "summary": _parse_ping_summary(stdout),
    }


@router.get("/{device_id}/traceroute")
async def traceroute_device(
    device_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """Run traceroute to a device and return the network path."""
    check_rate_limit(request, max_requests=5, window_seconds=60, action="device_traceroute")

    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if not device.ip_address:
        raise HTTPException(status_code=422, detail="Device has no IP address")

    try:
        raw = await tools_client.nmap(
            device.ip_address,
            ["-sn", "--traceroute", "-oX", "-"],
            timeout=60,
        )
    except Exception as exc:
        logger.warning("Traceroute failed for %s: %s", device.ip_address, exc)
        raise HTTPException(
            status_code=get_tools_error_status(exc),
            detail=describe_tools_error(exc, fallback="Traceroute failed"),
        )

    xml_out = raw.get("stdout", "")
    hops = _parse_traceroute_xml(xml_out)

    return {
        "device_id": device_id,
        "ip_address": device.ip_address,
        "hops": hops,
        "total_hops": len(hops),
    }


@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.patch("/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: str,
    data: DeviceUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    updates = sanitize_dict(data.model_dump(exclude_unset=True), ["hostname", "manufacturer", "model", "firmware_version", "notes", "location", "serial_number"])

    # Duplicate IP/MAC validation
    if "ip_address" in updates and updates["ip_address"]:
        dup = await db.execute(
            select(Device).where(Device.ip_address == updates["ip_address"], Device.id != device_id)
        )
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=409, detail=f"A device with IP address {updates['ip_address']} already exists")
    if "mac_address" in updates and updates["mac_address"]:
        dup = await db.execute(
            select(Device).where(Device.mac_address == updates["mac_address"], Device.id != device_id)
        )
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=409, detail=f"A device with MAC address {updates['mac_address']} already exists")

    # Validate addressing_mode transitions
    effective_mode = updates.get("addressing_mode", device.addressing_mode.value if hasattr(device.addressing_mode, "value") else device.addressing_mode)
    if effective_mode == "dhcp":
        effective_mac = updates.get("mac_address", device.mac_address)
        if not effective_mac:
            raise HTTPException(status_code=422, detail="MAC address is required when addressing mode is DHCP")
    elif effective_mode == "static":
        effective_ip = updates.get("ip_address", device.ip_address)
        if not effective_ip:
            raise HTTPException(status_code=422, detail="IP address is required when addressing mode is static")

    # Validate profile_id exists if provided
    if "profile_id" in updates and updates["profile_id"]:
        from app.models.device_profile import DeviceProfile
        profile_result = await db.execute(select(DeviceProfile.id).where(DeviceProfile.id == updates["profile_id"]))
        if profile_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Device profile not found")

    allowed_fields = [
        "ip_address", "mac_address", "hostname", "manufacturer", "model",
        "firmware_version", "category", "status", "notes", "addressing_mode",
        "profile_id", "open_ports", "discovery_data", "location", "serial_number",
    ]
    for field in allowed_fields:
        if field in updates:
            setattr(device, field, updates[field])
    await db.flush()
    await db.refresh(device)
    await log_action(db, user, "update", "device", device_id, {"fields": list(updates.keys())}, request)
    return device


@router.delete("/{device_id}", status_code=204)
async def delete_device(
    device_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["admin"])),
):
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    await db.delete(device)
    await db.flush()
    await log_action(db, user, "delete", "device", device_id, {"ip": device.ip_address}, request)


@router.post("/{device_id}/discover-ip", response_model=DeviceResponse)
async def discover_device_ip(
    device_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Run an ARP scan on local subnets to find the IP for a DHCP device by MAC address."""
    check_rate_limit(request, max_requests=10, window_seconds=60, action="discover_ip")
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    if not device.mac_address:
        raise HTTPException(
            status_code=422,
            detail="Device has no MAC address — cannot discover IP",
        )

    mac_upper = device.mac_address.upper().replace("-", ":")

    authorized_networks = await get_active_networks(db)
    authorized_cidrs = [network.cidr for network in authorized_networks if network.cidr]
    detection = None
    try:
        detection = await tools_client.detect_networks()
    except Exception as exc:
        logger.warning("Network detection failed during DHCP IP discovery: %s", exc)

    subnets_to_scan = _build_discovery_scan_ranges(authorized_cidrs, detection)
    discovered_ip = None
    successful_scans = 0
    last_scan_error: str | None = None
    last_scan_exception: Exception | None = None

    for subnet in subnets_to_scan:
        try:
            scan_result = await tools_client.nmap(
                target=subnet,
                args=["-sn", "-PR"],  # ARP ping scan
                timeout=30,
            )
            successful_scans += 1
            hosts = nmap_parser.parse_host_discovery(scan_result.get("stdout", ""))
            for host in hosts:
                found_mac = str(host.get("mac") or "").upper().replace("-", ":")
                candidate_ip = str(host.get("ip") or "").strip()
                if found_mac != mac_upper or not candidate_ip:
                    continue
                try:
                    ipaddress.ip_address(candidate_ip)
                except ValueError:
                    logger.warning("Ignoring invalid discovered IP %s for MAC %s", candidate_ip, mac_upper)
                    continue
                discovered_ip = candidate_ip
                break
            if discovered_ip:
                break
        except Exception as exc:
            last_scan_exception = exc
            last_scan_error = describe_tools_error(exc, fallback=f"Discovery scan failed on {subnet}")
            logger.warning("ARP scan on %s failed: %s", subnet, exc)
            continue

    if not discovered_ip:
        if successful_scans == 0:
            raise HTTPException(
                status_code=get_tools_error_status(last_scan_exception or RuntimeError("Tools sidecar is unavailable")),
                detail=last_scan_error or "Tools sidecar is unavailable. Automated IP discovery could not run.",
            )
        raise HTTPException(
            status_code=404,
            detail=f"Could not discover IP for MAC {device.mac_address}. "
                   f"Scanned {len(subnets_to_scan)} subnet(s). Ensure the device is powered on and connected to the network.",
        )

    # Check that no other device already has this IP
    existing_ip = await db.execute(
        select(Device).where(Device.ip_address == discovered_ip, Device.id != device_id)
    )
    if existing_ip.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Discovered IP {discovered_ip} is already assigned to another device",
        )

    device.ip_address = discovered_ip
    await db.flush()
    await db.refresh(device)
    await log_action(
        db, user, "discover_ip", "device", device_id,
        {"mac": device.mac_address, "discovered_ip": discovered_ip}, request,
    )
    return device
