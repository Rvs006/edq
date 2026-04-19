"""Test Run management routes."""

import logging
import os
import uuid
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, and_
from sqlalchemy.orm import selectinload

from app.models.database import get_db
from app.models.test_run import (
    TestRun,
    TestRunStatus,
    normalize_test_run_status,
)
from app.models.test_result import TestResult, TestVerdict, TestTier
from app.models.test_template import TestTemplate
from app.models.device import Device
from app.models.user import User
from app.models.nessus_finding import NessusFinding
from app.schemas.test import TestRunCreate, TestRunUpdate, TestRunResponse
from app.security.auth import get_current_active_user
from app.services.discovery_service import build_device_display_name
from app.services.run_readiness import (
    build_run_readiness_summary,
    merge_readiness_into_metadata,
)
from app.services.test_run_connectivity import ensure_device_execution_readiness
from app.services.test_library import get_test_by_id
from app.services.test_run_launcher import cancel_test_run as _cancel_test_run, is_run_executing, launch_test_run
from app.services.wobbly_cable import get_cable_handler
from app.services.nessus_parser import nessus_parser
from app.config import settings
from app.utils.audit import log_action
from app.utils.collections import ordered_unique
from app.utils.datetime import utcnow_naive
from app.models.user import UserRole

logger = logging.getLogger("edq.routes.test_runs")

router = APIRouter()


