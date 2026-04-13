"""Hardening coverage for test-engine lifecycle and trust metadata."""

import asyncio
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


@pytest.mark.asyncio
async def test_run_uses_refreshed_device_ip_for_live_cable_handler(monkeypatch: pytest.MonkeyPatch):
    run = SimpleNamespace(
        id="run-3",
        device_id="device-3",
        template_id="template-3",
        run_metadata={},
        started_at=None,
    )
    device = SimpleNamespace(
        id="device-3",
        ip_address="192.168.10.20",
        open_ports=[{"port": 443}],
    )
    template = SimpleNamespace(whitelist_id=None)
    created_handlers: list[SimpleNamespace] = []

    class DummyResults:
        def scalars(self):
            return self

        def all(self):
            return []

    class DummySession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def commit(self):
            return None

        async def refresh(self, _obj):
            return None

        def expunge(self, _obj):
            return None

        async def execute(self, _query):
            return DummyResults()

    class FakeCableHandler:
        def __init__(self, ip: str, run_id: str, _manager, probe_ports: list[int] | None = None):
            self.ip = ip
            self.run_id = run_id
            self.probe_ports = probe_ports or []
            self.pause_calls: list[dict] = []
            self.monitor_started = False
            self.is_running = True
            self.stopped = False
            created_handlers.append(self)

        async def monitor(self):
            self.monitor_started = True
            while self.is_running:
                await asyncio.sleep(0.01)

        async def pause_for_disconnect(self, message: str | None = None, kill_tools: bool = True, reason: str = "cable"):
            await asyncio.sleep(0)
            self.pause_calls.append(
                {"message": message, "kill_tools": kill_tools, "reason": reason}
            )

        def stop(self):
            self.is_running = False
            self.stopped = True

    async def fake_versions():
        return {"versions": {}}

    async def fake_broadcast(_channel, _payload):
        return None

    async def fake_readiness(_db, refreshed_device, *, logger=None):
        refreshed_device.ip_address = "192.168.10.44"
        return SimpleNamespace(
            can_execute=False,
            reason="unreachable",
            pause_message="Waiting for reconnect",
            probe_ports=[443],
            missing_ip=False,
        )

    async def fake_finalize(_run_id: str):
        return None

    monkeypatch.setattr(test_engine_module, "async_session", lambda: DummySession())
    monkeypatch.setattr(test_engine_module.tools_client, "versions", fake_versions)
    monkeypatch.setattr(test_engine_module.manager, "broadcast", fake_broadcast)
    monkeypatch.setattr(test_engine_module, "ensure_device_execution_readiness", fake_readiness)
    monkeypatch.setattr(test_engine_module, "WobblyCableHandler", FakeCableHandler)

    engine = TestEngine()

    async def fake_load_run(_db, _run_id):
        return run

    async def fake_load_device(_db, _device_id):
        return device

    async def fake_load_template(_db, _template_id):
        return template

    async def fake_load_whitelist(_db, _whitelist_id):
        return []

    monkeypatch.setattr(engine, "_load_run", fake_load_run)
    monkeypatch.setattr(engine, "_load_device", fake_load_device)
    monkeypatch.setattr(engine, "_load_template", fake_load_template)
    monkeypatch.setattr(engine, "_load_whitelist", fake_load_whitelist)
    monkeypatch.setattr(engine, "_finalize_run", fake_finalize)

    await engine.run("run-3")

    assert len(created_handlers) == 1
    handler = created_handlers[0]
    assert handler.ip == "192.168.10.44"
    assert handler.monitor_started is True
    assert handler.pause_calls == [
        {"message": "Waiting for reconnect", "kill_tools": False, "reason": "cable"}
    ]
    assert handler.stopped is True
