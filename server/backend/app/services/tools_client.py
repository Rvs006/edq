"""Async HTTP client for the EDQ tools sidecar container."""

from typing import Any, Dict, List, Optional

import httpx

from app.config import settings


class ToolsClient:
    """Calls the tools sidecar REST API to execute security scans."""

    def __init__(self) -> None:
        self.base_url: str = settings.TOOLS_SIDECAR_URL

    async def _post(
        self,
        path: str,
        payload: Dict[str, Any],
        timeout: int = 300,
    ) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=timeout + 10) as client:
            resp = await client.post(
                f"{self.base_url}{path}",
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

    async def health(self) -> Dict[str, Any]:
        """Check sidecar health and tool availability."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{self.base_url}/health")
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
            resp = await client.get(f"{self.base_url}/versions")
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


tools_client = ToolsClient()
