"""Shared launcher for background test-run execution tasks."""

import asyncio
import logging

from app.services.test_engine import test_engine

logger = logging.getLogger(__name__)

_running_tasks: dict[str, asyncio.Task] = {}

# Limit the number of test runs executing concurrently to prevent resource exhaustion.
MAX_CONCURRENT_RUNS = 10
_run_semaphore = asyncio.Semaphore(MAX_CONCURRENT_RUNS)


async def _guarded_run(run_id: str, test_plan_id: str | None) -> None:
    """Acquire the concurrency semaphore, then delegate to the engine."""
    async with _run_semaphore:
        await test_engine.run(run_id, test_plan_id)


def is_run_executing(run_id: str) -> bool:
    task = _running_tasks.get(run_id)
    return bool(task and not task.done())


def launch_test_run(run_id: str, test_plan_id: str | None = None) -> asyncio.Task | None:
    """Start a test engine task for a run. Returns None if already running."""
    if is_run_executing(run_id):
        logger.warning("Test run %s already executing — ignoring duplicate launch", run_id)
        return None

    task = asyncio.create_task(_guarded_run(run_id, test_plan_id))
    _running_tasks[run_id] = task

    def _cleanup(task, rid=run_id):
        _running_tasks.pop(rid, None)

    task.add_done_callback(_cleanup)
    return task


def cancel_test_run(run_id: str) -> bool:
    """Cancel an in-flight execution task."""
    task = _running_tasks.get(run_id)
    if not task or task.done():
        return False
    task.cancel()
    return True
