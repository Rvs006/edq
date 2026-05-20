from app.models.test_run import TestRunStatus
from app.services.test_run_lifecycle import (
    can_cancel_run,
    can_flag_cable_issue,
    can_pause_run,
    can_resume_run,
    can_start_run,
)


def test_lifecycle_predicates_accept_canonical_status_groups():
    assert can_start_run(TestRunStatus.PENDING)
    assert can_start_run("failed")
    assert can_start_run("cancelled")
    assert not can_start_run("running")

    assert can_cancel_run("syncing")
    assert can_cancel_run("paused_cable")
    assert not can_cancel_run("completed")

    assert can_pause_run("running")
    assert not can_pause_run("paused_manual")

    assert can_resume_run("paused")
    assert can_resume_run("paused_cable")
    assert not can_resume_run("pending")

    assert can_flag_cable_issue("running")
    assert can_flag_cable_issue("awaiting_manual")
    assert not can_flag_cable_issue("completed")
