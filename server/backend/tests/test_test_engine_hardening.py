"""Hardening coverage for test-engine lifecycle and trust metadata."""

import asyncio
from types import SimpleNamespace

import pytest

from app.models.test_result import TestTier as ResultTierEnum, TestVerdict as ResultVerdictEnum
from app.models.test_run import TestRunStatus as RunStatusEnum, TestRunVerdict as RunVerdictEnum
from app.services import test_engine as test_engine_module
from app.services.parsers.nmap_parser import nmap_parser
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


def test_nmap_xml_or_raise_rejects_empty_scanner_output():
    with pytest.raises(RuntimeError, match="U06 nmap returned no XML output"):
        test_engine_module._nmap_xml_or_raise("U06", {"exit_code": 0, "stdout": ""})


def test_nmap_xml_or_raise_keeps_parseable_xml_from_nonzero_nmap_exit():
    xml = "<?xml version=\"1.0\"?><nmaprun><host><status state=\"up\" /></host></nmaprun>"

    assert test_engine_module._nmap_xml_or_raise(
        "U06",
        {"exit_code": 1, "stdout": xml, "stderr": "some probes failed"},
    ) == xml


def test_nmap_xml_or_raise_rejects_invalid_xml():
    with pytest.raises(RuntimeError, match="returned invalid XML"):
        test_engine_module._nmap_xml_or_raise(
            "U06",
            {"exit_code": 0, "stdout": "<nmaprun><host></nmaprun>"},
        )


def test_nmap_scan_evidence_distinguishes_missing_from_valid_empty_scan():
    assert test_engine_module._has_nmap_scan_evidence({}) is False
    assert test_engine_module._has_nmap_scan_evidence({"open_ports": []}) is False
    assert test_engine_module._has_nmap_scan_evidence({"scan_info": {"type": "connect"}}) is True
    assert test_engine_module._has_nmap_scan_evidence({"hosts": [{"status": "up"}]}) is True


def test_infer_os_from_services_treats_easyio_samba_as_embedded_linux():
    inferred = test_engine_module._infer_os_from_services(
        [
            {"service": "ssh", "product": "Dropbear sshd", "version": ""},
            {"service": "microsoft-ds", "product": "Samba smbd", "version": "3.X - 4.X"},
        ]
    )

    assert inferred == "Embedded Linux/Unix (inferred from service banners)"


def test_infer_os_from_services_does_not_treat_microsoft_ds_label_as_windows():
    assert test_engine_module._infer_os_from_services(
        [{"service": "microsoft-ds", "product": "", "version": ""}]
    ) is None


def test_merge_nmap_scan_data_preserves_tcp_and_udp_ports():
    merged = test_engine_module._merge_nmap_scan_data(
        {"open_ports": [{"port": 53, "protocol": "tcp", "state": "open"}], "scan_info": {"type": "connect"}},
        {"open_ports": [{"port": 53, "protocol": "udp", "state": "open|filtered"}], "scan_info": {"type": "udp"}},
    )

    assert {p["protocol"] for p in merged["open_ports"]} == {"tcp", "udp"}


def test_merge_nmap_scan_data_keeps_richer_service_details():
    merged = test_engine_module._merge_nmap_scan_data(
        {
            "open_ports": [
                {"port": 2222, "protocol": "tcp", "state": "open", "service": "unknown"}
            ],
            "scan_info": {"type": "connect", "protocol": "tcp"},
        },
        {
            "open_ports": [
                {
                    "port": 2222,
                    "protocol": "tcp",
                    "state": "open",
                    "service": "ssh",
                    "product": "OpenSSH",
                    "version": "OpenSSH 9.2",
                }
            ],
            "scan_info": {"type": "version", "protocol": "tcp"},
        },
    )

    assert len(merged["open_ports"]) == 1
    assert merged["open_ports"][0]["service"] == "ssh"
    assert merged["open_ports"][0]["version"] == "OpenSSH 9.2"


def test_parse_arp_cache_accepts_windows_output():
    parsed = nmap_parser.parse_arp_cache(
        """
Interface: 192.168.4.10 --- 0x6
  Internet Address      Physical Address      Type
  192.168.4.64          38-d1-35-aa-bb-cc     dynamic
        """
    )

    assert parsed["mac_address"] == "38:D1:35:AA:BB:CC"


