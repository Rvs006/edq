"""Hardening coverage for test-engine lifecycle and trust metadata."""

import asyncio
import base64
import json
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


def test_ssh_ports_from_scan_data_prefers_definite_tcp_ssh_ports():
    ports = test_engine_module._ssh_ports_from_scan_data(
        {
            "open_ports": [
                {"port": 2222, "protocol": "tcp", "state": "open", "service": "ssh"},
                {"port": 22, "protocol": "tcp", "state": "open", "service": "unknown"},
                {"port": 2223, "protocol": "udp", "state": "open", "service": "ssh"},
                {"port": 2200, "protocol": "tcp", "state": "open|filtered", "service": "ssh"},
            ]
        }
    )

    assert ports == [22, 2222]


def test_docker_tcp_inventory_includes_smart_building_ports():
    ports = test_engine_module._port_candidates_from_device(SimpleNamespace(open_ports=[]))

    assert 5061 in ports
    assert 8078 in ports
    assert 5627 in ports
    assert 47808 in ports


def test_testssl_args_omit_ip_pin_for_ip_targets():
    assert test_engine_module._testssl_args_for_test("U10", "192.168.4.64") == ["-p"]
    assert test_engine_module._testssl_args_for_test("U11", "192.168.4.64") == ["-E"]
    assert test_engine_module._testssl_args_for_test("U12", "192.168.4.64:8443") == ["--fast"]


def test_testssl_args_keep_ip_pin_for_hostnames():
    assert test_engine_module._testssl_args_for_test("U10", "device.local") == ["--ip", "one", "-p"]
    assert test_engine_module._testssl_args_for_test("U11", "device.local:8443") == ["--ip", "one", "-E"]


def test_u12_requires_certificate_fields_before_reusing_tls_cache():
    protocol_only_cache = {
        "tls_versions": ["TLSv1.2"],
        "weak_versions": [],
        "probe_source": "testssl",
        "cipher_inventory_complete": True,
        "hsts_checked": True,
    }
    certificate_cache = {
        **protocol_only_cache,
        "cert_subject": "CN=device.local",
        "cert_issuer": "CN=device.local",
        "cert_not_after": "2030-01-01T00:00:00+00:00",
    }

    assert test_engine_module._tls_cache_satisfies_test("U10", protocol_only_cache) is True
    assert test_engine_module._tls_cache_satisfies_test("U12", protocol_only_cache) is False
    assert test_engine_module._tls_cache_satisfies_test("U12", certificate_cache) is True


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
async def test_u02_accepts_plaintext_nmap_mac_output(monkeypatch):
    engine = TestEngine()
    stdout = (
        "Starting Nmap 7.98 ( https://nmap.org ) at 2026-04-28 12:51 +0100\n"
        "Nmap scan report for 192.168.4.31\n"
        "Host is up (0.00044s latency).\n"
        "MAC Address: BC:6A:44:01:0A:96 (Commend International GmbH)\n"
    )

    async def fake_nmap_stream(_target, _args=None, timeout=300, on_line=None):
        return {"exit_code": 0, "stdout": stdout}

    async def fake_resolve(mac, current_vendor=None):
        assert mac == "BC:6A:44:01:0A:96"
        return current_vendor

    monkeypatch.setattr(test_engine_module.tools_client, "nmap_stream", fake_nmap_stream)
    monkeypatch.setattr(test_engine_module, "resolve_mac_vendor", fake_resolve)

    parsed, raw = await engine._dispatch_test(
        "U02",
        "192.168.4.31",
        "run-plaintext",
        SimpleNamespace(mac_address=None, oui_vendor=None, manufacturer=None),
        "direct",
    )

    assert raw == stdout
    assert parsed["mac_address"] == "BC:6A:44:01:0A:96"
    assert parsed["oui_vendor"] == "Commend International GmbH"


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
async def test_u16_does_not_run_hydra_against_generic_login_forms(monkeypatch):
    engine = TestEngine()
    run_id = "run-form-login"
    test_engine_module._PORT_SCAN_CACHE.pop(run_id, None)
    test_engine_module._PORT_SCAN_CACHE[run_id] = {
        "scan_info": {"type": "connect", "protocol": "tcp"},
        "open_ports": [{"port": 80, "protocol": "tcp", "state": "open", "service": "http"}],
    }

    async def fake_easyio(_self, _device_ip, _port, _service):
        return None

    async def fake_detect(_self, _device_ip, port, service):
        assert port == 80
        assert service == "http-get"
        return {"auth_required": True, "auth_type": "form", "url": "http://192.168.4.31/login"}

    async def fake_hydra_stream(*_args, **_kwargs):
        raise AssertionError("U16 must not run hydra http-get against HTML login forms")

    monkeypatch.setattr(TestEngine, "_check_easyio_default_credentials", fake_easyio)
    monkeypatch.setattr(TestEngine, "_detect_http_auth_surface", fake_detect)
    monkeypatch.setattr(test_engine_module.tools_client, "hydra_stream", fake_hydra_stream)

    try:
        parsed, raw = await engine._dispatch_test(
            "U16",
            "192.168.4.31",
            run_id,
            SimpleNamespace(),
            "direct",
        )
    finally:
        test_engine_module._PORT_SCAN_CACHE.pop(run_id, None)

    assert raw is None
    assert parsed["check_ran"] is False
    assert parsed["found_credentials"] == []
    assert parsed["services_tested"][0]["auth_type"] == "form"
    assert "HTML login form detected" in parsed["reason"]


