"""Async HTTP client for the EDQ tools sidecar container."""

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Callable, Coroutine, Dict, List, Optional

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
        if exc.response.status_code in (401, 403, 429, 502, 503, 504):
            return 503 if exc.response.status_code in (502, 503, 504) else 502
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
        # Detect Docker environment — nmap needs -sT -Pn through NAT
        import os
        self.in_docker: bool = os.path.exists("/.dockerenv")
        self._client: Optional[httpx.AsyncClient] = None

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
            await self._client.aclose()
            self._client = None

    def docker_nmap_flags(self, args: List[str]) -> List[str]:
        """Adjust nmap flags for container NAT without breaking discovery scans."""
        if not self.in_docker:
            return list(args)
        if "-sn" in args or "-PR" in args:
            return list(args)
        adjusted = []
        for a in args:
            if a == "-sS":
                adjusted.append("-sT")
            else:
                adjusted.append(a)
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
        """POST to a streaming SSE endpoint, calling on_line for each stdout line.

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
                    if event.get("type") == "stdout" and on_line:
                        await on_line(event.get("line", ""))
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

    async def health(self) -> Dict[str, Any]:
        """Check sidecar health and tool availability."""
        client = self._get_client(10)
        resp = await client.get(f"{self.base_url}/health", headers=self._headers, timeout=10)
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
