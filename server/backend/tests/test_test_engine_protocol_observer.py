from types import SimpleNamespace

import pytest

from app.services import test_engine as test_engine_module
from app.services.test_engine import TestEngine


@pytest.mark.asyncio
async def test_dispatch_u05_ipv4_target_is_not_scanned(monkeypatch: pytest.MonkeyPatch):
    async def fail_nmap_stream(*args, **kwargs):
        raise AssertionError("IPv4 targets should not be scanned with nmap -6")

    monkeypatch.setattr(test_engine_module.tools_client, "nmap_stream", fail_nmap_stream)

    engine = TestEngine()
    parsed, raw = await engine._dispatch_test(
        "U05",
        "192.168.4.68",
        "run-u05",
        SimpleNamespace(mac_address=None),
        "direct",
    )

    assert raw is None
    assert parsed["ipv6_assessed"] is False


@pytest.mark.asyncio
async def test_dispatch_u09_filters_inconclusive_udp_ports():
    run_id = "run-u09-open-filtered"
    test_engine_module._PORT_SCAN_CACHE[f"{run_id}_u07"] = {
        "scan_info": {"type": "udp", "protocol": "udp"},
        "hosts": [{"ip": "192.168.4.68", "status": "up"}],
        "open_ports": [
            {
                "port": 9999,
                "protocol": "udp",
                "state": "open|filtered",
                "service": "unknown",
            }
        ],
    }

    try:
        engine = TestEngine()
        parsed, raw = await engine._dispatch_test(
            "U09",
            "192.168.4.68",
            run_id,
            SimpleNamespace(mac_address=None),
            "direct",
        )
    finally:
        test_engine_module._PORT_SCAN_CACHE.pop(run_id, None)
        test_engine_module._PORT_SCAN_CACHE.pop(f"{run_id}_u07", None)
        test_engine_module._PORT_SCAN_CACHE.pop(f"{run_id}_u08", None)

    assert raw is None
    assert parsed["open_ports"] == []


@pytest.mark.asyncio
async def test_dispatch_u04_uses_dhcp_observer_details(monkeypatch: pytest.MonkeyPatch):
    async def fake_observe_dhcp_activity(*, expected_mac: str | None, timeout_seconds=None, port=None):
        assert expected_mac == "AA:BB:CC:DD:EE:FF"
        return {
            "observed": True,
            "lease_acknowledged": True,
            "offer_capable": True,
            "offered_ip": "192.168.4.68",
            "server_identifier": "192.168.4.1",
            "events": [{"message_type": 3, "observer_reply_type": 5}],
        }

    monkeypatch.setattr(test_engine_module, "observe_dhcp_activity", fake_observe_dhcp_activity)
    monkeypatch.setattr(test_engine_module.settings, "PROTOCOL_OBSERVER_ENABLED", True)

    engine = TestEngine()
    parsed, raw = await engine._dispatch_test(
        "U04",
        "192.168.4.68",
        "run-u04",
        SimpleNamespace(mac_address="AA:BB:CC:DD:EE:FF"),
        "direct",
    )

    assert raw is None
    assert parsed["dhcp_observed"] is True
    assert parsed["dhcp_lease_acknowledged"] is True
    assert parsed["offer_capable"] is True
    assert parsed["offered_ip"] == "192.168.4.68"
    assert parsed["dhcp_server"] == "192.168.4.1"


@pytest.mark.asyncio
async def test_dispatch_u26_prefers_observed_ntp_traffic(monkeypatch: pytest.MonkeyPatch):
    async def fake_observe_ntp_queries(*, expected_device_ip: str | None, timeout_seconds=None, port=None):
        assert expected_device_ip == "192.168.4.68"
        return {
            "observed": True,
            "version": 4,
            "events": [{"source_ip": expected_device_ip, "version": 4, "mode": 3}],
        }

    monkeypatch.setattr(test_engine_module, "observe_ntp_queries", fake_observe_ntp_queries)
    monkeypatch.setattr(test_engine_module.settings, "PROTOCOL_OBSERVER_ENABLED", True)

    engine = TestEngine()
    parsed, raw = await engine._dispatch_test(
        "U26",
        "192.168.4.68",
        "run-1",
        SimpleNamespace(mac_address="AA:BB:CC:DD:EE:FF"),
        "direct",
    )

    assert raw is None
    assert parsed["ntp_observed_sync"] is True
    assert parsed["ntp_version"] == 4


@pytest.mark.asyncio
async def test_dispatch_u29_prefers_observed_dns_queries(monkeypatch: pytest.MonkeyPatch):
    async def fake_observe_dns_queries(*, expected_device_ip: str | None, timeout_seconds=None, port=None):
        assert expected_device_ip == "192.168.4.68"
        return {
            "observed": True,
            "events": [{"source_ip": expected_device_ip, "query_name": "pool.ntp.org", "query_type": 1}],
        }

    monkeypatch.setattr(test_engine_module, "observe_dns_queries", fake_observe_dns_queries)
    monkeypatch.setattr(test_engine_module.settings, "PROTOCOL_OBSERVER_ENABLED", True)

    engine = TestEngine()
    parsed, raw = await engine._dispatch_test(
        "U29",
        "192.168.4.68",
        "run-2",
        SimpleNamespace(mac_address="AA:BB:CC:DD:EE:FF"),
        "direct",
    )

    assert raw is None
    assert parsed["dns_observed_requests"] is True
    assert parsed["dns_queries"][0]["query_name"] == "pool.ntp.org"
