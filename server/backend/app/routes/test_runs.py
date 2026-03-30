"""Test Run management routes."""

import asyncio
import logging
import os
import uuid
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.models.database import get_db
from app.models.test_run import TestRun, TestRunStatus
from app.models.test_result import TestResult, TestVerdict, TestTier
from app.models.test_template import TestTemplate
from app.models.device import Device
from app.models.user import User
from app.models.nessus_finding import NessusFinding
from app.schemas.test import TestRunCreate, TestRunUpdate, TestRunResponse
from app.security.auth import get_current_active_user
from app.services.test_library import get_test_by_id
from app.services.test_engine import test_engine
from app.services.nessus_parser import nessus_parser
from app.config import settings
from app.utils.audit import log_action
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

_running_tasks: dict[str, asyncio.Task] = {}


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
        query = query.where(TestRun.status == status)
    result = await db.execute(
        query.order_by(TestRun.created_at.desc()).offset(skip).limit(limit)
    )
    return result.scalars().all()


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


@router.post("/", response_model=TestRunResponse, status_code=201)
async def create_test_run(
    data: TestRunCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    device = await db.execute(select(Device).where(Device.id == data.device_id))
    if not device.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Device not found")

    template_result = await db.execute(select(TestTemplate).where(TestTemplate.id == data.template_id))
    template = template_result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Handle both native list and double-serialized JSON string
    raw_ids = template.test_ids
    if isinstance(raw_ids, str):
        import json as _json
        raw_ids = _json.loads(raw_ids)

    test_run = TestRun(
        device_id=data.device_id,
        template_id=data.template_id,
        engineer_id=user.id,
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
    return test_run


@router.get("/{run_id}", response_model=TestRunResponse)
async def get_test_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    run = await _get_authorized_test_run(run_id, user, db)
    # Eagerly load results for the response
    result = await db.execute(
        select(TestRun).where(TestRun.id == run_id)
        .options(selectinload(TestRun.results))
    )
    return result.scalar_one()


@router.patch("/{run_id}", response_model=TestRunResponse)
async def update_test_run(
    run_id: str,
    data: TestRunUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    run = await _get_authorized_test_run(run_id, user, db)
    updates = data.model_dump(exclude_unset=True)
    if "status" in updates:
        run.status = updates["status"]
    if "overall_verdict" in updates:
        run.overall_verdict = updates["overall_verdict"]
    if "progress_pct" in updates:
        run.progress_pct = updates["progress_pct"]
    if "completed_tests" in updates:
        run.completed_tests = updates["completed_tests"]
    if "passed_tests" in updates:
        run.passed_tests = updates["passed_tests"]
    if "failed_tests" in updates:
        run.failed_tests = updates["failed_tests"]
    if "advisory_tests" in updates:
        run.advisory_tests = updates["advisory_tests"]
    if "na_tests" in updates:
        run.na_tests = updates["na_tests"]
    if "synopsis" in updates:
        run.synopsis = updates["synopsis"]
    if "synopsis_status" in updates:
        run.synopsis_status = updates["synopsis_status"]
    await db.flush()
    await db.refresh(run)
    return run


@router.post("/{run_id}/start")
async def start_test_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    run = await _get_authorized_test_run(run_id, user, db)

    if run.status not in (TestRunStatus.PENDING, TestRunStatus.FAILED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot start run in '{run.status.value}' status. Must be 'pending' or 'failed'.",
        )

    if run_id in _running_tasks and not _running_tasks[run_id].done():
        raise HTTPException(status_code=409, detail="Test run is already executing")

    task = asyncio.create_task(test_engine.run(run_id))
    _running_tasks[run_id] = task

    task.add_done_callback(lambda t: _running_tasks.pop(run_id, None))

    return {"status": "running", "message": "Test execution started", "run_id": run_id}


@router.post("/{run_id}/pause")
async def pause_test_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    run = await _get_authorized_test_run(run_id, user, db)

    if run.status != TestRunStatus.RUNNING:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot pause run in '{run.status.value}' status. Must be 'running'.",
        )

    run.status = TestRunStatus.PAUSED
    await db.flush()
    await db.refresh(run)

    return {"status": "paused", "message": "Test execution paused", "run_id": run_id}


@router.post("/{run_id}/resume")
async def resume_test_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    run = await _get_authorized_test_run(run_id, user, db)

    if run.status != TestRunStatus.PAUSED:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resume run in '{run.status.value}' status. Must be 'paused'.",
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

    results = await db.execute(select(TestResult).where(TestResult.test_run_id == run_id))
    all_results = results.scalars().all()

    passed = sum(1 for r in all_results if r.verdict == TestVerdict.PASS)
    failed = sum(1 for r in all_results if r.verdict == TestVerdict.FAIL)
    advisory = sum(1 for r in all_results if r.verdict == TestVerdict.ADVISORY)
    na = sum(1 for r in all_results if r.verdict == TestVerdict.NA)

    essential_failed = any(
        r for r in all_results
        if r.verdict == TestVerdict.FAIL and r.is_essential == "yes"
    )

    run.completed_tests = passed + failed + advisory + na
    run.passed_tests = passed
    run.failed_tests = failed
    run.advisory_tests = advisory
    run.na_tests = na
    run.progress_pct = 100.0
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

    await db.flush()
    await db.refresh(run)
    return run


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