async def _get_authorized_test_run(
    run_id: str, user: User, db: AsyncSession
) -> TestRun:
    """Load a test run and verify the current user is authorized to access it.

    Admins and reviewers can access all test runs.
    Engineers can only access their own test runs.
    """
    result = await db.execute(select(TestRun).where(TestRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Test run not found")
    if user.role == UserRole.ENGINEER and run.engineer_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return run

def _enrich_run_from_loaded(run: TestRun) -> dict:
    """Add device info, template_name, and confidence score to a TestRun.

    Expects that ``run.device``, ``run.template``, and ``run.engineer``
    have already been eager-loaded (e.g. via ``selectinload``).
    """
    data = TestRunResponse.model_validate(run).model_dump()
    data["status"] = normalize_test_run_status(run.status)

    device = run.device
    if device:
        data["device_name"] = build_device_display_name(
            device.ip_address,
            device.hostname,
            device.manufacturer,
            device.model,
        )
        data["device_ip"] = device.ip_address
        data["device_mac_address"] = device.mac_address
        data["device_manufacturer"] = device.manufacturer
        data["device_model"] = device.model
        data["device_category"] = device.category.value if device.category else None
    else:
        data["device_name"] = None
        data["device_ip"] = None
        data["device_mac_address"] = None
        data["device_manufacturer"] = None
        data["device_model"] = None
        data["device_category"] = None

    template = run.template
    data["template_name"] = template.name if template else None

    engineer = run.engineer
    data["engineer_name"] = (
        (engineer.full_name or engineer.username) if engineer else None
    )

    readiness_summary = build_run_readiness_summary(run)
    data["confidence"] = readiness_summary["score"]
    data["readiness_summary"] = readiness_summary

    return data


def _run_eager_options():
    """Return the selectinload options needed for _enrich_run_from_loaded."""
    return [
        selectinload(TestRun.device),
        selectinload(TestRun.template),
        selectinload(TestRun.engineer),
    ]


async def _enrich_run(run: TestRun, db: AsyncSession) -> dict:
    """Enrich a single run by re-loading it with eager relationships.

    Used for single-run endpoints (create, update, get-by-id).
    For list endpoints, use _enrich_run_from_loaded with eager-loaded query.
    """
    result = await db.execute(
        select(TestRun)
        .where(TestRun.id == run.id)
        .options(*_run_eager_options())
    )
    loaded = result.scalar_one()
    return _enrich_run_from_loaded(loaded)


def _status_filter_values(status: str) -> list[str]:
    normalized = normalize_test_run_status(status)
    values = [normalized]
    if normalized == TestRunStatus.PAUSED_MANUAL.value:
        values.append(TestRunStatus.PAUSED.value)
    return values


async def _summarize_run_results(db: AsyncSession, run_id: str) -> dict[str, int | bool]:
    # Use SQL aggregation instead of loading all result rows into Python
    result = await db.execute(
        select(
            func.count(case((TestResult.verdict == TestVerdict.PASS, 1))).label("passed"),
            func.count(case((TestResult.verdict == TestVerdict.FAIL, 1))).label("failed"),
            func.count(case((TestResult.verdict == TestVerdict.ADVISORY, 1))).label("advisory"),
            func.count(case((TestResult.verdict == TestVerdict.NA, 1))).label("na"),
            func.count(case((TestResult.verdict == TestVerdict.ERROR, 1))).label("errors"),
            func.count(case((and_(
                TestResult.verdict == TestVerdict.PENDING,
                TestResult.tier == TestTier.GUIDED_MANUAL,
            ), 1))).label("pending_manual"),
            func.count(case((and_(
                TestResult.verdict == TestVerdict.FAIL,
                TestResult.is_essential == "yes",
            ), 1))).label("essential_failed"),
            func.count().label("total"),
        ).where(TestResult.test_run_id == run_id)
    )
    row = result.one()
    passed = row.passed
    failed = row.failed
    advisory = row.advisory
    na = row.na
    errors = row.errors

    return {
        "passed": passed,
        "failed": failed,
        "advisory": advisory,
        "na": na,
        "errors": errors,
        "pending_manual": row.pending_manual,
        "completed": passed + failed + advisory + na + errors,
        "essential_failed": row.essential_failed > 0,
        "total": row.total,
    }


def _overall_verdict_from_summary(summary: dict[str, int | bool]) -> str | None:
    if summary["essential_failed"] or summary["failed"]:
        return "fail"
    if summary["advisory"]:
        return "qualified_pass"
    if summary["completed"]:
        return "pass"
    return None


def _apply_summary_to_run(run: TestRun, summary: dict[str, int | bool]) -> None:
    run.passed_tests = int(summary["passed"])
    run.failed_tests = int(summary["failed"])
    run.advisory_tests = int(summary["advisory"])
    run.na_tests = int(summary["na"])
    run.completed_tests = int(summary["completed"])
    if run.total_tests:
        run.progress_pct = round((run.completed_tests / run.total_tests) * 100, 1)


def _calc_confidence(run: TestRun) -> int:
    """Calculate a 1-10 confidence score for a test run."""
    return build_run_readiness_summary(run)["score"]


def _missing_ip_detail_for_action(action: str, dhcp_missing_ip: bool) -> str:
    if not dhcp_missing_ip:
        return "Device has no IP address"
    if action == "resume":
        return (
            "DHCP device still has no discovered IP address. Reconnect it to the "
            "target network or use Discover IP before resuming."
        )
    return (
        "DHCP device has no discovered IP address yet. Use Discover IP or connect "
        "it to the target network so EDQ can locate the lease."
    )


def _resume_block_detail(reason: str) -> str:
    if reason == "service_unreachable":
        return (
            "Device is reachable but no supported service ports are open yet. "
            "Resume once a service port becomes reachable."
        )
    return "Device is still unreachable. Reconnect the cable or device before resuming."


@router.get("/", response_model=List[TestRunResponse])
async def list_test_runs(
    device_id: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    query = select(TestRun)
    # Engineers can only see their own test runs
    if user.role == UserRole.ENGINEER:
        query = query.where(TestRun.engineer_id == user.id)
    if device_id:
        query = query.where(TestRun.device_id == device_id)
    if status:
        query = query.where(TestRun.status.in_(_status_filter_values(status)))
    result = await db.execute(
        query.options(*_run_eager_options())
        .order_by(TestRun.created_at.desc()).offset(skip).limit(limit)
    )
    runs = result.scalars().all()
    return [_enrich_run_from_loaded(r) for r in runs]


@router.get("/stats")
async def test_run_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    # Engineers see only their own stats; admins/reviewers see all
    base_filter = TestRun.engineer_id == user.id if user.role == UserRole.ENGINEER else True

    total = await db.execute(select(func.count(TestRun.id)).where(base_filter))
    by_status = await db.execute(
        select(TestRun.status, func.count(TestRun.id))
        .where(base_filter)
        .group_by(TestRun.status)
    )
    by_verdict = await db.execute(
        select(TestRun.overall_verdict, func.count(TestRun.id))
        .where(base_filter)
        .where(TestRun.overall_verdict.isnot(None))
        .group_by(TestRun.overall_verdict)
    )
    return {
        "total": total.scalar() or 0,
        "by_status": {str(row[0]): row[1] for row in by_status.all()},
        "by_verdict": {str(row[0]): row[1] for row in by_verdict.all()},
    }


@router.get("/check-duplicate")
async def check_duplicate_runs(
    device_id: str = Query(...),
    template_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Check if there are existing runs for the same device+template combo."""
    query = (
        select(TestRun)
        .where(TestRun.device_id == device_id, TestRun.template_id == template_id)
        .order_by(TestRun.created_at.desc())
        .limit(5)
    )
    result = await db.execute(query)
    existing = result.scalars().all()

    runs_info = []
    for r in existing:
        readiness_summary = build_run_readiness_summary(r)
        runs_info.append({
            "id": r.id,
            "status": normalize_test_run_status(r.status),
            "overall_verdict": r.overall_verdict,
            "completed_tests": r.completed_tests,
            "total_tests": r.total_tests,
            "confidence": readiness_summary["score"],
            "readiness_summary": readiness_summary,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        })

    return {
        "has_duplicates": len(runs_info) > 0,
        "count": len(runs_info),
        "existing_runs": runs_info,
    }


@router.post("/", response_model=TestRunResponse, status_code=201)
async def create_test_run(
    data: TestRunCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    device_result = await db.execute(select(Device).where(Device.id == data.device_id))
    device = device_result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    template_result = await db.execute(
        select(TestTemplate).where(
            TestTemplate.id == data.template_id,
            TestTemplate.is_active == True,
        )
    )
    template = template_result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Handle both native list and double-serialized JSON string
    raw_ids = template.test_ids
    if isinstance(raw_ids, str):
        import json as _json
        raw_ids = _json.loads(raw_ids)

    raw_ids = ordered_unique(raw_ids)

    test_run = TestRun(
        device_id=data.device_id,
        template_id=data.template_id,
        engineer_id=user.id,
        project_id=device.project_id,
        agent_id=data.agent_id,
        connection_scenario=data.connection_scenario,
        total_tests=len(raw_ids),
        status=TestRunStatus.PENDING,
        run_metadata=data.metadata,
    )
    db.add(test_run)
    await db.flush()

    for test_id in raw_ids:
        test_def = get_test_by_id(test_id)
        if test_def:
            result = TestResult(
                test_run_id=test_run.id,
                test_id=test_id,
                test_name=test_def["name"],
                tier=TestTier(test_def["tier"]),
                tool=test_def.get("tool"),
                verdict=TestVerdict.PENDING,
                is_essential="yes" if test_def["is_essential"] else "no",
                compliance_map=test_def.get("compliance_map", []),
            )
            db.add(result)

    await db.flush()
    await db.refresh(test_run)
    await log_action(db, user, "create", "test_run", test_run.id, {"device_id": data.device_id}, request)
    # Commit explicitly so the new run is visible to subsequent GET requests
    # immediately (before get_db's implicit commit after response is sent).
    await db.commit()
    return await _enrich_run(test_run, db)


@router.get("/{run_id}", response_model=TestRunResponse)
async def get_test_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    run = await _get_authorized_test_run(run_id, user, db)
    return await _enrich_run(run, db)


@router.patch("/{run_id}", response_model=TestRunResponse)
async def update_test_run(
    run_id: str,
    data: TestRunUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    run = await _get_authorized_test_run(run_id, user, db)
    updates = data.model_dump(exclude_unset=True)
    if "connection_scenario" in updates:
        if normalize_test_run_status(run.status) != TestRunStatus.PENDING.value:
            raise HTTPException(
                status_code=400,
                detail="Connection scenario can only be changed before a run starts",
            )
        run.connection_scenario = updates["connection_scenario"]
    if "synopsis" in updates:
        run.synopsis = updates["synopsis"]
    if "synopsis_status" in updates:
        run.synopsis_status = updates["synopsis_status"]
    await db.flush()
    await db.refresh(run)
    return await _enrich_run(run, db)


@router.post("/{run_id}/start")
async def start_test_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    run = await _get_authorized_test_run(run_id, user, db)
    run_status = normalize_test_run_status(run.status)

    if run_status not in (
        TestRunStatus.PENDING.value,
        TestRunStatus.FAILED.value,
        TestRunStatus.CANCELLED.value,
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot start run in '{run_status}' status. Must be 'pending', 'failed', or 'cancelled'.",
        )

    if is_run_executing(run_id):
        raise HTTPException(status_code=409, detail="Test run is already executing")

    device = await db.get(Device, run.device_id)
    readiness = await ensure_device_execution_readiness(db, device, logger=logger)
    if readiness.missing_ip:
        raise HTTPException(
            status_code=409 if readiness.dhcp_missing_ip else 422,
            detail=_missing_ip_detail_for_action("start", readiness.dhcp_missing_ip),
        )

    task = launch_test_run(run_id)
    if task is None:
        raise HTTPException(
            status_code=409,
            detail="Test run was already started by another process",
        )

    return {"status": "running", "message": "Test execution started", "run_id": run_id}


@router.post("/{run_id}/cancel")
async def cancel_test_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Cancel a running or paused test run and kill its sidecar processes."""
    from app.services.tools_client import tools_client

    run = await _get_authorized_test_run(run_id, user, db)
    run_status = normalize_test_run_status(run.status)

    if run_status not in (
        TestRunStatus.RUNNING.value,
        TestRunStatus.SELECTING_INTERFACE.value,
        TestRunStatus.SYNCING.value,
        TestRunStatus.PAUSED_MANUAL.value,
        TestRunStatus.PAUSED_CABLE.value,
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel run in '{run_status}' status. Must be active or paused.",
        )

    # 1. Cancel the asyncio task (stops test engine loop)
    _cancel_test_run(run_id)

    # 2. Kill sidecar tool processes for this device
    device = await db.get(Device, run.device_id)
    if device and device.ip_address:
        kill_result = await tools_client.kill_target(device.ip_address)
        logger.info("Cancelled run %s — killed %s sidecar process(es) for %s",
                     run_id, kill_result.get("killed", 0), device.ip_address)

    # 3. Mark run as cancelled
    run.status = TestRunStatus.CANCELLED
    run.completed_at = utcnow_naive()
    await db.flush()

    return {"status": "cancelled", "message": "Test run cancelled", "run_id": run_id}


@router.post("/{run_id}/pause")
async def pause_test_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    run = await _get_authorized_test_run(run_id, user, db)
    run_status = normalize_test_run_status(run.status)

    if run_status != TestRunStatus.RUNNING.value:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot pause run in '{run_status}' status. Must be 'running'.",
        )

    run.status = TestRunStatus.PAUSED_MANUAL
    await db.flush()
    await db.refresh(run)

    # Sync the live cable handler so it does NOT auto-resume the run
    # while the engineer has manually paused it.
    handler = get_cable_handler(run_id)
    if handler:
        handler.manual_pause()

    return {"status": TestRunStatus.PAUSED_MANUAL.value, "message": "Test execution paused", "run_id": run_id}


@router.post("/{run_id}/pause-cable")
async def pause_test_run_for_cable(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    run = await _get_authorized_test_run(run_id, user, db)
    run_status = normalize_test_run_status(run.status)

    if run_status not in (TestRunStatus.RUNNING.value, TestRunStatus.AWAITING_MANUAL.value):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot flag cable issue in '{run_status}' status. Must be 'running' or 'awaiting_manual'.",
        )

    run.status = TestRunStatus.PAUSED_CABLE
    await db.flush()
    await db.refresh(run)

    # Sync the live cable handler — mark as manually paused so the
    # monitor loop does NOT auto-resume even if the device is pingable.
    handler = get_cable_handler(run_id)
    if handler:
        handler.manual_pause()
        await handler.manager.broadcast(
            f"test-run:{run_id}",
            {
                "type": "cable_disconnected",
                "data": {
                    "run_id": run_id,
                    "device_ip": handler.ip,
                    "message": "Cable issue manually flagged by engineer",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
        )

    return {"status": TestRunStatus.PAUSED_CABLE.value, "message": "Cable issue flagged", "run_id": run_id}


@router.post("/{run_id}/resume")
async def resume_test_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    run = await _get_authorized_test_run(run_id, user, db)
    run_status = normalize_test_run_status(run.status)

    if run_status not in (
        TestRunStatus.PAUSED_MANUAL.value,
        TestRunStatus.PAUSED_CABLE.value,
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resume run in '{run_status}' status. Must be paused.",
        )

    handler = get_cable_handler(run_id)

    if run_status == TestRunStatus.PAUSED_CABLE.value:
        device = await db.get(Device, run.device_id)
        readiness = await ensure_device_execution_readiness(db, device, logger=logger)
        if readiness.missing_ip:
            raise HTTPException(
                status_code=409,
                detail=_missing_ip_detail_for_action("resume", readiness.dhcp_missing_ip),
            )
        if handler and device and device.ip_address:
            handler.update_target(device.ip_address, readiness.probe_ports)
        if handler and is_run_executing(run_id) and not readiness.can_execute:
            raise HTTPException(
                status_code=409,
                detail=_resume_block_detail(readiness.reason),
            )

    # Sync the live cable handler so the monitor loop exits paused state
    # and enters TCP grace mode (tolerates TCP failures for 45s).
    if handler and is_run_executing(run_id):
        run.status = TestRunStatus.RUNNING
        await db.flush()
        await db.refresh(run)
        await handler.resume()
        return {"status": "running", "message": "Test execution resumed", "run_id": run_id}

    task = launch_test_run(run_id)
    if task is None:
        raise HTTPException(
            status_code=409,
            detail="Test run was already started by another process",
        )

    run.status = TestRunStatus.RUNNING
    await db.flush()
    await db.refresh(run)
    return {"status": "running", "message": "Test execution resumed", "run_id": run_id}


@router.post("/{run_id}/complete", response_model=TestRunResponse)
async def complete_test_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    run = await _get_authorized_test_run(run_id, user, db)
    summary = await _summarize_run_results(db, run_id)
    if summary["pending_manual"]:
        raise HTTPException(
            status_code=400,
            detail="Cannot complete run while manual tests are still pending",
        )

    _apply_summary_to_run(run, summary)
    run.progress_pct = 100.0 if run.total_tests else 0.0
    run.status = TestRunStatus.COMPLETED
    run.completed_at = utcnow_naive()
    run.overall_verdict = _overall_verdict_from_summary(summary)
    results = await db.execute(
        select(TestResult).where(TestResult.test_run_id == run_id).order_by(TestResult.test_id)
    )
    all_results = list(results.scalars().all())
    run.run_metadata = merge_readiness_into_metadata(
        run.run_metadata,
        build_run_readiness_summary(run, all_results),
    )

    await db.commit()
    return await _enrich_run(run, db)


@router.post("/{run_id}/request-review", response_model=TestRunResponse)
async def request_review_for_test_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    run = await _get_authorized_test_run(run_id, user, db)
    summary = await _summarize_run_results(db, run_id)
    if summary["pending_manual"]:
        raise HTTPException(
            status_code=400,
            detail="Cannot request review while manual tests are still pending",
        )

    _apply_summary_to_run(run, summary)
    run.progress_pct = 100.0 if run.total_tests else 0.0
    run.status = TestRunStatus.AWAITING_REVIEW
    run.completed_at = utcnow_naive()
    run.overall_verdict = _overall_verdict_from_summary(summary)
    results = await db.execute(
        select(TestResult).where(TestResult.test_run_id == run_id).order_by(TestResult.test_id)
    )
    all_results = list(results.scalars().all())
    run.run_metadata = merge_readiness_into_metadata(
        run.run_metadata,
        build_run_readiness_summary(run, all_results),
    )
    await db.commit()
    return await _enrich_run(run, db)


@router.post("/{run_id}/nessus/upload")
async def upload_nessus(
    run_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    run = await _get_authorized_test_run(run_id, user, db)

    if not file.filename or not file.filename.endswith(".nessus"):
        raise HTTPException(status_code=400, detail="Only .nessus files are accepted")

    # Validate content type
    if file.content_type and file.content_type not in (
        "text/xml", "application/xml", "application/octet-stream",
    ):
        raise HTTPException(status_code=400, detail=f"Invalid content type: {file.content_type}")

    content = await file.read()
    max_nessus = settings.MAX_NESSUS_FILE_SIZE
    if len(content) > max_nessus:
        raise HTTPException(status_code=400, detail=f"Nessus file exceeds maximum size of {max_nessus // (1024*1024)}MB")

    upload_dir = os.path.join(settings.UPLOAD_DIR, "nessus")
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, f"{run_id}_{uuid.uuid4().hex[:8]}.nessus")

    with open(file_path, "wb") as f:
        f.write(content)

    try:
        findings = nessus_parser.parse(file_path)
    except Exception:
        os.remove(file_path)
        logger.exception("Failed to parse .nessus file for run %s", run_id)
        raise HTTPException(status_code=400, detail="Failed to parse .nessus file")

    existing = await db.execute(
        select(func.count(NessusFinding.id)).where(NessusFinding.run_id == run_id)
    )
    existing_count = existing.scalar() or 0

    created = 0
    for finding_data in findings:
        nf = NessusFinding(
            run_id=run_id,
            plugin_id=finding_data["plugin_id"],
            plugin_name=finding_data["plugin_name"],
            severity=finding_data["severity"],
            risk_factor=finding_data.get("risk_factor"),
            description=finding_data.get("description"),
            solution=finding_data.get("solution"),
            port=finding_data.get("port"),
            protocol=finding_data.get("protocol"),
            plugin_output=finding_data.get("plugin_output"),
            cvss_score=finding_data.get("cvss_score"),
            cve_ids=finding_data.get("cve_ids"),
        )
        db.add(nf)
        created += 1

    await db.flush()

    severity_counts = {}
    for f in findings:
        sev = f["severity"]
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    return {
        "message": f"Successfully imported {created} Nessus findings",
        "run_id": run_id,
        "findings_imported": created,
        "previously_existing": existing_count,
        "severity_breakdown": severity_counts,
    }


@router.get("/{run_id}/nessus/findings")
async def list_nessus_findings(
    run_id: str,
    severity: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    await _get_authorized_test_run(run_id, user, db)

    query = select(NessusFinding).where(NessusFinding.run_id == run_id)
    if severity:
        query = query.where(NessusFinding.severity == severity)
    query = query.order_by(NessusFinding.cvss_score.desc()).offset(skip).limit(limit)

    findings_result = await db.execute(query)
    findings = findings_result.scalars().all()

    count_query = select(func.count(NessusFinding.id)).where(NessusFinding.run_id == run_id)
    if severity:
        count_query = count_query.where(NessusFinding.severity == severity)
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    return {
        "total": total,
        "findings": [
            {
                "id": f.id,
                "plugin_id": f.plugin_id,
                "plugin_name": f.plugin_name,
                "severity": f.severity,
                "risk_factor": f.risk_factor,
                "port": f.port,
                "protocol": f.protocol,
                "cvss_score": f.cvss_score,
                "cve_ids": f.cve_ids,
                "description": f.description,
                "solution": f.solution,
                "plugin_output": f.plugin_output,
                "imported_at": f.imported_at.isoformat() if f.imported_at else None,
            }
            for f in findings
        ],
    }
