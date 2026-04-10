"""Shared launcher for background test-run execution tasks."""

import asyncio
import logging

from app.services.test_engine import test_engine

logger = logging.getLogger(__name__)

_running_tasks: dict[str, asyncio.Task] = {}


def is_run_executing(run_id: str) -> bool:
    task = _running_tasks.get(run_id)
    return bool(task and not task.done())


def launch_test_run(run_id: str, test_plan_id: str | None = None) -> asyncio.Task | None:
    """Start a test engine task for a run. Returns None if already running."""
    if is_run_executing(run_id):
        logger.warning("Test run %s already executing — ignoring duplicate launch", run_id)
        return None

    task = asyncio.create_task(test_engine.run(run_id, test_plan_id))
    _running_tasks[run_id] = task
    task.add_done_callback(lambda _: _running_tasks.pop(run_id, None))
    return task


def cancel_test_run(run_id: str) -> bool:
    """Cancel an in-flight execution task."""
    task = _running_tasks.get(run_id)
    if not task or task.done():
        return False
    task.cancel()
    return True
