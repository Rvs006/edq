"""Test Run management routes."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from datetime import datetime, timezone

from app.models.database import get_db
from app.models.test_run import TestRun, TestRunStatus
from app.models.test_result import TestResult, TestVerdict, TestTier
from app.models.test_template import TestTemplate
from app.models.device import Device
from app.models.user import User
from app.schemas.test import TestRunCreate, TestRunUpdate, TestRunResponse
from app.security.auth import get_current_active_user
from app.services.test_library import get_test_by_id

router = APIRouter()


@router.get("/", response_model=List[TestRunResponse])
async def list_test_runs(
    device_id: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    query = select(TestRun)
    if device_id:
        query = query.where(TestRun.device_id == device_id)
    if status:
        query = query.where(TestRun.status == status)
    result = await db.execute(query.order_by(TestRun.created_at.desc()).offset(skip).limit(limit))
    return result.scalars().all()


@router.get("/stats")
async def test_run_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    total = await db.execute(select(func.count(TestRun.id)))
    by_status = await db.execute(
        select(TestRun.status, func.count(TestRun.id)).group_by(TestRun.status)
    )
    by_verdict = await db.execute(
        select(TestRun.overall_verdict, func.count(TestRun.id))
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
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    # Validate device exists
    device = await db.execute(select(Device).where(Device.id == data.device_id))
    if not device.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Device not found")

    # Validate template exists
    template_result = await db.execute(select(TestTemplate).where(TestTemplate.id == data.template_id))
    template = template_result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Create test run
    test_run = TestRun(
        device_id=data.device_id,
        template_id=data.template_id,
        engineer_id=user.id,
        agent_id=data.agent_id,
        total_tests=len(template.test_ids),
        status=TestRunStatus.PENDING,
        metadata=data.metadata,
    )
    db.add(test_run)
    await db.flush()

    # Create individual test results for each test in the template
    for test_id in template.test_ids:
        test_def = get_test_by_id(test_id)
        if test_def:
            result = TestResult(
                test_run_id=test_run.id,
                test_id=test_id,
                test_name=test_def["name"],
                tier=TestTier(test_def["tier"]),
                tool=test_def.get("tool"),
                is_essential="yes" if test_def["is_essential"] else "no",
                compliance_map=test_def.get("compliance_map", []),
            )
            db.add(result)

    await db.flush()
    await db.refresh(test_run)
    return test_run


@router.get("/{run_id}", response_model=TestRunResponse)
async def get_test_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    result = await db.execute(select(TestRun).where(TestRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Test run not found")
    return run


@router.patch("/{run_id}", response_model=TestRunResponse)
async def update_test_run(
    run_id: str,
    data: TestRunUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    result = await db.execute(select(TestRun).where(TestRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Test run not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(run, field, value)
    await db.flush()
    await db.refresh(run)
    return run


@router.post("/{run_id}/start", response_model=TestRunResponse)
async def start_test_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    result = await db.execute(select(TestRun).where(TestRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Test run not found")
    run.status = TestRunStatus.RUNNING
    run.started_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(run)
    return run


@router.post("/{run_id}/complete", response_model=TestRunResponse)
async def complete_test_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    result = await db.execute(select(TestRun).where(TestRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Test run not found")

    # Calculate verdict from results
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
        run.overall_verdict = "advisory"
    else:
        run.overall_verdict = "pass"

    await db.flush()
    await db.refresh(run)
    return run
