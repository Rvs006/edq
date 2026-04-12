"""Wobbly Cable Handler - monitors device reachability during test execution."""

import asyncio
import logging
import time
from datetime import datetime, timezone

from app.models.database import async_session
from app.models.test_run import TestRun, TestRunStatus, normalize_test_run_status
from app.services.connectivity_probe import probe_device_connectivity
from app.utils.datetime import utcnow_naive

logger = logging.getLogger("edq.wobbly_cable")

# ---------------------------------------------------------------------------
# Handler registry — allows REST endpoints (pause-cable, resume) to look up
# the live in-memory handler for a running test and sync state changes.
# ---------------------------------------------------------------------------
_active_handlers: dict[str, "WobblyCableHandler"] = {}


def get_cable_handler(run_id: str) -> "WobblyCableHandler | None":
    """Return the live cable handler for *run_id*, or None if not active."""
    return _active_handlers.get(run_id)


class WobblyCableHandler:
    FAIL_THRESHOLD = 3
    RETRY_INTERVAL = 5
    STABILITY_WAIT = 8
    TIMEOUT_MINUTES = 5
    PING_INTERVAL = 3
    MAX_PING_INTERVAL = 30
    TCP_GRACE_SECONDS = 45

    def __init__(self, ip: str, run_id: str, ws_manager, probe_ports: list[int] | None = None):
        self.ip = ip
        self.run_id = run_id
        self.manager = ws_manager
        self.probe_ports = probe_ports or []
        self.is_running = True
        self.is_paused = False
        # When True, the monitor loop will NOT auto-resume even if the
        # device is reachable.  Set by manual pause actions (Flag Cable
        # button, general pause).  Cleared only by an explicit resume.
        self.is_manually_paused = False
        self.consecutive_failures = 0
        self._resume_lock = asyncio.Lock()
        # Monotonic timestamp until which TCP failures are tolerated after
        # a cable reconnection.  Prevents the "flapping" bug where TCP
        # services haven't started yet but ICMP is already up.
        self._tcp_grace_until: float = 0.0
        _active_handlers[self.run_id] = self

    def update_probe_ports(self, ports: list[int]) -> None:
        """Hot-update the port list used for TCP reachability probes."""
        self.probe_ports = ports

    async def check_connectivity(self, require_tcp: bool = True) -> bool:
        """Return True when the device is reachable.

        When *require_tcp* is False, ICMP-only responses are accepted.
        This is used during reconnection detection where a ping is
        sufficient to prove the cable is connected.
        """
        try:
            _reachable, probe_method = await probe_device_connectivity(self.ip, self.probe_ports)
            if not probe_method:
                return False
            if require_tcp:
                return probe_method.startswith("tcp:")
            return True
        except Exception as exc:
            logger.warning("Connectivity probe error for %s: %s", self.ip, exc)
            return False

    async def monitor(self) -> None:
        """Continuous monitoring loop during test execution."""
        logger.info("Cable monitor started for run %s (device %s)", self.run_id, self.ip)
        probe_interval = self.PING_INTERVAL
        try:
            while self.is_running:
                now_mono = time.monotonic()
                in_grace = now_mono < self._tcp_grace_until

                # During cable-paused state or TCP grace period, accept ICMP.
                require_tcp = not self.is_paused and not in_grace
                reachable = await self.check_connectivity(require_tcp=require_tcp)

                # Always broadcast probe status — including during paused
                # state — so the frontend can show reconnection progress.
                await self.manager.broadcast(
                    f"test-run:{self.run_id}",
                    {
                        "type": "cable_probe",
                        "data": {
                            "reachable": reachable,
                            "consecutive_failures": self.consecutive_failures,
                            "fail_threshold": self.FAIL_THRESHOLD,
                            "paused": self.is_paused,
                            "in_grace": in_grace,
                            "manually_paused": self.is_manually_paused,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    },
                )

                if reachable:
                    if self.is_paused and not self.is_manually_paused:
                        # Only auto-resume if the pause was caused by a
                        # detected cable disconnect, NOT by a manual action.
                        logger.info(
                            "Device %s reachable again while run %s is paused; verifying stability",
                            self.ip,
                            self.run_id,
                        )
                        await asyncio.sleep(self.STABILITY_WAIT)
                        if await self.check_connectivity(require_tcp=False):
                            await self._resume_testing()
                    async with self._resume_lock:
                        self.consecutive_failures = 0
                    probe_interval = self.PING_INTERVAL
                else:
                    # During TCP grace period, don't count failures toward
                    # the disconnect threshold — TCP services may still be
                    # booting after a cable reconnection.
                    if in_grace:
                        logger.debug(
                            "TCP probe failed for %s but in grace period (%ds left)",
                            self.ip,
                            int(self._tcp_grace_until - now_mono),
                        )
                    else:
                        async with self._resume_lock:
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
                            probe_interval = self.PING_INTERVAL
                        else:
                            probe_interval = min(probe_interval * 2, self.MAX_PING_INTERVAL)

                await asyncio.sleep(probe_interval)
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

    def manual_pause(self) -> None:
        """Mark the handler as manually paused (prevents auto-resume)."""
        self.is_paused = True
        self.is_manually_paused = True

    async def _wait_for_reconnection(self) -> None:
        """Poll until the device comes back, or notify after timeout.

        Exits early if the run is resumed externally (e.g. via REST),
        which clears ``is_paused``.
        """
        logger.info("Waiting for reconnection to %s (timeout %dm)", self.ip, self.TIMEOUT_MINUTES)
        elapsed = 0
        attempt = 0
        max_wait = self.TIMEOUT_MINUTES * 60

        while self.is_running and self.is_paused and elapsed < max_wait:
            # Fast initial polling (5s), with gentle backoff up to 15s
            interval = min(self.RETRY_INTERVAL * (1 + attempt // 3), 15)
            await asyncio.sleep(interval)
            elapsed += interval
            attempt += 1

            # Exit immediately if resumed externally (REST resume endpoint)
            if not self.is_paused:
                logger.info("Run %s was resumed externally during reconnection wait", self.run_id)
                return

            reachable = await self.check_connectivity(require_tcp=False)

            # Broadcast reconnection progress so the UI can show it
            # Use live state instead of hardcoded values
            await self.manager.broadcast(
                f"test-run:{self.run_id}",
                {
                    "type": "cable_probe",
                    "data": {
                        "reachable": reachable,
                        "consecutive_failures": self.consecutive_failures,
                        "fail_threshold": self.FAIL_THRESHOLD,
                        "paused": self.is_paused,
                        "in_grace": time.monotonic() < self._tcp_grace_until,
                        "manually_paused": self.is_manually_paused,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                },
            )

            if reachable:
                logger.info(
                    "Device %s back online - waiting %ds for stability",
                    self.ip,
                    self.STABILITY_WAIT,
                )
                await asyncio.sleep(self.STABILITY_WAIT)

                if await self.check_connectivity(require_tcp=False):
                    await self._resume_testing()
                    return

                logger.warning("Device %s went down again during stability wait", self.ip)

        if self.is_paused and elapsed >= max_wait:
            await self._mark_paused_cable()

    async def _resume_testing(self) -> None:
        """Resume the test run after reconnection (idempotent)."""
        async with self._resume_lock:
            if not self.is_paused:
                return
            self.is_paused = False
            self.is_manually_paused = False
            self.consecutive_failures = 0
            # Start TCP grace period — don't require TCP for 45s after resume
            # because services need time to bind ports after link-up.
            self._tcp_grace_until = time.monotonic() + self.TCP_GRACE_SECONDS

        logger.info("Resuming test run %s after cable reconnection (TCP grace %ds)", self.run_id, self.TCP_GRACE_SECONDS)

        try:
            async with async_session() as session:
                from sqlalchemy import select

                result = await session.execute(select(TestRun).where(TestRun.id == self.run_id))
                run = result.scalar_one_or_none()
                if run and normalize_test_run_status(run.status) == TestRunStatus.PAUSED_CABLE.value:
                    run.status = TestRunStatus.RUNNING
                    if not run.started_at:
                        run.started_at = utcnow_naive()
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
        """Stop the monitoring loop and unregister from the handler registry."""
        self.is_running = False
        _active_handlers.pop(self.run_id, None)
