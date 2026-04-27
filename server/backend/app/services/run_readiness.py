"""Shared run readiness and trust-summary helpers."""

from __future__ import annotations

from typing import Any, Iterable

from app.models.test_run import TestRunStatus, normalize_test_run_status
from app.services.test_library import get_test_by_id

_ACTIVE_STATUSES = {
    TestRunStatus.PENDING.value,
    TestRunStatus.SELECTING_INTERFACE.value,
    TestRunStatus.SYNCING.value,
    TestRunStatus.RUNNING.value,
    TestRunStatus.PAUSED_MANUAL.value,
    TestRunStatus.PAUSED_CABLE.value,
}

_DEFAULT_TRUST_TIER_COUNTS = {
    "release_blocking": 0,
    "review_required": 0,
    "advisory": 0,
    "manual_evidence": 0,
}

_FAILURE_VERDICTS = {"fail", "error"}
_PENDING_VERDICTS = {"", "pending", "none"}


def _string(value: Any) -> str:
    if hasattr(value, "value"):
        value = value.value
    return "" if value is None else str(value)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _verdict(value: Any) -> str:
    return _string(value).strip().lower()


def _tier(value: Any) -> str:
    return _string(value).strip().lower()


def _trust_tier_counts(raw: Any) -> dict[str, int]:
    counts = dict(_DEFAULT_TRUST_TIER_COUNTS)
    if isinstance(raw, dict):
        for key in counts:
            counts[key] = _int(raw.get(key))
    return counts


def _trust_level_for_result(result: Any) -> str:
    test_id = _string(getattr(result, "test_id", "")).strip()
    definition = get_test_by_id(test_id) or {}
    trust_level = _string(definition.get("trust_level")).strip().lower()
    return trust_level if trust_level in _DEFAULT_TRUST_TIER_COUNTS else "advisory"


def summarize_results_for_readiness(results: Iterable[Any]) -> dict[str, Any]:
    trust_tier_counts = dict(_DEFAULT_TRUST_TIER_COUNTS)
    release_blocking_failure_count = 0
    review_required_issue_count = 0
    manual_evidence_pending_count = 0
    override_count = 0
    pending_manual_count = 0
    completed_result_count = 0
    failed_test_count = 0
    advisory_count = 0

    for result in results:
        verdict = _verdict(getattr(result, "verdict", None))
        tier = _tier(getattr(result, "tier", None))
        trust_level = _trust_level_for_result(result)
        trust_tier_counts[trust_level] += 1

        if verdict not in _PENDING_VERDICTS:
            completed_result_count += 1

        if tier == "guided_manual" and verdict in _PENDING_VERDICTS:
            pending_manual_count += 1

        if trust_level == "manual_evidence" and verdict in _PENDING_VERDICTS:
            manual_evidence_pending_count += 1

        if verdict in _FAILURE_VERDICTS:
            failed_test_count += 1
            if trust_level == "release_blocking":
                release_blocking_failure_count += 1
            elif trust_level == "review_required":
                review_required_issue_count += 1
        elif verdict == "advisory":
            advisory_count += 1
            if trust_level == "review_required":
                review_required_issue_count += 1

        if (
            bool(getattr(result, "is_overridden", False))
            or bool(getattr(result, "override_reason", None))
            or bool(getattr(result, "override_verdict", None))
        ):
            override_count += 1

    return {
        "trust_tier_counts": trust_tier_counts,
        "release_blocking_failure_count": release_blocking_failure_count,
        "review_required_issue_count": review_required_issue_count,
        "manual_evidence_pending_count": manual_evidence_pending_count,
        "override_count": override_count,
        "pending_manual_count": pending_manual_count,
        "completed_result_count": completed_result_count,
        "failed_test_count": failed_test_count,
        "advisory_count": advisory_count,
    }


