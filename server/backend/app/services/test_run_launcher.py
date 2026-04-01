"""Shared launcher for background test-run execution tasks."""

import asyncio

from app.services.test_engine import test_engine

_running_tasks: dict[str, asyncio.Task] = {}


def is_run_executing(run_id: str) -> bool:
    task = _running_tasks.get(run_id)
    return bool(task and not task.done())


def launch_test_run(run_id: str, test_plan_id: str | None = None) -> asyncio.Task:
    """Start a test engine task for a run and track it until completion."""
    if is_run_executing(run_id):
        raise RuntimeError("Test run is already executing")

    task = asyncio.create_task(test_engine.run(run_id, test_plan_id))
    _running_tasks[run_id] = task
    task.add_done_callback(lambda _: _running_tasks.pop(run_id, None))
    return task


def cancel_test_run(run_id: str) -> bool:
    """Cancel an in-flight execution task if it exists."""
    task = _running_tasks.get(run_id)
    if not task or task.done():
        return False
    task.cancel()
    return True
