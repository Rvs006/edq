"""Scan Scheduler — asyncio-based background scheduler for recurring device scans.

Uses asyncio tasks instead of APScheduler to avoid adding external dependencies.
Checks for due schedules every 60 seconds and triggers test runs automatically.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import async_session
from app.models.scan_schedule import ScanSchedule, ScheduleFrequency
from app.models.test_run import TestRun, TestRunStatus
from app.models.test_result import TestResult, TestTier
from app.models.test_template import TestTemplate
from app.services.test_library import get_test_by_id

logger = logging.getLogger("edq.scheduler")

_scheduler_task: asyncio.Task | None = None

CHECK_INTERVAL_SECONDS = 60


def compute_next_run(frequency: ScheduleFrequency, from_time: datetime) -> datetime:
    """Compute the next run time based on frequency."""
    if frequency == ScheduleFrequency.DAILY:
        return from_time + timedelta(days=1)
    elif frequency == ScheduleFrequency.WEEKLY:
        return from_time + timedelta(weeks=1)
    elif frequency == ScheduleFrequency.MONTHLY:
        return from_time + timedelta(days=30)
    return from_time + timedelta(days=1)


def compute_diff(old_results: list[dict], new_results: list[dict]) -> dict:
    """Compare two sets of test results and produce a diff summary.

    Returns a dict with:
    - new_findings: tests that newly failed
    - resolved: tests that previously failed but now pass
    - changed: tests where verdict changed
    - unchanged_count: number of tests with same verdict
    """
    old_map: dict[str, str] = {}
    for r in old_results:
        test_id = r.get("test_id", "")
        verdict = r.get("verdict", "")
        if test_id:
            old_map[test_id] = verdict

    new_map: dict[str, str] = {}
    for r in new_results:
        test_id = r.get("test_id", "")
        verdict = r.get("verdict", "")
        if test_id:
            new_map[test_id] = verdict

    new_findings: list[dict[str, str]] = []
    resolved: list[dict[str, str]] = []
    changed: list[dict[str, str]] = []
    unchanged_count = 0

    all_test_ids = set(old_map.keys()) | set(new_map.keys())
    for tid in sorted(all_test_ids):
        old_v = old_map.get(tid)
        new_v = new_map.get(tid)

        if old_v is None and new_v is not None:
            new_findings.append({"test_id": tid, "verdict": new_v})
        elif old_v is not None and new_v is None:
            continue  # test removed from template
        elif old_v == new_v:
            unchanged_count += 1
        else:
            if old_v == "fail" and new_v in ("pass", "advisory", "n/a"):
                resolved.append({"test_id": tid, "old": old_v, "new": new_v})
            elif new_v == "fail" and old_v in ("pass", "advisory", "n/a"):
                new_findings.append({"test_id": tid, "verdict": new_v, "was": old_v})
            else:
                changed.append({"test_id": tid, "old": old_v, "new": new_v})

    return {
        "new_findings": new_findings,
        "resolved": resolved,
        "changed": changed,
        "unchanged_count": unchanged_count,
        "total_compared": len(all_test_ids),
    }


async def _get_previous_results(db: AsyncSession, device_id: str, template_id: str) -> list[dict]:
    """Get results from the most recent completed test run for a device/template pair."""
    stmt = (
        select(TestRun)
        .where(
            and_(
                TestRun.device_id == device_id,
                TestRun.template_id == template_id,
                TestRun.status == TestRunStatus.COMPLETED,
            )
        )
        .order_by(TestRun.completed_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    prev_run = result.scalar_one_or_none()
    if not prev_run:
        return []

    results_stmt = select(TestResult).where(TestResult.test_run_id == prev_run.id)
    results = await db.execute(results_stmt)
    return [
        {"test_id": r.test_id, "verdict": r.verdict}
        for r in results.scalars().all()
    ]


async def _execute_scheduled_scan(schedule_id: str) -> None:
    """Execute a single scheduled scan and compute diff with previous results."""
    async with async_session() as db:
        try:
            # Re-query the schedule in this session so changes are tracked
            result = await db.execute(
                select(ScanSchedule).where(ScanSchedule.id == schedule_id)
            )
            schedule = result.scalar_one_or_none()
            if not schedule or not schedule.is_active:
                return

            # Get previous results for diff comparison
            prev_results = await _get_previous_results(
                db, schedule.device_id, schedule.template_id
            )

            # Load template to get test IDs
            tmpl_result = await db.execute(
                select(TestTemplate).where(TestTemplate.id == schedule.template_id)
            )
            template = tmpl_result.scalar_one_or_none()
            if not template:
                logger.warning("Template %s not found for schedule %s", schedule.template_id, schedule_id)
                return

            # Create a new test run with total_tests
            new_run = TestRun(
                device_id=schedule.device_id,
                template_id=schedule.template_id,
                engineer_id=schedule.created_by,
                status=TestRunStatus.PENDING,
                connection_scenario="direct",
                total_tests=len(template.test_ids),
            )
            db.add(new_run)
            await db.flush()

            # Create TestResult entries for each test in the template
            for test_id in template.test_ids:
                test_def = get_test_by_id(test_id)
                if test_def:
                    tr = TestResult(
                        test_run_id=new_run.id,
                        test_id=test_id,
                        test_name=test_def["name"],
                        tier=TestTier(test_def["tier"]),
                        tool=test_def.get("tool"),
                        is_essential="yes" if test_def["is_essential"] else "no",
                        compliance_map=test_def.get("compliance_map", []),
                    )
                    db.add(tr)

            # Update schedule metadata
            now = datetime.now(timezone.utc)
            schedule.last_run_at = now
            schedule.run_count += 1
            schedule.next_run_at = compute_next_run(schedule.frequency, now)

            # Deactivate if max_runs reached
            if schedule.max_runs and schedule.run_count >= schedule.max_runs:
                schedule.is_active = False

            if prev_results:
                schedule.diff_summary = {
                    "status": "pending",
                    "previous_result_count": len(prev_results),
                }

            await db.commit()

            logger.info(
                "Scheduled scan triggered: schedule=%s device=%s run=%s",
                schedule.id, schedule.device_id, new_run.id,
            )

        except Exception:
            logger.exception("Failed to execute scheduled scan %s", schedule_id)
            await db.rollback()


async def _check_due_schedules() -> None:
    """Check for schedules that are due and execute them."""
    async with async_session() as db:
        now = datetime.now(timezone.utc)
        stmt = select(ScanSchedule).where(
            and_(
                ScanSchedule.is_active.is_(True),
                ScanSchedule.next_run_at <= now,
            )
        )
        result = await db.execute(stmt)
        due_schedules = result.scalars().all()

        for schedule in due_schedules:
            await _execute_scheduled_scan(schedule.id)


async def _scheduler_loop() -> None:
    """Main scheduler loop — runs indefinitely checking for due schedules."""
    logger.info("Scan scheduler started (interval=%ds)", CHECK_INTERVAL_SECONDS)
    while True:
        try:
            await _check_due_schedules()
        except Exception:
            logger.exception("Error in scheduler loop")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


def start_scheduler() -> None:
    """Start the background scheduler task."""
    global _scheduler_task
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(_scheduler_loop())
        logger.info("Scan scheduler task created")


def stop_scheduler() -> None:
    """Stop the background scheduler task."""
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        logger.info("Scan scheduler task cancelled")
        _scheduler_task = None
