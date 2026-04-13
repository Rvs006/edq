"""Hardening coverage for test-engine lifecycle and trust metadata."""

from types import SimpleNamespace

import pytest

from app.models.test_result import TestTier as ResultTierEnum, TestVerdict as ResultVerdictEnum
from app.models.test_run import TestRunStatus as RunStatusEnum, TestRunVerdict as RunVerdictEnum
from app.services import test_engine as test_engine_module
from app.services.test_engine import TestEngine


def _result(
    test_id: str,
    verdict: ResultVerdictEnum,
    tier: ResultTierEnum,
    essential: str = "no",
):
    return SimpleNamespace(
        test_id=test_id,
        verdict=verdict,
        tier=tier,
        is_essential=essential,
    )


@pytest.mark.asyncio
async def test_finalize_run_awaiting_manual_sets_status_and_metadata(monkeypatch: pytest.MonkeyPatch):
    run = SimpleNamespace(
        id="run-1",
        total_tests=2,
        passed_tests=0,
        failed_tests=0,
        advisory_tests=0,
        na_tests=0,
        completed_tests=0,
        progress_pct=0.0,
        status=RunStatusEnum.RUNNING,
        overall_verdict=None,
        completed_at=None,
        run_metadata={},
    )
    all_results = [
        _result("U01", ResultVerdictEnum.PASS, ResultTierEnum.AUTOMATIC, "yes"),
        _result("U20", ResultVerdictEnum.PENDING, ResultTierEnum.GUIDED_MANUAL, "no"),
    ]
    messages: list[dict] = []

    class DummyResults:
        def scalars(self):
            return self

        def all(self):
            return all_results

    class DummySession:
        def __init__(self):
            self.committed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, query):
            return DummyResults()

        async def get(self, model, run_id):
            return run

        async def commit(self):
            self.committed = True

    monkeypatch.setattr(test_engine_module, "async_session", lambda: DummySession())
    async def _capture(channel, payload):
        messages.append({"channel": channel, "payload": payload})

    monkeypatch.setattr(test_engine_module.manager, "broadcast", _capture)

    engine = TestEngine()
    await engine._finalize_run("run-1")

    assert run.status == RunStatusEnum.AWAITING_MANUAL
    assert run.overall_verdict is None
    assert run.progress_pct == 100.0
    assert run.run_metadata["pending_manual_count"] == 1
    assert run.run_metadata["completed_result_count"] == 1
    assert run.run_metadata["trust_tier_counts"]["manual_evidence"] == 1
    assert messages[-1]["payload"]["data"]["status"] == "awaiting_manual"


@pytest.mark.asyncio
async def test_finalize_run_completed_sets_pass_and_release_blocking_counts(monkeypatch: pytest.MonkeyPatch):
    run = SimpleNamespace(
        id="run-2",
        total_tests=2,
        passed_tests=0,
        failed_tests=0,
        advisory_tests=0,
        na_tests=0,
        completed_tests=0,
        progress_pct=0.0,
        status=RunStatusEnum.RUNNING,
        overall_verdict=None,
        completed_at=None,
        run_metadata={},
    )
    all_results = [
        _result("U01", ResultVerdictEnum.PASS, ResultTierEnum.AUTOMATIC, "yes"),
        _result("U10", ResultVerdictEnum.ADVISORY, ResultTierEnum.AUTOMATIC, "yes"),
    ]
    messages: list[dict] = []

    class DummyResults:
        def scalars(self):
            return self

        def all(self):
            return all_results

    class DummySession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, query):
            return DummyResults()

        async def get(self, model, run_id):
            return run

        async def commit(self):
            return None

    monkeypatch.setattr(test_engine_module, "async_session", lambda: DummySession())
    async def _capture(channel, payload):
        messages.append({"channel": channel, "payload": payload})

    monkeypatch.setattr(test_engine_module.manager, "broadcast", _capture)

    engine = TestEngine()
    await engine._finalize_run("run-2")

    assert run.status == RunStatusEnum.COMPLETED
    assert run.overall_verdict == RunVerdictEnum.QUALIFIED_PASS
    assert run.completed_at is not None
    assert run.run_metadata["trust_tier_counts"]["release_blocking"] >= 1
    assert run.run_metadata["trust_tier_counts"]["release_blocking"] >= 2
    assert messages[-1]["payload"]["data"]["overall_verdict"] == RunVerdictEnum.QUALIFIED_PASS