@pytest.mark.asyncio
async def test_u17_falls_back_to_ssh_lockout_probe_when_web_auth_is_absent(monkeypatch):
    import httpx

    engine = TestEngine()
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200
        text = "device status"
        headers: dict[str, str] = {}
        url = SimpleNamespace(scheme="http")

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *args, **kwargs):
            return FakeResponse()

    async def fake_hydra(target, args=None, timeout=120):
        captured["target"] = target
        captured["args"] = args or []
        captured["timeout"] = timeout
        return {
            "exit_code": 1,
            "stdout": "account locked after 3 failed login attempts",
            "stderr": "",
        }

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(test_engine_module.tools_client, "hydra", fake_hydra)

    parsed = await engine._test_brute_force_protection(
        "192.168.4.31",
        {
            "open_ports": [
                {"port": 2222, "protocol": "tcp", "state": "open", "service": "ssh"}
            ]
        },
    )

    assert parsed["lockout_detected"] is True
    assert parsed["auth_type"] == "ssh"
    assert parsed["attempts"] == 3
    assert parsed["target_port"] == 2222
    assert captured["target"] == "192.168.4.31"
    assert captured["timeout"] == 90
    assert captured["args"] == [
        "-l",
        "admin",
        "-P",
        "/usr/share/wordlists/lockout-passwords.txt",
        "-t",
        "1",
        "-V",
        "-s",
        "2222",
        "192.168.4.31",
        "ssh",
    ]


@pytest.mark.asyncio
async def test_u17_prefers_ssh_lockout_probe_when_web_form_is_present(monkeypatch):
    import httpx

    engine = TestEngine()
    captured: dict[str, object] = {}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("U17 should not probe web auth before SSH when SSH is open")

    async def fake_hydra(target, args=None, timeout=120):
        captured["target"] = target
        captured["args"] = args or []
        return {
            "exit_code": 1,
            "stdout": "account locked after 3 failed login attempts",
            "stderr": "",
        }

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(test_engine_module.tools_client, "hydra", fake_hydra)

    parsed = await engine._test_brute_force_protection(
        "192.168.4.31",
        {
            "open_ports": [
                {"port": 80, "protocol": "tcp", "state": "open", "service": "http"},
                {"port": 22, "protocol": "tcp", "state": "open", "service": "ssh"},
            ]
        },
    )

    assert parsed["lockout_detected"] is True
    assert parsed["auth_type"] == "ssh"
    assert parsed["target_port"] == 22
    assert captured["target"] == "192.168.4.31"
    assert captured["args"][-2:] == ["192.168.4.31", "ssh"]


@pytest.mark.asyncio
async def test_u17_reports_not_assessed_when_ssh_hydra_kex_fails(monkeypatch):
    engine = TestEngine()

    async def fake_hydra(_target, args=None, timeout=120):
        return {
            "exit_code": 255,
            "stdout": "",
            "stderr": (
                "[ERROR] could not connect to ssh://192.168.4.64:22 - kex error : "
                "no match for method server host key algo: server [ssh-rsa], "
                "client [ssh-ed25519,rsa-sha2-512,rsa-sha2-256]"
            ),
        }

    monkeypatch.setattr(test_engine_module.tools_client, "hydra", fake_hydra)

    parsed = await engine._test_brute_force_protection(
        "192.168.4.64",
        {
            "open_ports": [
                {"port": 22, "protocol": "tcp", "state": "open", "service": "ssh"}
            ]
        },
    )

    assert parsed["check_ran"] is False
    assert parsed["lockout_detected"] is False
    assert parsed["attempts"] == 0
    assert parsed["auth_type"] == "ssh"
    assert "host-key/KEX" in parsed["reason"]


