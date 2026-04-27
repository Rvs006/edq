"""Tests for host scanner helpers in tools/server.py."""

import importlib.util
import os
from pathlib import Path

import pytest


pytest.importorskip("flask")


def _load_tools_server():
    os.environ.setdefault("TOOLS_API_KEY", "test-tools-api-key-minimum-32chars-ok")
    module_path = None
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "tools" / "server.py"
        if candidate.is_file():
            module_path = candidate
            break
    assert module_path is not None, "Unable to locate tools/server.py"
    spec = importlib.util.spec_from_file_location("edq_tools_server_under_test", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_neighbor_table_accepts_windows_arp_output():
    tools_server = _load_tools_server()
    tools_server._MAC_VENDOR_CACHE = {
        "38D135": "EasyIO Corporation Sdn. Bhd.",
    }
    stdout = """
Interface: 192.168.4.10 --- 0x8
  Internet Address      Physical Address      Type
  192.168.4.64          38-d1-35-12-34-56     dynamic
  192.168.4.255         ff-ff-ff-ff-ff-ff     static
"""

    entries = tools_server._parse_neighbor_table(stdout, "192.168.4.0/24")

    assert entries == [
        {
            "ip": "192.168.4.64",
            "mac": "38:D1:35:12:34:56",
            "vendor": "EasyIO Corporation Sdn. Bhd.",
            "device": "192.168.4.10",
            "state": "DYNAMIC",
        }
    ]


def test_parse_windows_ipconfig_returns_host_cidr():
    tools_server = _load_tools_server()
    stdout = """
Ethernet adapter Ethernet:

   Connection-specific DNS Suffix  . :
   IPv4 Address. . . . . . . . . . . : 192.168.4.10(Preferred)
   Subnet Mask . . . . . . . . . . . : 255.255.255.0
   Default Gateway . . . . . . . . . :
"""

    interfaces = tools_server._parse_windows_ipconfig(stdout)

    assert interfaces == [
        {
            "label": "Ethernet",
            "type": "ethernet",
            "cidr": "192.168.4.0/24",
            "host_ip": "192.168.4.10",
        }
    ]


def test_expand_tcp_probe_targets_accepts_multiple_ips():
    tools_server = _load_tools_server()

    targets = tools_server._expand_tcp_probe_targets("192.168.4.64 192.168.4.65", max_hosts=10)

    assert targets == ["192.168.4.64", "192.168.4.65"]


def test_detect_network_tcp_probe_treats_refused_as_reachable(monkeypatch):
    tools_server = _load_tools_server()

    def fake_port_detail(ip: str, port: int, timeout: float):
        return port, "refused" if port == 443 else "none"

    monkeypatch.setattr(tools_server, "_tcp_probe_port_detail", fake_port_detail)

    assert tools_server._tcp_probe("192.168.4.1", ports=(80, 443), timeout=0.1) is True


def test_tcp_probe_host_detail_can_stop_after_first_open_port(monkeypatch):
    tools_server = _load_tools_server()
    probed_ports: list[int] = []

    def fake_port_detail(ip: str, port: int, timeout: float):
        probed_ports.append(port)
        return port, "open" if port == 22 else "none"

    monkeypatch.setattr(tools_server, "_tcp_probe_port_detail", fake_port_detail)

    result = tools_server._tcp_probe_host_detail(
        "192.168.4.64",
        [22, 80, 443],
        timeout=0.1,
        stop_on_first_open=True,
    )

    assert result["reachable"] is True
    assert result["source"] == "tcp:22"
    assert probed_ports == [22]


def test_parse_scan_request_rejects_extra_ip_targets_in_args():
    tools_server = _load_tools_server()

    with tools_server.app.test_request_context(
        "/scan/nmap",
        method="POST",
        json={
            "target": "192.168.4.64",
            "args": ["-sT", "-p", "80", "192.168.4.65"],
        },
    ):
        target, args, timeout, err = tools_server._parse_scan_request(tool_name="nmap")

    assert target is None
    assert args is None
    assert timeout is None
    assert err == ("Unexpected positional target(s) in nmap args: 192.168.4.65", 400)


def test_hydra_args_must_match_validated_target():
    tools_server = _load_tools_server()

    tools_server._validate_hydra_target_arg(
        "192.168.4.64",
        ["-L", "/usr/share/wordlists/usernames.txt", "-P", "/usr/share/wordlists/passwords.txt", "192.168.4.64", "ssh"],
    )

    with pytest.raises(ValueError, match="validated target"):
        tools_server._validate_hydra_target_arg(
            "192.168.4.64",
            ["-L", "/usr/share/wordlists/usernames.txt", "-P", "/usr/share/wordlists/passwords.txt", "192.168.4.65", "ssh"],
        )


def test_tool_update_version_parsing_handles_scanner_banner_formats():
    tools_server = _load_tools_server()

    assert tools_server._parse_installed_version(
        "ssh_audit",
        "\x1b[0;36m# ssh-audit v3.3.0, https://github.com/jtesta/ssh-audit\x1b[0m",
    ) == "3.3.0"
    assert tools_server._parse_installed_version(
        "testssl",
        "testssl.sh version 3.2.3 from https://testssl.sh/",
    ) == "3.2.3"
    assert tools_server._parse_installed_version(
        "snmpwalk",
        "NET-SNMP version: 5.9.4.pre2",
    ) == "5.9.4"


def test_tool_update_comparison_treats_newer_installed_versions_as_current():
    tools_server = _load_tools_server()

    assert tools_server._is_installed_version_current("5.9.4", "5.9.3") is True
    assert tools_server._is_installed_version_current("3.2.2", "3.2.3") is False
    assert tools_server._is_installed_version_current(None, "3.2.3") is None
