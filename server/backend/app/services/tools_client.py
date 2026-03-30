"""Async HTTP client for the EDQ tools sidecar container."""

import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings

logger = logging.getLogger("edq.services.tools_client")

_RETRYABLE_STATUS = {502, 503, 504}
_MAX_RETRIES = 3
_RETRY_BACKOFF = 2  # seconds, doubled each retry


class ToolsClient:
    """Calls the tools sidecar REST API to execute security scans."""

    def __init__(self) -> None:
        self.base_url: str = settings.TOOLS_SIDECAR_URL
        self._headers: Dict[str, str] = {}
        if settings.TOOLS_API_KEY:
            self._headers["X-Tools-Key"] = settings.TOOLS_API_KEY

    async def _post(
        self,
        path: str,
        payload: Dict[str, Any],
        timeout: int = 300,
    ) -> Dict[str, Any]:
        last_exc: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=timeout + 10) as client:
                    resp = await client.post(
                        f"{self.base_url}{path}",
                        json=payload,
                        headers=self._headers,
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

    async def health(self) -> Dict[str, Any]:
        """Check sidecar health and tool availability."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{self.base_url}/health", headers=self._headers)
            resp.raise_for_status()
            return resp.json()

    async def nmap(
        self,
        target: str,
        args: Optional[List[str]] = None,
        timeout: int = 300,
    ) -> Dict[str, Any]:
        """Run nmap scan."""
        return await self._post(
            "/scan/nmap",
            {"target": target, "args": args or [], "timeout": timeout},
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
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{self.base_url}/versions", headers=self._headers)
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


    async def rotate_key(self, new_key: str) -> Dict[str, Any]:
        """Push a new API key to the sidecar, then update local headers."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{self.base_url}/rotate-key",
                json={"new_key": new_key},
                headers=self._headers,
            )
            resp.raise_for_status()
            result = resp.json()
        # Update local headers after successful sidecar update
        self._headers["X-Tools-Key"] = new_key
        return result


tools_client = ToolsClient()
