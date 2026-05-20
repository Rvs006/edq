"""Lifecycle predicates for test run orchestration."""

from __future__ import annotations

from app.models.test_run import TestRunStatus, normalize_test_run_status

STARTABLE_STATUSES = {
    TestRunStatus.PENDING.value,
    TestRunStatus.FAILED.value,
    TestRunStatus.CANCELLED.value,
}

CANCELLABLE_STATUSES = {
    TestRunStatus.RUNNING.value,
    TestRunStatus.SELECTING_INTERFACE.value,
    TestRunStatus.SYNCING.value,
    TestRunStatus.PAUSED_MANUAL.value,
    TestRunStatus.PAUSED_CABLE.value,
}

PAUSABLE_STATUSES = {
    TestRunStatus.RUNNING.value,
}

RESUMABLE_STATUSES = {
    TestRunStatus.PAUSED_MANUAL.value,
    TestRunStatus.PAUSED_CABLE.value,
}

def can_start_run(status: TestRunStatus | str | None) -> bool:
    return normalize_test_run_status(status) in STARTABLE_STATUSES


def can_cancel_run(status: TestRunStatus | str | None) -> bool:
    return normalize_test_run_status(status) in CANCELLABLE_STATUSES


def can_pause_run(status: TestRunStatus | str | None) -> bool:
    return normalize_test_run_status(status) in PAUSABLE_STATUSES


def can_resume_run(status: TestRunStatus | str | None) -> bool:
    return normalize_test_run_status(status) in RESUMABLE_STATUSES


def can_flag_cable_issue(status: TestRunStatus | str | None) -> bool:
    return normalize_test_run_status(status) in {
        TestRunStatus.RUNNING.value,
        TestRunStatus.AWAITING_MANUAL.value,
    }
