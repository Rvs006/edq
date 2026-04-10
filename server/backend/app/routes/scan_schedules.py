"""Scan Schedule routes — manage recurring device re-scans."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone

from app.models.database import get_db
from app.models.scan_schedule import ScanSchedule, ScheduleFrequency
from app.models.device import Device
from app.models.test_template import TestTemplate
from app.models.user import User
from app.security.auth import get_current_active_user, require_role
from app.services.scan_scheduler import compute_next_run, compute_diff
from app.utils.audit import log_action
from app.utils.datetime import utcnow_naive

router = APIRouter()


class ScheduleCreate(BaseModel):
    device_id: str
    template_id: str
    frequency: ScheduleFrequency
    max_runs: Optional[int] = Field(None, ge=1)


class ScheduleUpdate(BaseModel):
    frequency: Optional[ScheduleFrequency] = None
    is_active: Optional[bool] = None
    max_runs: Optional[int] = Field(None, ge=1)


class ScheduleResponse(BaseModel):
    id: str
    device_id: str
    template_id: str
    created_by: str
    frequency: ScheduleFrequency
    is_active: bool
    last_run_at: Optional[datetime] = None
    next_run_at: datetime
    run_count: int
    max_runs: Optional[int] = None
    diff_summary: Optional[dict] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DiffResponse(BaseModel):
    new_findings: list
    resolved: list
    changed: list
    unchanged_count: int
    total_compared: int


@router.get("/", response_model=List[ScheduleResponse])
async def list_schedules(
    device_id: Optional[str] = None,
    is_active: Optional[bool] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """List all scan schedules, optionally filtered by device or status."""
    query = select(ScanSchedule)
    if device_id:
        query = query.where(ScanSchedule.device_id == device_id)
    if is_active is not None:
        query = query.where(ScanSchedule.is_active == is_active)
    result = await db.execute(
        query.order_by(ScanSchedule.next_run_at).offset(skip).limit(limit)
    )
    return result.scalars().all()


@router.post("/", response_model=ScheduleResponse, status_code=201)
async def create_schedule(
    data: ScheduleCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["admin", "reviewer"])),
):
    """Create a new scan schedule for a device."""
    # Validate device exists
    device = await db.execute(select(Device).where(Device.id == data.device_id))
    if not device.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Device not found")

    # Validate template exists
    template = await db.execute(
        select(TestTemplate).where(TestTemplate.id == data.template_id)
    )
    if not template.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Test template not found")

    now = utcnow_naive()
    next_run = compute_next_run(data.frequency, now)

    schedule = ScanSchedule(
        device_id=data.device_id,
        template_id=data.template_id,
        created_by=user.id,
        frequency=data.frequency,
        next_run_at=next_run,
        max_runs=data.max_runs,
    )
    db.add(schedule)
    await db.flush()
    await db.refresh(schedule)
    await log_action(
        db, user, "create", "scan_schedule", schedule.id,
        {"device_id": data.device_id, "frequency": data.frequency.value},
        request,
    )
    return schedule


@router.get("/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(
    schedule_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """Get a specific scan schedule."""
    result = await db.execute(
        select(ScanSchedule).where(ScanSchedule.id == schedule_id)
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return schedule


@router.patch("/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    schedule_id: str,
    data: ScheduleUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["admin", "reviewer"])),
):
    """Update a scan schedule."""
    result = await db.execute(
        select(ScanSchedule).where(ScanSchedule.id == schedule_id)
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    updates = data.model_dump(exclude_unset=True)
    if "frequency" in updates:
        schedule.frequency = updates["frequency"]
        schedule.next_run_at = compute_next_run(
            schedule.frequency, utcnow_naive()
        )
    if "is_active" in updates:
        schedule.is_active = updates["is_active"]
    if "max_runs" in updates:
        schedule.max_runs = updates["max_runs"]

    await db.flush()
    await db.refresh(schedule)
    await log_action(
        db, user, "update", "scan_schedule", schedule_id,
        {"fields": list(updates.keys())}, request,
    )
    return schedule


@router.delete("/{schedule_id}", status_code=204)
async def delete_schedule(
    schedule_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["admin"])),
):
    """Delete a scan schedule."""
    result = await db.execute(
        select(ScanSchedule).where(ScanSchedule.id == schedule_id)
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    await db.delete(schedule)
    await log_action(
        db, user, "delete", "scan_schedule", schedule_id,
        {"device_id": schedule.device_id}, request,
    )


@router.get("/{schedule_id}/diff", response_model=DiffResponse)
async def get_schedule_diff(
    schedule_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """Get the diff between the two most recent scans for this schedule's device/template."""
    result = await db.execute(
        select(ScanSchedule).where(ScanSchedule.id == schedule_id)
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    # If we have a cached diff summary, return it
    if schedule.diff_summary and schedule.diff_summary.get("status") != "pending":
        return schedule.diff_summary

    # Compute fresh diff from the two most recent completed runs
    from app.models.test_run import TestRun, TestRunStatus
    from app.models.test_result import TestResult
    from sqlalchemy import and_

    stmt = (
        select(TestRun)
        .where(
            and_(
                TestRun.device_id == schedule.device_id,
                TestRun.template_id == schedule.template_id,
                TestRun.status == TestRunStatus.COMPLETED,
            )
        )
        .order_by(TestRun.completed_at.desc())
        .limit(2)
    )
    runs_result = await db.execute(stmt)
    runs = runs_result.scalars().all()

    if len(runs) < 2:
        return {
            "new_findings": [],
            "resolved": [],
            "changed": [],
            "unchanged_count": 0,
            "total_compared": 0,
        }

    # Get results for both runs
    async def get_results(run_id: str) -> list[dict]:
        res = await db.execute(
            select(TestResult).where(TestResult.test_run_id == run_id)
        )
        return [{"test_id": r.test_id, "verdict": r.verdict} for r in res.scalars().all()]

    new_results = await get_results(runs[0].id)
    old_results = await get_results(runs[1].id)

    diff = compute_diff(old_results, new_results)

    # Cache the diff
    schedule.diff_summary = diff
    await db.flush()

    return diff
