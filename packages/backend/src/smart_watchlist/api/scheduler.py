"""In-process scheduler for unattended ingestion.

The smallest thing that makes "what changed while you were gone" operationally true: one
asyncio task in the application's own lifespan, one cycle at a time, an explicit interval.

No broker, no worker pool, no distributed lock. For a single process the lock is an
in-process flag, and that is not a shortcut — a distributed lock here would be machinery
guarding against a topology this deployment does not have (D10's rule applied to
scheduling).

Blocking work runs in a thread so the event loop stays responsive; the cycle itself is
synchronous because the pipelines are.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from ..core.ingestion import run_cycle

if TYPE_CHECKING:
    from collections.abc import Callable

    from ..core.ingestion import CycleResult, IngestionSources
    from ..core.ports import AssessmentStore, WatchPointStore

__all__ = ["IngestionScheduler", "SchedulerConfig"]

log = logging.getLogger("smart_watchlist.scheduler")


@dataclass(frozen=True)
class SchedulerConfig:
    """Deliberately four knobs. No cron expressions, no per-company schedules."""

    enabled: bool = True
    interval: timedelta = timedelta(minutes=15)
    run_on_startup: bool = True
    startup_delay: timedelta = timedelta(seconds=2)
    """A moment before the first run so application startup is not blocked behind a
    network round trip."""


class IngestionScheduler:
    """Runs :func:`run_cycle` on an interval, one cycle at a time."""

    def __init__(
        self,
        sources: IngestionSources,
        store: AssessmentStore,
        config: SchedulerConfig | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        watch_points: WatchPointStore | None = None,
    ) -> None:
        self._sources = sources
        self._store = store
        self._watch_points = watch_points
        self._config = config or SchedulerConfig()
        self._now = now
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()
        # An in-process guard, not a lock over a shared resource: it exists to stop a slow
        # cycle overlapping the next tick within this one process.
        self._running = False
        self.last_result: CycleResult | None = None
        self.next_run_at: datetime | None = None
        self.cycles_completed = 0

    @property
    def is_running_cycle(self) -> bool:
        return self._running

    @property
    def is_started(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Begin the loop. Reaps interrupted runs first.

        Anything still recorded as RUNNING can only have been left by a process that died
        mid-cycle, and until it is reclassified its partial coverage would read as current
        health.
        """
        if not self._config.enabled:
            log.info("scheduler.disabled")
            return
        reaped = self._store.reap_interrupted_runs()
        if reaped:
            log.warning("scheduler.reaped_interrupted_runs count=%d", reaped)
        self._stopping.clear()
        self._task = asyncio.create_task(self._loop())
        log.info(
            "scheduler.started interval_seconds=%d run_on_startup=%s",
            int(self._config.interval.total_seconds()),
            self._config.run_on_startup,
        )

    async def stop(self, drain_timeout: float = 30.0) -> None:
        """Stop the loop, letting an active cycle finish first.

        Cancelling outright would leave the run recorded as RUNNING and its partial work
        half-written. Waiting bounded gives the cycle a chance to reach its own
        ``_finish_run`` — and if it does not, startup will reap it as INTERRUPTED, which
        is the honest record rather than a silent gap.
        """
        self._stopping.set()

        waited = 0.0
        while self._running and waited < drain_timeout:
            await asyncio.sleep(0.05)
            waited += 0.05
        if self._running:
            log.warning("scheduler.stop_timed_out cycle_still_running=true")

        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        log.info("scheduler.stopped cycles_completed=%d", self.cycles_completed)

    async def trigger(self) -> CycleResult | None:
        """Run one cycle now. ``None`` when one is already in flight.

        The caller reports that as busy rather than queueing: two concurrent cycles would
        duplicate fetches and interleave run records for no benefit.
        """
        if self._running:
            return None
        return await self._run_once()

    async def _loop(self) -> None:
        if self._config.run_on_startup:
            await asyncio.sleep(self._config.startup_delay.total_seconds())
            if not self._stopping.is_set():
                await self._run_once()
        while not self._stopping.is_set():
            self.next_run_at = self._now() + self._config.interval
            try:
                await asyncio.wait_for(
                    self._stopping.wait(), timeout=self._config.interval.total_seconds()
                )
                return  # stop was requested during the wait
            except TimeoutError:
                pass
            if not self._stopping.is_set():
                await self._run_once()

    async def _run_once(self) -> CycleResult | None:
        if self._running:
            # A cycle outlasting its interval skips the tick rather than stacking.
            log.warning("scheduler.tick_skipped reason=cycle_still_running")
            return None
        self._running = True
        try:
            result = await asyncio.to_thread(
                run_cycle, self._sources, self._store, self._now, self._watch_points
            )
            self.last_result = result
            self.cycles_completed += 1
            return result
        finally:
            self._running = False

    def status(self) -> dict[str, object]:
        """Enough to answer the operational questions without a dashboard."""
        result = self.last_result
        return {
            "enabled": self._config.enabled,
            "started": self.is_started,
            "cycle_active": self._running,
            "interval_seconds": int(self._config.interval.total_seconds()),
            "cycles_completed": self.cycles_completed,
            "next_run_at": None if self.next_run_at is None else self.next_run_at.isoformat(),
            "last_cycle": None
            if result is None
            else {
                "started_at": result.started_at.isoformat(),
                "finished_at": None
                if result.finished_at is None
                else result.finished_at.isoformat(),
                "outcome": result.outcome,
                "assessed": result.assessed,
                "healthy_families": result.healthy_families,
                "failed_families": result.failed_families,
            },
        }