def test_login_form_extraction_uses_actual_input_names():
    form = test_engine_module._extract_login_form(
        """
        <html><body>
          <form method="post" action="/session/login">
            <input type="text" name="user[name]" />
            <input type="password" name="user[password]" />
            <input type="hidden" name="submit" value="Login" />
          </form>
        </body></html>
        """,
        "http://192.168.4.31/login",
    )

    assert form is not None
    assert form["form_path"] == "/session/login"
    assert form["username_field"] == "user[name]"
    assert form["password_field"] == "user[password]"
    assert form["tokenized"] is False

    hydra_fields = test_engine_module._build_hydra_form_fields(form)
    assert hydra_fields.startswith("/session/login:")
    assert "user%5Bname%5D=^USER^" in hydra_fields
    assert "user%5Bpassword%5D=^PASS^" in hydra_fields
    assert "submit=Login" in hydra_fields


@pytest.mark.asyncio
async def test_u17_uses_discovered_web_login_port_and_form_fields(monkeypatch):
    import httpx

    engine = TestEngine()
    captured: dict[str, object] = {}

    class FakeResponse:
        def __init__(self, url: str, text: str, status_code: int = 200):
            self.url = url
            self.text = text
            self.status_code = status_code
            self.headers: dict[str, str] = {}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, *args, **kwargs):
            if str(url).endswith("/login"):
                return FakeResponse(
                    str(url),
                    """
                    <form method="post" action="/session/login">
                      <input type="text" name="user[name]" />
                      <input type="password" name="user[password]" />
                    </form>
                    """,
                )
            return FakeResponse(str(url), "device status")

    async def fake_hydra(target, args=None, timeout=120):
        captured["target"] = target
        captured["args"] = args or []
        captured["timeout"] = timeout
        return {
            "exit_code": 1,
            "stdout": "too many failed login attempts; account locked",
            "stderr": "",
        }

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(test_engine_module.tools_client, "hydra", fake_hydra)

    parsed = await engine._test_brute_force_protection(
        "192.168.4.31",
        {
            "scan_info": {"type": "connect", "protocol": "tcp"},
            "open_ports": [
                {"port": 8080, "protocol": "tcp", "state": "open", "service": "http-proxy"}
            ],
        },
    )

    args = captured["args"]
    assert parsed["lockout_detected"] is True
    assert parsed["auth_type"] == "http-post-form"
    assert parsed["target_port"] == 8080
    assert parsed["login_form"] == {
        "form_path": "/session/login",
        "username_field": "user[name]",
        "password_field": "user[password]",
    }
    assert captured["target"] == "192.168.4.31"
    assert captured["timeout"] == 90
    assert "-s" in args and "8080" in args
    assert args[-2] == "http-post-form"
    assert args[-1].startswith("/session/login:")
    assert "user%5Bname%5D=^USER^" in args[-1]
    assert "user%5Bpassword%5D=^PASS^" in args[-1]


@pytest.mark.asyncio
async def test_u17_follow_up_form_probe_preserves_hidden_fields(monkeypatch):
    import httpx

    engine = TestEngine()
    captured: dict[str, object] = {}

    class FakeResponse:
        def __init__(self, url: str, text: str, status_code: int = 200):
            self.url = url
            self.text = text
            self.status_code = status_code
            self.headers: dict[str, str] = {}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, *args, **kwargs):
            if str(url).endswith("/login"):
                return FakeResponse(
                    str(url),
                    """
                    <form method="post" action="/session/login">
                      <input type="text" name="user[name]" />
                      <input type="password" name="user[password]" />
                      <input type="hidden" name="submit" value="Login" />
                      <input type="hidden" name="realm" value="local" />
                    </form>
                    """,
                )
            return FakeResponse(str(url), "device status")

        async def post(self, url, *args, **kwargs):
            captured["post_url"] = str(url)
            captured["post_data"] = kwargs.get("data")
            return FakeResponse(str(url), "too many attempts", 429)

    async def fake_hydra(target, args=None, timeout=120):
        captured["hydra_args"] = args or []
        return {
            "exit_code": 0,
            "stdout": "Hydra completed with no access throttling",
            "stderr": "",
        }

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(test_engine_module.tools_client, "hydra", fake_hydra)

    parsed = await engine._test_brute_force_protection(
        "192.168.4.31",
        {
            "scan_info": {"type": "connect", "protocol": "tcp"},
            "open_ports": [
                {"port": 8080, "protocol": "tcp", "state": "open", "service": "http-proxy"}
            ],
        },
    )

    assert parsed["lockout_detected"] is True
    assert captured["post_url"] == "http://192.168.4.31:8080/session/login"
    assert captured["post_data"] == {
        "submit": "Login",
        "realm": "local",
        "user[name]": "invalid0",
        "user[password]": "invalid0",
    }
    hydra_args = captured["hydra_args"]
    assert "submit=Login" in hydra_args[-1]
    assert "realm=local" in hydra_args[-1]


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
        captured["connect_timeout"] = connect_timeout
        captured["timeout"] = timeout
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
    assert 5061 in captured["ports"]
    assert 8078 in captured["ports"]
    assert captured["connect_timeout"] == 0.35
    assert captured["timeout"] >= 45
    assert {p["port"] for p in parsed["open_ports"]} == {22, 443}
    assert parsed["scan_info"]["type"] == "tcp-probe"
    assert '"open_ports"' in raw