@pytest.mark.asyncio
async def test_u02_uses_saved_device_mac_when_container_cannot_see_arp(monkeypatch):
    engine = TestEngine()
    empty_host_xml = (
        '<?xml version="1.0"?><nmaprun>'
        '<host><status state="up"/><address addr="192.168.4.64" addrtype="ipv4"/></host>'
        "</nmaprun>"
    )

    async def fake_nmap_stream(_target, _args=None, timeout=300, on_line=None):
        return {"exit_code": 0, "stdout": empty_host_xml}

    async def fake_post(_path, _payload, timeout=300):
        return {"exit_code": 0, "stdout": empty_host_xml}

    async def fake_ping(_target, count=3):
        return {"exit_code": 0, "stdout": "1 received"}

    async def fake_arp_cache(_target):
        return {"exit_code": 0, "stdout": ""}

    async def fake_resolve(mac, current_vendor=None):
        assert mac == "38:D1:35:AA:BB:CC"
        assert current_vendor == "EasyIO Corporation Sdn. Bhd."
        return current_vendor

    monkeypatch.setattr(test_engine_module.tools_client, "nmap_stream", fake_nmap_stream)
    monkeypatch.setattr(test_engine_module.tools_client, "_post", fake_post)
    monkeypatch.setattr(test_engine_module.tools_client, "ping", fake_ping)
    monkeypatch.setattr(test_engine_module.tools_client, "arp_cache", fake_arp_cache)
    monkeypatch.setattr(test_engine_module, "resolve_mac_vendor", fake_resolve)

    parsed, raw = await engine._dispatch_test(
        "U02",
        "192.168.4.64",
        "run-1",
        SimpleNamespace(
            mac_address="38:D1:35:AA:BB:CC",
            oui_vendor="EasyIO Corporation Sdn. Bhd.",
            manufacturer=None,
        ),
        "direct",
    )

    assert raw == empty_host_xml
    assert parsed["mac_address"] == "38:D1:35:AA:BB:CC"
    assert parsed["oui_vendor"] == "EasyIO Corporation Sdn. Bhd."
    assert parsed["source"] == "device_record"


@pytest.mark.asyncio
async def test_u02_uses_sidecar_parsed_arp_entries(monkeypatch):
    engine = TestEngine()
    empty_host_xml = (
        '<?xml version="1.0"?><nmaprun>'
        '<host><status state="up"/><address addr="192.168.4.64" addrtype="ipv4"/></host>'
        "</nmaprun>"
    )

    async def fake_nmap_stream(_target, _args=None, timeout=300, on_line=None):
        return {"exit_code": 0, "stdout": empty_host_xml}

    async def fake_post(_path, _payload, timeout=300):
        return {"exit_code": 0, "stdout": empty_host_xml}

    async def fake_ping(_target, count=3):
        return {"exit_code": 0, "stdout": "1 received"}

    async def fake_arp_cache(_target):
        return {
            "exit_code": 0,
            "stdout": "",
            "entries": [
                {
                    "ip": "192.168.4.64",
                    "mac": "38:D1:35:AA:BB:CC",
                    "vendor": "EasyIO Corporation Sdn. Bhd.",
                }
            ],
        }

    async def fake_resolve(mac, current_vendor=None):
        assert mac == "38:D1:35:AA:BB:CC"
        return current_vendor

    monkeypatch.setattr(test_engine_module.tools_client, "nmap_stream", fake_nmap_stream)
    monkeypatch.setattr(test_engine_module.tools_client, "_post", fake_post)
    monkeypatch.setattr(test_engine_module.tools_client, "ping", fake_ping)
    monkeypatch.setattr(test_engine_module.tools_client, "arp_cache", fake_arp_cache)
    monkeypatch.setattr(test_engine_module, "resolve_mac_vendor", fake_resolve)

    parsed, _raw = await engine._dispatch_test(
        "U02",
        "192.168.4.64",
        "run-1",
        SimpleNamespace(mac_address=None, oui_vendor=None, manufacturer=None),
        "direct",
    )

    assert parsed["mac_address"] == "38:D1:35:AA:BB:CC"
    assert parsed["oui_vendor"] == "EasyIO Corporation Sdn. Bhd."


@pytest.mark.asyncio
async def test_u06_full_scan_has_bounded_host_timeout(monkeypatch):
    engine = TestEngine()
    captured: dict[str, object] = {}
    xml = (
        '<?xml version="1.0"?><nmaprun><scaninfo type="connect" protocol="tcp"/>'
        '<host><status state="up"/><address addr="192.168.4.64" addrtype="ipv4"/></host>'
        "</nmaprun>"
    )

    async def fake_nmap_stream(target, args=None, timeout=300, on_line=None):
        captured["target"] = target
        captured["args"] = args or []
        captured["timeout"] = timeout
        return {"exit_code": 0, "stdout": xml}

    monkeypatch.setattr(test_engine_module.tools_client, "nmap_stream", fake_nmap_stream)
    monkeypatch.setattr(test_engine_module.tools_client, "scanner_in_docker", False)
    monkeypatch.setattr(test_engine_module.tools_client, "backend_in_docker", False)

    parsed, raw = await engine._dispatch_test(
        "U06",
        "192.168.4.64",
        "run-1",
        SimpleNamespace(),
        "direct",
    )

    assert raw == xml
    assert parsed["scan_info"]["type"] == "connect"
    assert "--host-timeout" in captured["args"]
    assert "180s" in captured["args"]
    assert "--stats-every" in captured["args"]
    assert captured["timeout"] == 240