def _readiness_snapshot_from_metadata(run: Any) -> dict[str, Any]:
    metadata = getattr(run, "run_metadata", None)
    metadata = metadata if isinstance(metadata, dict) else {}
    snapshot = metadata.get("readiness_summary")
    snapshot = snapshot if isinstance(snapshot, dict) else {}

    return {
        "trust_tier_counts": _trust_tier_counts(
            snapshot.get("trust_tier_counts") or metadata.get("trust_tier_counts")
        ),
        "release_blocking_failure_count": _int(snapshot.get("release_blocking_failure_count")),
        "review_required_issue_count": _int(snapshot.get("review_required_issue_count")),
        "manual_evidence_pending_count": _int(
            snapshot.get(
                "manual_evidence_pending_count",
                snapshot.get(
                    "pending_manual_count",
                    metadata.get("pending_manual_count"),
                ),
            )
        ),
        "override_count": _int(snapshot.get("override_count")),
        "pending_manual_count": _int(
            snapshot.get("pending_manual_count", metadata.get("pending_manual_count"))
        ),
        "completed_result_count": _int(
            snapshot.get("completed_result_count", metadata.get("completed_result_count"))
        ),
        "failed_test_count": _int(
            snapshot.get("failed_test_count", getattr(run, "failed_tests", 0))
        ),
        "advisory_count": _int(
            snapshot.get("advisory_count", getattr(run, "advisory_tests", 0))
        ),
    }


def _score_readiness(
    *,
    total_result_count: int,
    completed_result_count: int,
    pending_manual_count: int,
    release_blocking_failure_count: int,
    review_required_issue_count: int,
    advisory_count: int,
    override_count: int,
    status: str,
) -> int:
    if total_result_count <= 0:
        return 1

    score = 10.0
    incomplete_count = max(total_result_count - completed_result_count, 0)
    score -= min(4.0, (incomplete_count / total_result_count) * 4.0)

    if status in _ACTIVE_STATUSES:
        score -= 1.0
    if status == TestRunStatus.AWAITING_REVIEW.value:
        score -= 1.0

    score -= min(3.0, float(pending_manual_count))
    score -= min(4.0, float(release_blocking_failure_count) * 3.0)
    score -= min(3.0, float(review_required_issue_count) * 2.0)
    score -= min(2.0, float(advisory_count))
    score -= min(1.0, float(override_count))

    return max(1, min(10, round(score)))


