"""Tests for tools sidecar client scan argument adaptation."""

import httpx
import pytest

from app.services.tools_client import ToolsClient


def _client(in_docker: bool = True, raw_capable: bool = True) -> ToolsClient:
    client = ToolsClient.__new__(ToolsClient)
    client.in_docker = in_docker
    client.backend_in_docker = in_docker
    client.scanner_in_docker = in_docker
    client.scanner_mode = "docker" if in_docker else "host"
    client._docker_raw_scan_capable = raw_capable
    client.base_url = "http://docker-tools"
    client.host_network_scanner_url = ""
    client.host_arp_helper_url = ""
    client._headers = {}
    return client


def test_docker_nmap_flags_adds_privileged_for_udp_scans():
    flags = _client().docker_nmap_flags(["-sU", "-p", "47808", "-oX", "-"])

    assert "--privileged" in flags
    assert "-Pn" in flags


def test_docker_nmap_flags_prefers_tcp_connect_scan_in_docker(monkeypatch):
    monkeypatch.delenv("EDQ_FORCE_DOCKER_TCP_CONNECT_SCAN", raising=False)

    flags = _client(raw_capable=True).docker_nmap_flags(["-sS", "-p", "80", "-oX", "-"])

    assert "-sT" in flags
    assert "-sS" not in flags
    assert "--privileged" not in flags


def test_docker_nmap_flags_allows_raw_scan_when_connect_fallback_disabled(monkeypatch):
    monkeypatch.setenv("EDQ_FORCE_DOCKER_TCP_CONNECT_SCAN", "false")

    flags = _client(raw_capable=True).docker_nmap_flags(["-sS", "-p", "80", "-oX", "-"])

    assert "-sS" in flags
    assert "-sT" not in flags
    assert "--privileged" in flags
    assert "-Pn" in flags


def test_docker_nmap_flags_keeps_connect_fallback_when_raw_scan_unavailable():
    flags = _client(raw_capable=False).docker_nmap_flags(["-sS", "-p", "80", "-oX", "-"])

    assert "-sT" in flags
    assert "-sS" not in flags
    assert "--privileged" not in flags


def test_docker_nmap_flags_are_not_rewritten_for_host_scanner():
    flags = _client(in_docker=False, raw_capable=False).docker_nmap_flags(["-sS", "-p", "80", "-oX", "-"])

    assert flags == ["-sS", "-p", "80", "-oX", "-"]


def test_auto_scanner_mode_treats_loopback_as_docker_default(monkeypatch):
    monkeypatch.delenv("EDQ_SCANNER_MODE", raising=False)
    monkeypatch.delenv("TOOLS_SCANNER_MODE", raising=False)
    monkeypatch.delenv("EDQ_START_INTERNAL_TOOLS", raising=False)

    client = ToolsClient.__new__(ToolsClient)
    client.base_url = "http://127.0.0.1:8001"
    client.backend_in_docker = False

    assert client._resolve_scanner_mode() == "docker"


def test_explicit_host_scanner_mode_overrides_loopback_default(monkeypatch):
    monkeypatch.setenv("EDQ_SCANNER_MODE", "host")

    client = ToolsClient.__new__(ToolsClient)
    client.base_url = "http://127.0.0.1:8001"
    client.backend_in_docker = False

    assert client._resolve_scanner_mode() == "host"


@pytest.mark.asyncio
async def test_host_arp_cache_uses_dedicated_helper_url():
    client = _client()
    client.host_arp_helper_url = "http://host.docker.internal:8002"
    client._headers = {"X-Tools-Key": "test-key"}
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"entries": [{"ip": "192.168.4.54", "mac": "38:D1:35:01:02:89"}]}

    class FakeClient:
        async def post(self, url, **kwargs):
            captured["url"] = url
            captured.update(kwargs)
            return FakeResponse()

    client._get_client = lambda _timeout=300: FakeClient()

    result = await client.host_arp_cache("192.168.4.54")

    assert captured["url"] == "http://host.docker.internal:8002/scan/arp-cache"
    assert captured["json"] == {"target": "192.168.4.54", "timeout": 15}
    assert captured["headers"] == {"X-Tools-Key": "test-key"}
    assert result["entries"][0]["mac"] == "38:D1:35:01:02:89"


@pytest.mark.asyncio
async def test_host_arp_cache_noops_without_helper_url():
    client = _client()

    result = await client.host_arp_cache("192.168.4.54")

    assert result is None


@pytest.mark.asyncio
async def test_post_stream_forwards_stderr_progress_lines():
    client = _client(in_docker=False)
    client.base_url = "http://tools"
    client._headers = {}
    seen_lines: list[str] = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        async def aiter_lines(self):
            yield 'data: {"type": "stderr", "line": "Stats: 40% done"}'
            yield 'data: {"type": "stdout", "line": "<nmaprun>"}'
            yield 'data: {"type": "result", "data": {"exit_code": 0, "stdout": "<nmaprun/>"}}'

    class FakeStream:
        async def __aenter__(self):
            return FakeResponse()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeClient:
        def stream(self, *_args, **_kwargs):
            return FakeStream()

    def fake_get_client(_timeout: int = 300):
        return FakeClient()

    async def capture(line: str):
        seen_lines.append(line)

    client._get_client = fake_get_client

    result = await client._post_stream("/stream/nmap", {}, on_line=capture)

    assert result["exit_code"] == 0
    assert seen_lines == ["[stderr] Stats: 40% done", "<nmaprun>"]


