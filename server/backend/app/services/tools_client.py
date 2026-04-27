"""Async HTTP client for the EDQ tools sidecar container."""

import asyncio
import json
import logging
import os
import shutil
import subprocess
from typing import Any, AsyncGenerator, Callable, Coroutine, Dict, List, Optional
from urllib.parse import urlparse
from xml.etree import ElementTree

import httpx

from app.config import settings

logger = logging.getLogger("edq.services.tools_client")

_RETRYABLE_STATUS = {502, 503, 504}
_MAX_RETRIES = 3
_RETRY_BACKOFF = 2  # seconds, doubled each retry


def get_tools_error_status(exc: Exception) -> int:
    """Map sidecar/client failures to an API response code."""
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.TimeoutException)):
        return 503
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (502, 503, 504):
            return 503
        if code == 429:
            return 429
        if code in (401, 403):
            return 502
        return 502
    return 502


def describe_tools_error(exc: Exception, fallback: str = "Tools sidecar error") -> str:
    """Return an operator-friendly description of a sidecar failure."""
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
        return "Tools sidecar is unreachable. Automated discovery is unavailable."
    if isinstance(exc, (httpx.ReadTimeout, httpx.TimeoutException)):
        return "Tools sidecar timed out while running the scan."
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        body = (exc.response.text or "").strip()
        if status == 401:
            return "Tools sidecar authentication failed. Check TOOLS_API_KEY."
        if status == 403:
            return "Tools sidecar rejected the request."
        if status == 429:
            return "Tools sidecar rate limit exceeded. Retry in a moment."
        if status == 503:
            return "Tools sidecar is running, but the required scan tool is unavailable."
        if body:
            return f"{fallback}: {body[:200]}"
        return fallback

    message = str(exc).strip()
    return message or fallback


