"""Test Result routes — per-test verdicts with findings."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional

from app.models.database import get_db
from app.models.test_result import TestResult
from app.models.user import User
from app.schemas.test import TestResultCreate, TestResultUpdate, TestResultResponse
from app.security.auth import get_current_active_user
from app.utils.sanitize import sanitize_dict
from app.utils.audit import log_action

router = APIRouter()


@router.get("/", response_model=List[TestResultResponse])
async def list_results(
    test_run_id: Optional[str] = None,
    verdict: Optional[str] = None,
    tier: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    query = select(TestResult)
    if test_run_id:
        query = query.where(TestResult.test_run_id == test_run_id)
    if verdict:
        query = query.where(TestResult.verdict == verdict)
    if tier:
        query = query.where(TestResult.tier == tier)
    result = await db.execute(query.order_by(TestResult.test_id).offset(skip).limit(limit))
    return result.scalars().all()


@router.get("/{result_id}", response_model=TestResultResponse)
async def get_result(
    result_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    result = await db.execute(select(TestResult).where(TestResult.id == result_id))
    test_result = result.scalar_one_or_none()
    if not test_result:
        raise HTTPException(status_code=404, detail="Test result not found")
    return test_result


@router.patch("/{result_id}", response_model=TestResultResponse)
async def update_result(
    result_id: str,
    data: TestResultUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    result = await db.execute(select(TestResult).where(TestResult.id == result_id))
    test_result = result.scalar_one_or_none()
    if not test_result:
        raise HTTPException(status_code=404, detail="Test result not found")
    updates = sanitize_dict(data.model_dump(exclude_unset=True), ["comment", "comment_override", "engineer_notes"])
    if "verdict" in updates:
        test_result.verdict = updates["verdict"]
    if "comment" in updates:
        test_result.comment = updates["comment"]
    if "comment_override" in updates:
        test_result.comment_override = updates["comment_override"]
    if "engineer_notes" in updates:
        test_result.engineer_notes = updates["engineer_notes"]
    if "raw_output" in updates:
        test_result.raw_output = updates["raw_output"]
    if "parsed_data" in updates:
        test_result.parsed_data = updates["parsed_data"]
    if "findings" in updates:
        test_result.findings = updates["findings"]
    if "evidence_files" in updates:
        test_result.evidence_files = updates["evidence_files"]
    if "duration_seconds" in updates:
        test_result.duration_seconds = updates["duration_seconds"]
    await db.flush()
    await db.refresh(test_result)
    await log_action(db, user, "update", "test_result", result_id, {"fields": list(updates.keys())}, request)
    return test_result


@router.post("/batch", response_model=List[TestResultResponse])
async def batch_update_results(
    updates: List[TestResultCreate],
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """Batch create/update test results (used by agents)."""
    created = []
    for data in updates:
        result = TestResult(**data.model_dump())
        db.add(result)
        created.append(result)
    await db.flush()
    for r in created:
        await db.refresh(r)
    return created