@pytest.mark.asyncio
async def test_u06_docker_mode_uses_fast_tcp_inventory(monkeypatch):
    engine = TestEngine()
    captured: dict[str, object] = {}

    async def fake_tcp_probe(target, ports, connect_timeout=1.0, concurrency=64, max_hosts=1024, timeout=60):
        captured["target"] = target
        captured["ports"] = ports
        return {
            "hosts": [
                {
                    "ip": target,
                    "reachable": True,
                    "open_ports": [{"port": 22}, {"port": 443}],
                    "responses": [
                        {"port": 22, "state": "open"},
                        {"port": 443, "state": "open"},
                    ],
                }
            ]
        }

    monkeypatch.setattr(test_engine_module.tools_client, "scanner_in_docker", True)
    monkeypatch.setattr(test_engine_module.tools_client, "backend_in_docker", True)
    monkeypatch.setattr(test_engine_module.tools_client, "tcp_probe", fake_tcp_probe)

    parsed, raw = await engine._dispatch_test(
        "U06",
        "192.168.4.64",
        "run-1",
        SimpleNamespace(open_ports=[]),
        "direct",
    )

    assert captured["target"] == "192.168.4.64"
    assert {p["port"] for p in parsed["open_ports"]} == {22, 443}
    assert parsed["scan_info"]["type"] == "tcp-probe"
    assert '"open_ports"' in raw


def test_tcp_scan_evidence_rejects_udp_only_scan_for_port_skips():
    assert test_engine_module._has_tcp_scan_evidence({
        "scan_info": {"type": "udp", "protocol": "udp"},
        "open_ports": [{"port": 53, "protocol": "udp", "state": "open|filtered"}],
    }) is False
    assert test_engine_module._has_tcp_scan_evidence({
        "scan_info": {"type": "connect", "protocol": "tcp"},
        "open_ports": [],
    }) is True


@pytest.mark.asyncio
async def test_persist_run_progress_sets_and_clears_current_test(monkeypatch: pytest.MonkeyPatch):
    run = SimpleNamespace(
        completed_tests=0,
        progress_pct=0.0,
        status=RunStatusEnum.PENDING,
        started_at=None,
        run_metadata={"tool_versions": {"nmap": "7.95"}},
    )

    class DummySession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, _model, _run_id):
            return run

        async def commit(self):
            return None

    monkeypatch.setattr(test_engine_module, "async_session", lambda: DummySession())

    engine = TestEngine()
    await engine._persist_run_progress(
        "run-current",
        completed_tests=3,
        total_tests=10,
        status=RunStatusEnum.RUNNING,
        current_test_id="U35",
        current_test_name="Web Server Vulnerability Scan",
        current_test_started_at=test_engine_module.utcnow_naive(),
    )

    assert run.completed_tests == 3
    assert run.progress_pct == 30.0
    assert run.status == RunStatusEnum.RUNNING
    assert run.run_metadata["tool_versions"]["nmap"] == "7.95"
    assert run.run_metadata["current_test"]["test_id"] == "U35"
    assert run.run_metadata["current_test"]["test_name"] == "Web Server Vulnerability Scan"

    await engine._persist_run_progress(
        "run-current",
        completed_tests=4,
        total_tests=10,
        clear_current_test=True,
    )

    assert run.completed_tests == 4
    assert "current_test" not in run.run_metadata
    assert run.run_metadata["tool_versions"]["nmap"] == "7.95"


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
        run_metadata={"current_test": {"test_id": "U35"}},
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
    assert run.progress_pct == 50.0
    assert run.run_metadata["pending_manual_count"] == 1
    assert run.run_metadata["completed_result_count"] == 1
    assert run.run_metadata["trust_tier_counts"]["manual_evidence"] == 1
    assert "current_test" not in run.run_metadata
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
async def test_finalize_run_counts_info_and_marks_errors_incomplete(monkeypatch: pytest.MonkeyPatch):
    run = SimpleNamespace(
        id="run-error",
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
        _result("U06", ResultVerdictEnum.INFO, ResultTierEnum.AUTOMATIC, "yes"),
        _result("U08", ResultVerdictEnum.ERROR, ResultTierEnum.AUTOMATIC, "no"),
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
    await engine._finalize_run("run-error")

    assert run.status == RunStatusEnum.COMPLETED
    assert run.overall_verdict == RunVerdictEnum.INCOMPLETE
    assert run.completed_tests == 2
    assert run.failed_tests == 1
    assert run.run_metadata["info_count"] == 1
    assert run.run_metadata["error_count"] == 1
    assert messages[-1]["payload"]["data"]["overall_verdict"] == RunVerdictEnum.INCOMPLETE
    assert messages[-1]["payload"]["data"]["info"] == 1
    assert messages[-1]["payload"]["data"]["errors"] == 1


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
        def __init__(
            self,
            ip: str,
            run_id: str,
            _manager,
            probe_ports: list[int] | None = None,
            known_service_ports: list[int] | None = None,
        ):
            self.ip = ip
            self.run_id = run_id
            self.probe_ports = probe_ports or []
            self.known_service_ports = known_service_ports or []
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
