"""One ingestion cycle — the single path both the scheduler and the manual trigger use.

There is deliberately no second implementation. ``POST /ingest`` and the scheduled tick
call :func:`run_cycle`, so an operator triggering a run exercises exactly the code that
runs unattended, and a bug cannot hide in the path nobody exercises.

**Each source family is independent.** One family failing must not stop the others: a
news outage is a fact about news, not a reason for market data to go stale. Every family
records its own run and its own health, and a failure inside one is caught and recorded
rather than allowed to abort the cycle.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from .models import Coverage, CoverageRecord, CoverageStatus, IngestRun, RunStatus
from .pipeline import run_disclosure_pipeline, run_market_pipeline, run_news_pipeline
from .watchpoints import evaluate

if TYPE_CHECKING:
    from collections.abc import Callable

    from .ports import (
        AssessmentStore,
        DisclosureSource,
        Extractor,
        MarketSource,
        NewsSource,
        WatchPointStore,
    )

__all__ = ["CycleResult", "IngestionSources", "run_cycle"]

log = logging.getLogger("smart_watchlist.ingestion")


@dataclass(frozen=True)
class IngestionSources:
    """Everything a cycle needs. Passed in, so tests can substitute any of it."""

    market: MarketSource
    disclosures: DisclosureSource
    news: NewsSource
    extractor: Extractor
    fallback: Extractor | None = None


@dataclass
class CycleResult:
    """What one cycle did, per family, for logs and the status endpoint."""

    started_at: datetime
    finished_at: datetime | None = None
    runs: list[IngestRun] = field(default_factory=list)
    assessed: int = 0
    triggered: int = 0
    """Watch points satisfied by this cycle's stored bars. Not assessments — a reader's
    own level being crossed is private state, never a shared verdict (D37)."""

    @property
    def healthy_families(self) -> list[str]:
        return [run.source for run in self.runs if run.is_healthy]

    @property
    def failed_families(self) -> list[str]:
        return [run.source for run in self.runs if not run.is_healthy]

    @property
    def outcome(self) -> str:
        if not self.runs:
            return "failed"
        if not self.failed_families:
            return "succeeded"
        return "failed" if not self.healthy_families else "partial"


def run_cycle(
    sources: IngestionSources,
    store: AssessmentStore,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    watch_points: WatchPointStore | None = None,
) -> CycleResult:
    """Fetch, evaluate and persist for every source family.

    Never raises. A family that fails is recorded as a failed run with its own coverage
    marked unavailable, and the cycle continues — because the alternative is one bad
    provider silently freezing the whole system's view of the world.
    """
    result = CycleResult(started_at=now())

    # Market first: disclosures and news both attach market context to what they find,
    # so observing prices before reading about them gives the later families something
    # to corroborate against within the same cycle.
    for family, action in (
        ("market", lambda: run_market_pipeline(sources.market, store)),
        (
            "nse-disclosures",
            lambda: run_disclosure_pipeline(sources.disclosures, store, market=sources.market),
        ),
        (
            "news",
            lambda: run_news_pipeline(
                sources.news,
                sources.extractor,
                store,
                market=sources.market,
                fallback=sources.fallback,
            ),
        ),
    ):
        try:
            run, assessments = action()
            result.runs.append(run)
            result.assessed += len(assessments)
            log.info(
                "ingest.family.done family=%s status=%s healthy=%s assessed=%d",
                family,
                run.status.value,
                run.is_healthy,
                len(assessments),
            )
        except Exception as error:
            failed = _record_failure(store, family, result.started_at, now(), error)
            result.runs.append(failed)
            log.exception("ingest.family.failed family=%s", family)

    # After the families, because it reads the bars they just stored and nothing else.
    # A reader's level is settled by the same end-of-day data every other verdict uses.
    result.triggered = _settle_watch_points(store, watch_points)

    result.finished_at = now()
    log.info(
        "ingest.cycle.done outcome=%s assessed=%d healthy=%s failed=%s",
        result.outcome,
        result.assessed,
        ",".join(result.healthy_families) or "-",
        ",".join(result.failed_families) or "-",
    )
    return result


def _record_failure(
    store: AssessmentStore,
    family: str,
    started_at: datetime,
    finished_at: datetime,
    error: Exception,
) -> IngestRun:
    """Persist a failed attempt so the failure is visible rather than merely absent.

    The detail records the exception *type*, never its message: a provider error can echo
    the request, and a request carries credentials.
    """
    detail = f"Ingestion failed: {type(error).__name__}."

    # The pipeline records its run before fetching, so a failure normally has an in-flight
    # row already. Reconcile that one; a second row would leave the RUNNING record newest
    # and the failure invisible.
    if store.fail_running_runs(family, detail, finished_at):
        existing = store.latest_run(family)
        if existing is not None:
            return existing

    run = IngestRun(
        run_id=f"{family}:{started_at.isoformat()}",
        source=family,
        started_at=started_at,
        coverage=Coverage(
            records=(
                CoverageRecord(
                    source=family,
                    status=CoverageStatus.UNAVAILABLE,
                    observed_at=finished_at,
                    detail=detail,
                ),
            )
        ),
        assessed_count=0,
        status=RunStatus.FAILED,
        finished_at=finished_at,
        detail=detail,
    )
    store.save_run(run)
    return run


def _settle_watch_points(store: AssessmentStore, points: WatchPointStore | None) -> int:
    """Check every open watch point against stored bars, and record what crossed.

    Reads persisted bars rather than fetching: the cycle has just written them, and a
    second fetch would be a second opinion about the same session. Never raises — a
    failure here must not turn a healthy ingestion cycle into a failed one, because the
    families' own health is a claim about sources and this is not.
    """
    if points is None:
        return 0
    try:
        open_points = points.open_watch_points()
        if not open_points:
            return 0
        bars = store.price_bars(sorted({point.symbol for point in open_points}))
        settled = 0
        for point in open_points:
            trigger = evaluate(point, bars.get(point.symbol, []))
            if trigger is not None and points.mark_triggered(
                point.point_id, trigger.on, trigger.close
            ):
                settled += 1
                log.info(
                    "watchpoint.triggered symbol=%s level=%s on=%s",
                    point.symbol,
                    point.level,
                    trigger.on.isoformat(),
                )
        return settled
    except Exception:
        log.exception("watchpoint.settle.failed")
        return 0
