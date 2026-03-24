"""Test Result routes — per-test verdicts with findings."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional

from app.models.database import get_db
from app.models.test_result import TestResult
from app.models.user import User
from app.schemas.test import TestResultCreate, TestResultUpdate, TestResultResponse
from app.security.auth import get_current_active_user

router = APIRouter()


@router.get("/", response_model=List[TestResultResponse])
async def list_results(
    test_run_id: Optional[str] = None,
    verdict: Optional[str] = None,
    tier: Optional[str] = None,
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
    result = await db.execute(query.order_by(TestResult.test_id))
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
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    result = await db.execute(select(TestResult).where(TestResult.id == result_id))
    test_result = result.scalar_one_or_none()
    if not test_result:
        raise HTTPException(status_code=404, detail="Test result not found")
    updates = data.model_dump(exclude_unset=True)
    if "verdict" in updates:
        test_result.verdict = updates["verdict"]
    if "comment" in updates:
        test_result.comment = updates["comment"]
    if "findings" in updates:
        test_result.findings = updates["findings"]
    if "raw_output" in updates:
        test_result.raw_output = updates["raw_output"]
    if "tier" in updates:
        test_result.tier = updates["tier"]
    await db.flush()
    await db.refresh(test_result)
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