class ToolsClient:
    """Calls the tools sidecar REST API to execute security scans."""

    def __init__(self) -> None:
        self.base_url: str = settings.TOOLS_SIDECAR_URL
        self._headers: Dict[str, str] = {}
        if settings.TOOLS_API_KEY:
            self._headers["X-Tools-Key"] = settings.TOOLS_API_KEY
        self.backend_in_docker: bool = os.path.exists("/.dockerenv")
        # Backward-compatible name used by older route code/tests.
        self.in_docker: bool = self.backend_in_docker
        self.scanner_mode: str = self._resolve_scanner_mode()
        self.scanner_in_docker: bool = self.scanner_mode == "docker"
        self._docker_raw_scan_capable = self._detect_docker_raw_scan_capability()
        self._client: Optional[httpx.AsyncClient] = None

    def _tools_url_is_loopback(self) -> bool:
        host = (urlparse(self.base_url).hostname or "").lower()
        return host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}

    def _resolve_scanner_mode(self) -> str:
        raw_mode = (
            os.environ.get("EDQ_SCANNER_MODE")
            or os.environ.get("TOOLS_SCANNER_MODE")
            or "auto"
        ).strip().lower()
        normalized_mode = raw_mode.replace("_", "-")
        if normalized_mode in {"host", "host-scanner", "external", "external-host"}:
            return "host"
        if normalized_mode in {"docker", "container", "internal", "sidecar"}:
            return "docker"

        start_internal = os.environ.get("EDQ_START_INTERNAL_TOOLS", "true").strip().lower()
        if start_internal in {"0", "false", "no", "off"}:
            return "host"

        # Auto preserves the default EDQ development/deployment model: a scanner
        # reached on localhost is the bundled Docker sidecar unless host mode is
        # explicitly requested. Windows host scanner setups should set
        # EDQ_SCANNER_MODE=host.
        if self._tools_url_is_loopback():
            return "docker"
        return "host"

    def _detect_docker_raw_scan_capability(self) -> bool:
        if not self.scanner_in_docker or not self.backend_in_docker or not self._tools_url_is_loopback():
            return False

        if hasattr(os, "geteuid") and os.geteuid() == 0:
            return True

        getcap_path = next(
            (
                candidate
                for candidate in (shutil.which("getcap"), "/usr/sbin/getcap", "/sbin/getcap")
                if candidate and os.path.exists(candidate)
            ),
            None,
        )
        nmap_path = shutil.which("nmap")
        if not getcap_path or not nmap_path:
            return False

        try:
            result = subprocess.run(
                [getcap_path, nmap_path],
                capture_output=True,
                text=True,
                timeout=2,
            )
        except Exception:
            return False

        capabilities = f"{result.stdout}\n{result.stderr}".lower()
        return "cap_net_raw" in capabilities or "cap_net_admin" in capabilities

    def _prefer_docker_tcp_connect_scan(self) -> bool:
        """Prefer nmap TCP connect scans in Docker unless raw scans are explicitly enabled.

        Docker Desktop and bridge NAT often make SYN scans unreliable against
        directly connected LAN devices. TCP connect scans use the normal socket
        path, which is slower but much more predictable for U06/U09.
        """
        override = os.environ.get("EDQ_FORCE_DOCKER_TCP_CONNECT_SCAN", "true").strip().lower()
        return override not in {"0", "false", "no", "off"}

    def _get_client(self, timeout: int = 300) -> httpx.AsyncClient:
        """Return a persistent shared AsyncClient, creating it on first use."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=timeout + 30,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._client

    async def close(self) -> None:
        """Close the persistent HTTP client. Call on app shutdown."""
        if self._client and not self._client.is_closed:
            try:
                await self._client.aclose()
            except RuntimeError as exc:
                if "Event loop is closed" not in str(exc):
                    raise
            finally:
                self._client = None

    def docker_nmap_flags(self, args: List[str]) -> List[str]:
        """Adjust nmap flags for container NAT without breaking discovery scans."""
        scanner_in_docker = getattr(self, "scanner_in_docker", getattr(self, "in_docker", False))
        if not scanner_in_docker:
            return list(args)
        adjusted = list(args)
        prefer_connect = self._prefer_docker_tcp_connect_scan()
        if prefer_connect or not self._docker_raw_scan_capable:
            adjusted = ["-sT" if a == "-sS" else a for a in adjusted]
        privileged_flags = {"-sS", "-sU", "-O", "-A", "-PR", "-PE", "-PP", "-PM"}
        if self._docker_raw_scan_capable and "--privileged" not in adjusted:
            if any(flag in adjusted for flag in privileged_flags):
                adjusted.insert(0, "--privileged")
        if "-sn" in args or "-PR" in args:
            return adjusted
        if any(flag in adjusted for flag in ("-sT", "-sS", "-sV", "-O", "-A", "-p", "-p-", "--top-ports")) and "-Pn" not in adjusted:
            adjusted.insert(0, "-Pn")
        return adjusted

    async def _post(
        self,
        path: str,
        payload: Dict[str, Any],
        timeout: int = 300,
    ) -> Dict[str, Any]:
        last_exc: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES):
            try:
                client = self._get_client(timeout)
                resp = await client.post(
                    f"{self.base_url}{path}",
                    json=payload,
                    headers=self._headers,
                    timeout=timeout + 10,
                )
                if resp.status_code in _RETRYABLE_STATUS and attempt < _MAX_RETRIES - 1:
                    logger.warning("Retryable %d from %s (attempt %d)", resp.status_code, path, attempt + 1)
                    await asyncio.sleep(_RETRY_BACKOFF * (2 ** attempt))
                    continue
                resp.raise_for_status()
                return resp.json()
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    logger.warning("Connection error to sidecar (attempt %d): %s", attempt + 1, exc)
                    await asyncio.sleep(_RETRY_BACKOFF * (2 ** attempt))
                    continue
                raise
        raise last_exc or RuntimeError("Unexpected retry exhaustion")

    async def _post_stream(
        self,
        path: str,
        payload: Dict[str, Any],
        timeout: int = 300,
        on_line: Optional[Callable[[str], Coroutine]] = None,
    ) -> Dict[str, Any]:
        """POST to a streaming SSE endpoint, calling on_line for output lines.

        Returns the final result dict (same shape as _post).
        Falls back to the non-streaming endpoint if SSE fails.
        """
        result: Dict[str, Any] = {}
        try:
            client = self._get_client(timeout)
            async with client.stream(
                "POST",
                f"{self.base_url}{path}",
                json=payload,
                headers=self._headers,
                timeout=timeout + 30,
            ) as resp:
                resp.raise_for_status()
                async for raw_line in resp.aiter_lines():
                    if not raw_line.startswith("data: "):
                        continue
                    try:
                        event = json.loads(raw_line[6:])
                    except json.JSONDecodeError:
                        continue
                    event_type = event.get("type")
                    if event_type in {"stdout", "stderr"} and on_line:
                        line = event.get("line", "")
                        if event_type == "stderr":
                            line = f"[stderr] {line}"
                        await on_line(line)
                    elif event.get("type") == "result":
                        result = event.get("data", {})
        except Exception as exc:
            logger.warning("Streaming failed for %s, falling back to sync: %s", path, exc)
            # Fall back to non-streaming endpoint
            sync_path = path.replace("/stream/", "/scan/")
            return await self._post(sync_path, payload, timeout=timeout)

        if not result:
            sync_path = path.replace("/stream/", "/scan/")
            return await self._post(sync_path, payload, timeout=timeout)

        return result

    async def nmap_stream(
        self,
        target: str,
        args: Optional[List[str]] = None,
        timeout: int = 300,
        on_line: Optional[Callable[[str], Coroutine]] = None,
    ) -> Dict[str, Any]:
        """Run nmap with line-by-line streaming (auto-adjusts flags for Docker NAT)."""
        return await self._post_stream(
            "/stream/nmap",
            {"target": target, "args": self.docker_nmap_flags(args or []), "timeout": timeout},
            timeout=timeout,
            on_line=on_line,
        )

    async def testssl_stream(
        self,
        target: str,
        args: Optional[List[str]] = None,
        timeout: int = 300,
        on_line: Optional[Callable[[str], Coroutine]] = None,
    ) -> Dict[str, Any]:
        """Run testssl.sh with line-by-line streaming."""
        return await self._post_stream(
            "/stream/testssl",
            {"target": target, "args": args or [], "timeout": timeout},
            timeout=timeout,
            on_line=on_line,
        )

    async def ssh_audit_stream(
        self,
        target: str,
        args: Optional[List[str]] = None,
        timeout: int = 120,
        on_line: Optional[Callable[[str], Coroutine]] = None,
    ) -> Dict[str, Any]:
        """Run ssh-audit with line-by-line streaming."""
        return await self._post_stream(
            "/stream/ssh-audit",
            {"target": target, "args": args or [], "timeout": timeout},
            timeout=timeout,
            on_line=on_line,
        )

    async def hydra_stream(
        self,
        target: str,
        args: Optional[List[str]] = None,
        timeout: int = 120,
        on_line: Optional[Callable[[str], Coroutine]] = None,
    ) -> Dict[str, Any]:
        """Run hydra with line-by-line streaming."""
        return await self._post_stream(
            "/stream/hydra",
            {"target": target, "args": args or [], "timeout": timeout},
            timeout=timeout,
            on_line=on_line,
        )

    async def nikto_stream(
        self,
        target: str,
        args: Optional[List[str]] = None,
        timeout: int = 300,
        on_line: Optional[Callable[[str], Coroutine]] = None,
    ) -> Dict[str, Any]:
        """Run nikto with line-by-line streaming."""
        return await self._post_stream(
            "/stream/nikto",
            {"target": target, "args": args or [], "timeout": timeout},
            timeout=timeout,
            on_line=on_line,
        )

    async def snmpwalk(
        self,
        target: str,
        args: Optional[List[str]] = None,
        timeout: int = 120,
    ) -> Dict[str, Any]:
        """Run snmpwalk SNMP query."""
        return await self._post(
            "/scan/snmpwalk",
            {"target": target, "args": args or [], "timeout": timeout},
            timeout=timeout,
        )

    async def snmpwalk_stream(
        self,
        target: str,
        args: Optional[List[str]] = None,
        timeout: int = 120,
        on_line: Optional[Callable[[str], Coroutine]] = None,
    ) -> Dict[str, Any]:
        """Run snmpwalk with line-by-line streaming."""
        return await self._post_stream(
            "/stream/snmpwalk",
            {"target": target, "args": args or [], "timeout": timeout},
            timeout=timeout,
            on_line=on_line,
        )

    async def health(self) -> Dict[str, Any]:
        """Check sidecar health and tool availability."""
        client = self._get_client(10)
        resp = await client.get(f"{self.base_url}/health", headers=self._headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    async def check_updates(self) -> Dict[str, Any]:
        """Return sidecar scanner update guidance.

        The sidecar compares installed scanners with the image's pinned
        latest-known versions. EDQ reports that state but does not mutate
        scanner binaries at runtime.
        """
        client = self._get_client(15)
        resp = await client.get(f"{self.base_url}/check-updates", headers=self._headers, timeout=15)
        resp.raise_for_status()
        return resp.json()

    async def nmap(
        self,
        target: str,
        args: Optional[List[str]] = None,
        timeout: int = 300,
    ) -> Dict[str, Any]:
        """Run nmap scan (auto-adjusts flags for Docker NAT)."""
        return await self._post(
            "/scan/nmap",
            {"target": target, "args": self.docker_nmap_flags(args or []), "timeout": timeout},
            timeout=timeout,
        )

    async def testssl(
        self,
        target: str,
        args: Optional[List[str]] = None,
        timeout: int = 300,
    ) -> Dict[str, Any]:
        """Run testssl.sh scan."""
        return await self._post(
            "/scan/testssl",
            {"target": target, "args": args or [], "timeout": timeout},
            timeout=timeout,
        )

    async def ssh_audit(
        self,
        target: str,
        args: Optional[List[str]] = None,
        timeout: int = 120,
    ) -> Dict[str, Any]:
        """Run ssh-audit scan."""
        return await self._post(
            "/scan/ssh-audit",
            {"target": target, "args": args or [], "timeout": timeout},
            timeout=timeout,
        )

    async def hydra(
        self,
        target: str,
        args: Optional[List[str]] = None,
        timeout: int = 120,
    ) -> Dict[str, Any]:
        """Run hydra credential test."""
        return await self._post(
            "/scan/hydra",
            {"target": target, "args": args or [], "timeout": timeout},
            timeout=timeout,
        )

    async def nikto(
        self,
        target: str,
        args: Optional[List[str]] = None,
        timeout: int = 300,
    ) -> Dict[str, Any]:
        """Run nikto web scanner."""
        return await self._post(
            "/scan/nikto",
            {"target": target, "args": args or [], "timeout": timeout},
            timeout=timeout,
        )

    async def versions(self) -> Dict[str, Any]:
        """Get installed tool versions from the sidecar."""
        client = self._get_client(10)
        resp = await client.get(f"{self.base_url}/versions", headers=self._headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    async def detect_networks(self) -> Dict[str, Any]:
        """Get detected host/container networks from the sidecar."""
        client = self._get_client(30)
        resp = await client.get(f"{self.base_url}/detect-networks", headers=self._headers, timeout=30)
        resp.raise_for_status()
        return resp.json()

    async def ping(
        self,
        target: str,
        count: int = 3,
    ) -> Dict[str, Any]:
        """Ping a target to check reachability."""
        return await self._post(
            "/scan/ping",
            {"target": target, "count": count, "timeout": 30},
            timeout=30,
        )

    async def tcp_probe(
        self,
        target: str,
        ports: List[int],
        connect_timeout: float = 1.0,
        concurrency: int = 64,
        max_hosts: int = 1024,
        timeout: int = 60,
        stop_on_first_open: bool = False,
    ) -> Dict[str, Any]:
        """Probe TCP reachability from the scanner agent network namespace."""
        payload = {
            "target": target,
            "ports": ports,
            "connect_timeout": connect_timeout,
            "concurrency": concurrency,
            "max_hosts": max_hosts,
            "stop_on_first_open": stop_on_first_open,
        }
        try:
            return await self._post("/scan/tcp-probe", payload, timeout=timeout)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in {404, 405}:
                raise
            logger.warning(
                "Scanner agent does not expose /scan/tcp-probe; falling back to nmap TCP connect probe"
            )
            return await self._tcp_probe_via_nmap(target, ports, timeout=timeout)

    async def _tcp_probe_via_nmap(
        self,
        target: str,
        ports: List[int],
        timeout: int = 60,
    ) -> Dict[str, Any]:
        """Compatibility fallback for older scanner agents without /scan/tcp-probe."""
        port_list = ",".join(str(port) for port in ports if isinstance(port, int) and 1 <= port <= 65535)
        if not port_list:
            return {"target": target, "ports": ports, "hosts": [], "duration_seconds": 0}

        result = await self.nmap(
            target,
            [
                "-Pn",
                "-sT",
                "-p",
                port_list,
                "--max-retries",
                "1",
                "--host-timeout",
                "5s",
                "-T4",
                "-n",
                "-oX",
                "-",
            ],
            timeout=timeout,
        )
        hosts = self._parse_tcp_probe_nmap_xml(result.get("stdout", ""))
        return {
            "target": target,
            "ports": ports,
            "hosts": hosts,
            "duration_seconds": result.get("duration_seconds", 0),
            "fallback": "nmap",
        }

    def _parse_tcp_probe_nmap_xml(self, stdout: str) -> List[Dict[str, Any]]:
        try:
            root = ElementTree.fromstring(stdout)
        except Exception:
            return []

        hosts: List[Dict[str, Any]] = []
        for host_node in root.findall("host"):
            ip = None
            for address in host_node.findall("address"):
                if address.attrib.get("addrtype") in {"ipv4", "ipv6"}:
                    ip = address.attrib.get("addr")
                    break
            if not ip:
                continue

            responses: List[Dict[str, Any]] = []
            open_ports: List[Dict[str, Any]] = []
            first_refused_port: int | None = None

            ports_node = host_node.find("ports")
            if ports_node is not None:
                for port_node in ports_node.findall("port"):
                    try:
                        port = int(port_node.attrib.get("portid", "0"))
                    except ValueError:
                        continue
                    state_node = port_node.find("state")
                    nmap_state = state_node.attrib.get("state") if state_node is not None else None
                    if nmap_state == "open":
                        state = "open"
                        open_ports.append({"port": port, "service": "", "version": ""})
                    elif nmap_state == "closed":
                        state = "refused"
                        if first_refused_port is None:
                            first_refused_port = port
                    else:
                        state = "none"
                    responses.append({"port": port, "state": state})

            source = None
            if open_ports:
                source = f"tcp:{open_ports[0]['port']}"
            elif first_refused_port is not None:
                source = f"tcp_refused:{first_refused_port}"

            hosts.append(
                {
                    "ip": ip,
                    "reachable": bool(open_ports) or first_refused_port is not None,
                    "source": source,
                    "open_ports": open_ports,
                    "responses": responses,
                }
            )

        return hosts

    async def arp_cache(self, target: str) -> Dict[str, Any]:
        """Ping target then read ARP cache to get MAC address."""
        return await self._post(
            "/scan/arp-cache",
            {"target": target, "timeout": 15},
            timeout=20,
        )

    async def neighbors(self, subnet: str | None = None) -> Dict[str, Any]:
        """Read the sidecar neighbor cache, optionally filtered to a subnet."""
        payload: Dict[str, Any] = {}
        if subnet:
            payload["subnet"] = subnet
        return await self._post(
            "/scan/neighbors",
            payload,
            timeout=15,
        )

    async def mac_vendor(self, mac: str) -> Dict[str, Any]:
        """Resolve a MAC/OUI prefix to a vendor name using the sidecar's offline data."""
        return await self._post(
            "/scan/mac-vendor",
            {"mac": mac},
            timeout=15,
        )


    async def kill_target(self, target: str) -> Dict[str, Any]:
        """Kill all running tool processes for a target IP on the sidecar."""
        try:
            client = self._get_client(10)
            resp = await client.post(
                f"{self.base_url}/kill",
                json={"target": target},
                headers=self._headers,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("Failed to kill sidecar processes for %s: %s", target, exc)
            return {"killed": 0, "error": str(exc)}

    async def kill_all(self) -> Dict[str, Any]:
        """Kill ALL running tool processes on the sidecar. Used during orphan recovery."""
        try:
            client = self._get_client(10)
            resp = await client.post(
                f"{self.base_url}/kill-all",
                json={},
                headers=self._headers,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("Failed to kill all sidecar processes: %s", exc)
            return {"killed": 0, "error": str(exc)}

    async def rotate_key(self, new_key: str) -> Dict[str, Any]:
        """Push a new API key to the sidecar, then update local headers."""
        client = self._get_client(10)
        resp = await client.post(
            f"{self.base_url}/rotate-key",
            json={"new_key": new_key},
            headers=self._headers,
            timeout=10,
        )
        resp.raise_for_status()
        result = resp.json()
        # Update local headers after successful sidecar update
        self._headers["X-Tools-Key"] = new_key
        return result


tools_client = ToolsClient()