@pytest.mark.asyncio
async def test_u11_bypasses_fast_tls_cache_for_cipher_inventory(monkeypatch):
    engine = TestEngine()
    run_id = "run-tls-cache"
    test_engine_module._TESTSSL_CACHE.pop(run_id, None)
    test_engine_module._TESTSSL_CACHE[run_id] = {
        "tls_versions": ["TLSv1.2"],
        "ciphers": [{"name": "ECDHE-ECDSA-AES256-GCM-SHA384", "protocol": "TLSv1.2", "bits": 256}],
        "weak_ciphers": [],
        "fallback_probe": "python-ssl",
        "cipher_inventory_complete": False,
    }
    findings = [
        {"id": "TLS1_2", "finding": "offered", "severity": "OK"},
        {"id": "cipher_tls12_aes256", "finding": "ECDHE-ECDSA-AES256-GCM-SHA384", "severity": "OK"},
        {"id": "cipher_tls13_chacha", "finding": "TLS_CHACHA20_POLY1305_SHA256", "severity": "OK"},
    ]
    encoded = base64.b64encode(json.dumps(findings).encode("utf-8")).decode("ascii")
    calls: list[dict] = []

    async def fake_testssl_stream(target, args=None, timeout=300, on_line=None):
        calls.append({"target": target, "args": args or [], "timeout": timeout})
        return {"exit_code": 0, "stdout": "", "output_file": encoded}

    monkeypatch.setattr(test_engine_module.tools_client, "testssl_stream", fake_testssl_stream)

    try:
        parsed, raw = await engine._dispatch_test(
            "U11",
            "192.168.4.31",
            run_id,
            SimpleNamespace(open_ports=[{"port": 443, "service": "https"}]),
            "direct",
        )
    finally:
        test_engine_module._TESTSSL_CACHE.pop(run_id, None)

    assert raw == ""
    assert calls == [{"target": "192.168.4.31", "args": ["-E"], "timeout": 300}]
    assert parsed["probe_source"] == "testssl"
    assert parsed["cipher_inventory_complete"] is True
    assert {cipher["name"] for cipher in parsed["ciphers"]} == {
        "ECDHE-ECDSA-AES256-GCM-SHA384",
        "TLS_CHACHA20_POLY1305_SHA256",
    }


@pytest.mark.asyncio
async def test_u10_bypasses_fast_tls_cache_for_protocol_inventory(monkeypatch):
    engine = TestEngine()
    run_id = "run-tls-protocol-cache"
    test_engine_module._TESTSSL_CACHE.pop(run_id, None)
    test_engine_module._TESTSSL_CACHE[run_id] = {
        "tls_versions": ["TLSv1.2"],
        "weak_versions": [],
        "fallback_probe": "python-ssl",
    }
    findings = [
        {"id": "TLS1_0", "finding": "offered", "severity": "WARN"},
        {"id": "TLS1_2", "finding": "offered", "severity": "OK"},
    ]
    encoded = base64.b64encode(json.dumps(findings).encode("utf-8")).decode("ascii")
    calls: list[dict] = []

    async def fake_testssl_stream(target, args=None, timeout=300, on_line=None):
        calls.append({"target": target, "args": args or [], "timeout": timeout})
        return {"exit_code": 0, "stdout": "", "output_file": encoded}

    monkeypatch.setattr(test_engine_module.tools_client, "testssl_stream", fake_testssl_stream)

    try:
        parsed, _raw = await engine._dispatch_test(
            "U10",
            "192.168.4.64",
            run_id,
            SimpleNamespace(open_ports=[{"port": 443, "service": "https"}]),
            "direct",
        )
    finally:
        test_engine_module._TESTSSL_CACHE.pop(run_id, None)

    assert calls == [{"target": "192.168.4.64", "args": ["-p"], "timeout": 300}]
    assert parsed["probe_source"] == "testssl"
    assert parsed["tls_versions"] == ["TLSv1.0", "TLSv1.2"]
    assert parsed["weak_versions"] == ["TLSv1.0"]


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
        current_test_name="Web Server and HTTP Header Assessment",
        current_test_started_at=test_engine_module.utcnow_naive(),
    )

    assert run.completed_tests == 3
    assert run.progress_pct == 30.0
    assert run.status == RunStatusEnum.RUNNING
    assert run.run_metadata["tool_versions"]["nmap"] == "7.95"
    assert run.run_metadata["current_test"]["test_id"] == "U35"
    assert run.run_metadata["current_test"]["test_name"] == "Web Server and HTTP Header Assessment"

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
