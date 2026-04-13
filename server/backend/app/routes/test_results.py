"""Test Result routes with run-aware authorization and reviewer overrides."""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func, case, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.models.test_result import TestResult, TestTier, TestVerdict
from app.models.test_run import TestRun, TestRunStatus, normalize_test_run_status
from app.models.user import User, UserRole
from app.routes.test_runs import _get_authorized_test_run
from app.services.run_readiness import (
    build_run_readiness_summary,
    merge_readiness_into_metadata,
)
from app.schemas.test import (
    TestResultOverrideRequest,
    TestResultResponse,
    TestResultUpdate,
)
from app.security.auth import get_current_active_user, require_role
from app.utils.audit import log_action
from app.utils.datetime import utcnow_naive
from app.utils.sanitize import sanitize_dict

router = APIRouter()


async def _get_authorized_result(
    result_id: str,
    user: User,
    db: AsyncSession,
) -> tuple[TestResult, TestRun]:
    query = (
        select(TestResult, TestRun)
        .join(TestRun, TestRun.id == TestResult.test_run_id)
        .where(TestResult.id == result_id)
    )
    result = await db.execute(query)
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Test result not found")

    test_result, test_run = row
    if user.role == UserRole.ENGINEER and test_run.engineer_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return test_result, test_run


def _parse_verdict(value: str) -> TestVerdict:
    try:
        return TestVerdict(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Unsupported verdict '{value}'") from exc


def _overall_verdict(passed: int, failed: int, advisory: int, essential_failed: bool) -> str | None:
    if essential_failed or failed:
        return "fail"
    if advisory:
        return "qualified_pass"
    if passed:
        return "pass"
    return None


async def _refresh_parent_run(db: AsyncSession, run: TestRun) -> None:
    result = await db.execute(
        select(TestResult).where(TestResult.test_run_id == run.id).order_by(TestResult.test_id)
    )
    all_results = list(result.scalars().all())

    passed = sum(1 for item in all_results if item.verdict == TestVerdict.PASS)
    failed = sum(1 for item in all_results if item.verdict == TestVerdict.FAIL)
    advisory = sum(1 for item in all_results if item.verdict == TestVerdict.ADVISORY)
    na = sum(1 for item in all_results if item.verdict == TestVerdict.NA)
    errors = sum(1 for item in all_results if item.verdict == TestVerdict.ERROR)
    pending_manual = sum(
        1
        for item in all_results
        if item.verdict == TestVerdict.PENDING and item.tier == TestTier.GUIDED_MANUAL
    )
    essential_failed = any(
        item
        for item in all_results
        if item.verdict == TestVerdict.FAIL and item.is_essential == "yes"
    )

    run.passed_tests = passed
    run.failed_tests = failed
    run.advisory_tests = advisory
    run.na_tests = na
    run.completed_tests = passed + failed + advisory + na + errors
    if run.total_tests:
        run.progress_pct = round((run.completed_tests / run.total_tests) * 100, 1)

    current_status = normalize_test_run_status(run.status)
    active_statuses = {
        TestRunStatus.PENDING.value,
        TestRunStatus.SELECTING_INTERFACE.value,
        TestRunStatus.SYNCING.value,
        TestRunStatus.RUNNING.value,
        TestRunStatus.PAUSED_MANUAL.value,
        TestRunStatus.PAUSED_CABLE.value,
        TestRunStatus.CANCELLED.value,
        TestRunStatus.FAILED.value,
    }
    if current_status in active_statuses:
        pass
    elif pending_manual:
        run.status = TestRunStatus.AWAITING_MANUAL
        run.completed_at = None
        run.overall_verdict = None
    elif current_status == TestRunStatus.AWAITING_REVIEW.value:
        run.status = TestRunStatus.AWAITING_REVIEW
    else:
        run.status = TestRunStatus.COMPLETED

    if current_status not in active_statuses and run.completed_at is None:
        run.completed_at = utcnow_naive()
    if current_status not in active_statuses:
        run.overall_verdict = _overall_verdict(passed, failed, advisory, essential_failed)

    run.run_metadata = merge_readiness_into_metadata(
        run.run_metadata,
        build_run_readiness_summary(run, all_results),
    )


@router.get("/", response_model=List[TestResultResponse])
async def list_results(
    test_run_id: Optional[str] = None,
    verdict: Optional[str] = None,
    tier: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    query = select(TestResult)

    if user.role == UserRole.ENGINEER:
        query = query.join(TestRun, TestRun.id == TestResult.test_run_id)
        if test_run_id:
            await _get_authorized_test_run(test_run_id, user, db)
        query = query.where(TestRun.engineer_id == user.id)

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
    user: User = Depends(get_current_active_user),
):
    test_result, _ = await _get_authorized_result(result_id, user, db)
    return test_result


@router.patch("/{result_id}", response_model=TestResultResponse)
async def update_result(
    result_id: str,
    data: TestResultUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    test_result, test_run = await _get_authorized_result(result_id, user, db)
    updates = sanitize_dict(
        data.model_dump(exclude_unset=True),
        ["comment", "comment_override", "engineer_notes"],
    )

    if user.role in {UserRole.ADMIN, UserRole.REVIEWER} and "verdict" in updates:
        # Allow admin/reviewer to submit verdicts on manual tests (guided_manual)
        # but require the override endpoint for changing automatic test verdicts
        tier_raw = test_result.tier.value if hasattr(test_result.tier, "value") else str(test_result.tier)
        if tier_raw != "guided_manual":
            raise HTTPException(
                status_code=400,
                detail="Reviewers and admins must use the override endpoint to change verdicts on automatic tests",
            )

    if "verdict" in updates:
        test_result.verdict = _parse_verdict(updates["verdict"])
        if test_result.started_at is None:
            test_result.started_at = utcnow_naive()
        test_result.completed_at = (
            None if test_result.verdict == TestVerdict.PENDING else utcnow_naive()
        )
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

    await _refresh_parent_run(db, test_run)
    await db.commit()
    await db.refresh(test_result)
    await log_action(db, user, "update", "test_result", result_id, {"fields": list(updates.keys())}, request)
    return test_result


@router.post("/{result_id}/override", response_model=TestResultResponse)
async def override_result(
    result_id: str,
    data: TestResultOverrideRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["reviewer", "admin"])),
):
    test_result, test_run = await _get_authorized_result(result_id, user, db)

    override_verdict = _parse_verdict(data.verdict)
    now = utcnow_naive()
    sanitized = sanitize_dict(
        {"comment": data.comment, "override_reason": data.override_reason},
        ["comment", "override_reason"],
    )

    test_result.verdict = override_verdict
    if "comment" in sanitized:
        test_result.comment = sanitized["comment"]
    test_result.override_reason = sanitized["override_reason"]
    test_result.override_verdict = override_verdict.value
    test_result.overridden_by_user_id = user.id
    test_result.overridden_by_username = user.full_name or user.username
    test_result.overridden_at = now
    if test_result.started_at is None:
        test_result.started_at = now
    test_result.completed_at = now

    await _refresh_parent_run(db, test_run)
    await db.commit()
    await db.refresh(test_result)
    await log_action(
        db,
        user,
        "override",
        "test_result",
        result_id,
        {
            "override_reason": test_result.override_reason,
            "override_verdict": test_result.override_verdict,
            "test_run_id": test_run.id,
        },
        request,
    )
    return test_result