def build_run_readiness_summary(
    run: Any,
    results: Iterable[Any] | None = None,
) -> dict[str, Any]:
    status = normalize_test_run_status(getattr(run, "status", None))
    snapshot = (
        summarize_results_for_readiness(results)
        if results is not None
        else _readiness_snapshot_from_metadata(run)
    )

    total_result_count = _int(
        getattr(run, "total_tests", 0),
        default=_int(snapshot.get("completed_result_count")),
    )
    completed_result_count = max(
        _int(snapshot.get("completed_result_count")),
        _int(getattr(run, "completed_tests", 0)),
    )
    failed_test_count = max(
        _int(snapshot.get("failed_test_count")),
        _int(getattr(run, "failed_tests", 0)),
    )
    advisory_count = max(
        _int(snapshot.get("advisory_count")),
        _int(getattr(run, "advisory_tests", 0)),
    )
    pending_manual_count = max(
        _int(snapshot.get("pending_manual_count")),
        _int(snapshot.get("manual_evidence_pending_count")),
    )
    release_blocking_failure_count = _int(snapshot.get("release_blocking_failure_count"))
    review_required_issue_count = _int(snapshot.get("review_required_issue_count"))
    override_count = _int(snapshot.get("override_count"))
    trust_tier_counts = _trust_tier_counts(snapshot.get("trust_tier_counts"))

    if (
        release_blocking_failure_count == 0
        and review_required_issue_count == 0
        and failed_test_count > 0
    ):
        review_required_issue_count = failed_test_count

    overall_verdict = _string(getattr(run, "overall_verdict", None)).strip().lower()
    incomplete_count = max(total_result_count - completed_result_count, 0) if total_result_count else 0
    report_ready = (
        status == TestRunStatus.COMPLETED.value
        and pending_manual_count == 0
        and incomplete_count == 0
        and bool(overall_verdict)
    )
    operational_ready = (
        report_ready
        and release_blocking_failure_count == 0
        and review_required_issue_count == 0
        and override_count == 0
    )

    reasons: list[str] = []
    if status in _ACTIVE_STATUSES:
        reasons.append("Test session is still running or paused.")
    elif status == TestRunStatus.AWAITING_REVIEW.value:
        reasons.append("Reviewer sign-off is still pending.")

    if pending_manual_count:
        suffix = "" if pending_manual_count == 1 else "s"
        reasons.append(f"{pending_manual_count} manual test{suffix} still need evidence.")

    if incomplete_count:
        if incomplete_count == 1:
            reasons.append("1 test result is still incomplete.")
        else:
            reasons.append(f"{incomplete_count} test results are still incomplete.")

    if release_blocking_failure_count:
        suffix = "" if release_blocking_failure_count == 1 else "s"
        reasons.append(
            f"{release_blocking_failure_count} release-blocking test{suffix} failed."
        )

    if review_required_issue_count:
        if review_required_issue_count == 1:
            reasons.append("1 high-signal finding needs reviewer attention.")
        else:
            reasons.append(
                f"{review_required_issue_count} high-signal findings need reviewer attention."
            )

    if override_count:
        suffix = "" if override_count == 1 else "s"
        reasons.append(
            f"{override_count} result override{suffix} require sign-off traceability."
        )

    if advisory_count:
        if advisory_count == 1:
            reasons.append("1 advisory finding should be called out in the report.")
        else:
            reasons.append(
                f"{advisory_count} advisory findings should be called out in the report."
            )

    if not reasons:
        reasons.append("Run has complete evidence with no unresolved blocking issues.")

    if status in _ACTIVE_STATUSES:
        level = "in_progress"
        label = "Run still in progress"
        next_step = "Finish the active session before issuing an official report."
    elif status == TestRunStatus.AWAITING_REVIEW.value:
        level = "awaiting_review_signoff"
        label = "Awaiting reviewer sign-off"
        next_step = "Complete reviewer sign-off before issuing the official report."
    elif pending_manual_count:
        level = "awaiting_manual_evidence"
        label = "Manual evidence still required"
        next_step = "Complete the remaining manual checks and save their verdicts."
    elif incomplete_count:
        level = "incomplete"
        label = "Results still incomplete"
        next_step = "Wait for all test results to complete before issuing the official report."
    elif release_blocking_failure_count:
        level = "blocked"
        label = "Blocked by release-critical failures"
        next_step = "Resolve or explicitly accept the release-blocking failures before sign-off."
    elif review_required_issue_count or override_count:
        level = "review_required"
        label = "Reviewer attention required"
        next_step = "Review high-signal findings and overrides before issuing the official report."
    elif advisory_count:
        level = "conditional"
        label = "Operational with advisories"
        next_step = "Issue the report with the advisory notes and follow-up actions captured."
    else:
        level = "operational"
        label = "Operationally ready"
        next_step = "Run is ready for official reporting and engineer handover."

    score = _score_readiness(
        total_result_count=total_result_count,
        completed_result_count=completed_result_count,
        pending_manual_count=pending_manual_count,
        release_blocking_failure_count=release_blocking_failure_count,
        review_required_issue_count=review_required_issue_count,
        advisory_count=advisory_count,
        override_count=override_count,
        status=status,
    )

    return {
        "score": score,
        "level": level,
        "label": label,
        "report_ready": report_ready,
        "operational_ready": operational_ready,
        "blocking_issue_count": pending_manual_count + release_blocking_failure_count,
        "pending_manual_count": pending_manual_count,
        "release_blocking_failure_count": release_blocking_failure_count,
        "review_required_issue_count": review_required_issue_count,
        "manual_evidence_pending_count": _int(snapshot.get("manual_evidence_pending_count")),
        "advisory_count": advisory_count,
        "override_count": override_count,
        "failed_test_count": failed_test_count,
        "completed_result_count": completed_result_count,
        "total_result_count": total_result_count,
        "trust_tier_counts": trust_tier_counts,
        "reasons": reasons,
        "next_step": next_step,
        "summary": f"{label} ({score}/10). {reasons[0]}",
    }


def merge_readiness_into_metadata(
    metadata: Any,
    readiness_summary: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(metadata) if isinstance(metadata, dict) else {}
    merged["trust_tier_counts"] = readiness_summary.get(
        "trust_tier_counts",
        dict(_DEFAULT_TRUST_TIER_COUNTS),
    )
    merged["pending_manual_count"] = readiness_summary.get("pending_manual_count", 0)
    merged["completed_result_count"] = readiness_summary.get("completed_result_count", 0)
    merged["readiness_summary"] = readiness_summary
    return merged


def get_report_readiness_block_message(readiness_summary: dict[str, Any]) -> str:
    if _int(readiness_summary.get("pending_manual_count")) > 0:
        return "Cannot generate an official report while manual tests are still pending"
    if readiness_summary.get("level") == "awaiting_review_signoff":
        return "Cannot generate an official report until reviewer sign-off is complete"
    if readiness_summary.get("level") in {"in_progress", "incomplete"}:
        return "Cannot generate an official report until the test run is fully completed"
    return (
        "Cannot generate an official report yet: "
        f"{_string(readiness_summary.get('next_step')).strip() or 'complete the remaining readiness steps'}"
    )
