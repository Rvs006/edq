"""Wobbly Cable Handler - monitors device reachability during test execution."""

import asyncio
import logging
from datetime import datetime, timezone

from app.models.database import async_session
from app.models.test_run import TestRun, TestRunStatus, normalize_test_run_status
from app.services.connectivity_probe import probe_device_connectivity

logger = logging.getLogger("edq.wobbly_cable")


class WobblyCableHandler:
    FAIL_THRESHOLD = 3
    RETRY_INTERVAL = 30
    STABILITY_WAIT = 10
    TIMEOUT_MINUTES = 5
    PING_INTERVAL = 5

    def __init__(self, ip: str, run_id: str, ws_manager, probe_ports: list[int] | None = None):
        self.ip = ip
        self.run_id = run_id
        self.manager = ws_manager
        self.probe_ports = probe_ports or []
        self.is_running = True
        self.is_paused = False
        self.consecutive_failures = 0

    async def check_connectivity(self) -> bool:
        """Return True when the device is reachable on the network."""
        try:
            reachable, _probe_method = await probe_device_connectivity(self.ip, self.probe_ports)
            return reachable
        except Exception as exc:
            logger.warning("Connectivity probe error for %s: %s", self.ip, exc)
            return False

    async def monitor(self) -> None:
        """Continuous monitoring loop during test execution."""
        logger.info("Cable monitor started for run %s (device %s)", self.run_id, self.ip)
        try:
            while self.is_running:
                reachable = await self.check_connectivity()

                if reachable:
                    if self.is_paused:
                        logger.info(
                            "Device %s reachable again while run %s is paused; verifying stability",
                            self.ip,
                            self.run_id,
                        )
                        await asyncio.sleep(self.STABILITY_WAIT)
                        if await self.check_connectivity():
                            await self._resume_testing()
                    self.consecutive_failures = 0
                else:
                    self.consecutive_failures += 1
                    logger.debug(
                        "Probe failure %d/%d for %s",
                        self.consecutive_failures,
                        self.FAIL_THRESHOLD,
                        self.ip,
                    )

                    if self.consecutive_failures >= self.FAIL_THRESHOLD and not self.is_paused:
                        await self.pause_for_disconnect()
                        await self._wait_for_reconnection()

                await asyncio.sleep(self.PING_INTERVAL)
        except asyncio.CancelledError:
            logger.info("Cable monitor cancelled for run %s", self.run_id)
        except Exception as exc:
            logger.error("Cable monitor error for run %s: %s", self.run_id, exc)

    async def pause_for_disconnect(self, message: str | None = None, kill_tools: bool = True) -> None:
        """Pause the test run and broadcast a cable disconnect event."""
        self.is_paused = True
        logger.warning(
            "Cable disconnected detected for run %s (device %s) - pausing",
            self.run_id,
            self.ip,
        )

        try:
            async with async_session() as session:
                from sqlalchemy import select

                result = await session.execute(select(TestRun).where(TestRun.id == self.run_id))
                run = result.scalar_one_or_none()
                if run and normalize_test_run_status(run.status) not in {
                    TestRunStatus.COMPLETED.value,
                    TestRunStatus.CANCELLED.value,
                    TestRunStatus.FAILED.value,
                }:
                    run.status = TestRunStatus.PAUSED_CABLE
                    await session.commit()
        except Exception as exc:
            logger.error("Failed to update run status to paused: %s", exc)

        if kill_tools:
            try:
                from app.services.tools_client import tools_client

                kill_result = await tools_client.kill_target(self.ip)
                logger.info(
                    "Paused run %s after disconnect - killed %s active sidecar process(es)",
                    self.run_id,
                    kill_result.get("killed", 0),
                )
            except Exception as exc:
                logger.warning("Failed to kill active scans for %s: %s", self.ip, exc)

        await self.manager.broadcast(
            f"test-run:{self.run_id}",
            {
                "type": "cable_disconnected",
                "data": {
                    "run_id": self.run_id,
                    "device_ip": self.ip,
                    "message": message or "Device connectivity lost - testing paused",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
        )

    async def _wait_for_reconnection(self) -> None:
        """Poll until the device comes back, or notify after timeout."""
        logger.info("Waiting for reconnection to %s (timeout %dm)", self.ip, self.TIMEOUT_MINUTES)
        elapsed = 0
        max_wait = self.TIMEOUT_MINUTES * 60

        while self.is_running and elapsed < max_wait:
            await asyncio.sleep(self.RETRY_INTERVAL)
            elapsed += self.RETRY_INTERVAL

            reachable = await self.check_connectivity()
            if reachable:
                logger.info(
                    "Device %s back online - waiting %ds for stability",
                    self.ip,
                    self.STABILITY_WAIT,
                )
                await asyncio.sleep(self.STABILITY_WAIT)

                if await self.check_connectivity():
                    await self._resume_testing()
                    return

                logger.warning("Device %s went down again during stability wait", self.ip)

        if elapsed >= max_wait:
            await self._mark_paused_cable()

    async def _resume_testing(self) -> None:
        """Resume the test run after reconnection."""
        self.is_paused = False
        self.consecutive_failures = 0
        logger.info("Resuming test run %s after cable reconnection", self.run_id)

        try:
            async with async_session() as session:
                from sqlalchemy import select

                result = await session.execute(select(TestRun).where(TestRun.id == self.run_id))
                run = result.scalar_one_or_none()
                if run and normalize_test_run_status(run.status) == TestRunStatus.PAUSED_CABLE.value:
                    run.status = TestRunStatus.RUNNING
                    if not run.started_at:
                        run.started_at = datetime.now(timezone.utc)
                    await session.commit()
        except Exception as exc:
            logger.error("Failed to update run status to running: %s", exc)

        await self.manager.broadcast(
            f"test-run:{self.run_id}",
            {
                "type": "cable_reconnected",
                "data": {
                    "run_id": self.run_id,
                    "device_ip": self.ip,
                    "message": "Device connectivity restored - testing resumed",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
        )

    async def _mark_paused_cable(self) -> None:
        """Leave the run paused and notify the UI after extended downtime."""
        logger.error(
            "Device %s unreachable for %d minutes - marking run %s as paused",
            self.ip,
            self.TIMEOUT_MINUTES,
            self.run_id,
        )

        try:
            async with async_session() as session:
                from sqlalchemy import select

                result = await session.execute(select(TestRun).where(TestRun.id == self.run_id))
                run = result.scalar_one_or_none()
                if run:
                    run.status = TestRunStatus.PAUSED_CABLE
                    await session.commit()
        except Exception as exc:
            logger.error("Failed to update run status to paused (timeout): %s", exc)

        await self.manager.broadcast(
            f"test-run:{self.run_id}",
            {
                "type": "cable_timeout",
                "data": {
                    "run_id": self.run_id,
                    "device_ip": self.ip,
                    "message": f"Device unreachable for {self.TIMEOUT_MINUTES} minutes - intervention required",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
        )

    def stop(self) -> None:
        """Stop the monitoring loop."""
        self.is_running = False