@pytest.mark.asyncio
async def test_tcp_probe_falls_back_to_nmap_when_endpoint_missing():
    client = _client(in_docker=True, raw_capable=False)

    async def fake_post(path: str, payload: dict, timeout: int = 300):
        assert path == "/scan/tcp-probe"
        request = httpx.Request("POST", "http://tools/scan/tcp-probe")
        response = httpx.Response(404, request=request, text="not found")
        raise httpx.HTTPStatusError("not found", request=request, response=response)

    async def fake_nmap(target: str, args=None, timeout: int = 300):
        assert target == "192.168.4.64"
        assert "-sT" in args
        assert "-p" in args
        assert "80,81,82" in args
        return {
            "duration_seconds": 1.25,
            "stdout": """
                <nmaprun>
                  <host>
                    <address addr="192.168.4.64" addrtype="ipv4" />
                    <ports>
                      <port protocol="tcp" portid="80"><state state="open" /></port>
                      <port protocol="tcp" portid="81"><state state="closed" /></port>
                      <port protocol="tcp" portid="82"><state state="filtered" /></port>
                    </ports>
                  </host>
                </nmaprun>
            """,
        }

    client._post = fake_post
    client.nmap = fake_nmap

    result = await client.tcp_probe("192.168.4.64", [80, 81, 82])

    assert result["fallback"] == "nmap"
    assert result["duration_seconds"] == 1.25
    assert result["hosts"] == [
        {
            "ip": "192.168.4.64",
            "reachable": True,
            "source": "tcp:80",
            "open_ports": [{"port": 80, "service": "", "version": ""}],
            "responses": [
                {"port": 80, "state": "open"},
                {"port": 81, "state": "refused"},
                {"port": 82, "state": "none"},
            ],
        }
    ]


@pytest.mark.asyncio
async def test_nmap_uses_host_network_scanner_without_docker_flag_rewrite():
    client = _client(in_docker=True, raw_capable=False)
    client.host_network_scanner_url = "http://host-scanner"
    captured: dict[str, object] = {}

    async def fake_post(path: str, payload: dict, timeout: int = 300, base_url: str | None = None):
        captured["path"] = path
        captured["payload"] = payload
        captured["base_url"] = base_url
        return {"exit_code": 0, "stdout": "<nmaprun/>"}

    client._post = fake_post

    result = await client.nmap("192.168.4.54", ["-sS", "-p-", "-oX", "-"])

    assert result["exit_code"] == 0
    assert captured["base_url"] == "http://host-scanner"
    assert captured["payload"]["args"] == ["-sS", "-p-", "-oX", "-"]


@pytest.mark.asyncio
async def test_nmap_falls_back_to_docker_with_adjusted_flags_when_host_scanner_unavailable():
    client = _client(in_docker=True, raw_capable=False)
    client.host_network_scanner_url = "http://host-scanner"
    calls: list[dict[str, object]] = []

    async def fake_post(path: str, payload: dict, timeout: int = 300, base_url: str | None = None):
        calls.append({"path": path, "payload": payload, "base_url": base_url})
        if base_url == "http://host-scanner":
            request = httpx.Request("POST", "http://host-scanner/scan/nmap")
            raise httpx.ConnectError("refused", request=request)
        return {"exit_code": 0, "stdout": "<nmaprun/>"}

    client._post = fake_post

    result = await client.nmap("192.168.4.54", ["-sS", "-p", "80", "-oX", "-"])

    assert result["exit_code"] == 0
    assert calls[0]["base_url"] == "http://host-scanner"
    assert calls[0]["payload"]["args"] == ["-sS", "-p", "80", "-oX", "-"]
    assert calls[1]["base_url"] is None
    assert "-sT" in calls[1]["payload"]["args"]
    assert "-sS" not in calls[1]["payload"]["args"]


@pytest.mark.asyncio
async def test_application_tools_stay_on_docker_sidecar_when_host_network_scanner_is_configured():
    client = _client(in_docker=True, raw_capable=False)
    client.host_network_scanner_url = "http://host-scanner"
    captured: dict[str, object] = {}

    async def fake_post(path: str, payload: dict, timeout: int = 300, base_url: str | None = None):
        captured["path"] = path
        captured["payload"] = payload
        captured["base_url"] = base_url
        return {"exit_code": 0, "stdout": "ok"}

    client._post = fake_post

    await client.testssl("192.168.4.54", ["-E"])

    assert captured["path"] == "/scan/testssl"
    assert captured["base_url"] is None
    assert captured["payload"]["args"] == ["-E"]
