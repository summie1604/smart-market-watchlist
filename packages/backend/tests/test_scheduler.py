"""Scheduled ingestion: cycles, overlap, failure isolation and crash safety.

No real sleeps and no wall-clock dependence. Cycles are invoked directly or driven by a
controllable clock, because a scheduler tested with sleeps is a scheduler tested slowly
and flakily.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from smart_watchlist.adapters.rule_extractor import RuleExtractor
from smart_watchlist.adapters.sqlite_store import SqliteAssessmentStore
from smart_watchlist.api.scheduler import IngestionScheduler, SchedulerConfig
from smart_watchlist.core.ingestion import IngestionSources, run_cycle
from smart_watchlist.core.models import (
    CoverageRecord,
    CoverageStatus,
    Evidence,
    IngestRun,
    RunStatus,
    SourceTier,
)

START = datetime(2026, 9, 5, 9, 0, tzinfo=UTC)


class Clock:
    """A clock the test moves. Nothing here waits on the real one."""

    def __init__(self, start: datetime = START) -> None:
        self.now = start

    def __call__(self) -> datetime:
        self.now += timedelta(milliseconds=1)
        return self.now


def article(ref: str, symbol: str = "RELIANCE") -> Evidence:
    return Evidence(
        source="news",
        source_ref=ref,
        tier=SourceTier.CREDIBLE_REPORTING,
        publisher="Reuters",
        subject_company="Reliance Industries",
        retrieved_at=START,
        published_at=START,
        title="Reliance signs a supply agreement with a partner",
        body="",
        url="https://example.invalid",
        security_symbol=symbol,
        category="News",
    )


def ok(source: str) -> CoverageRecord:
    return CoverageRecord(source=source, status=CoverageStatus.OK, observed_at=START, detail="stub")


class StubMarket:
    name = "market"

    def __init__(self, bars: dict[str, list] | None = None, fail: bool = False) -> None:
        self._bars = bars or {}
        self._fail = fail

    def fetch(self, symbols):
        if self._fail:
            raise RuntimeError("market provider is down")
        return dict(self._bars), ok("market")


class StubDisclosures:
    name = "nse-disclosures"

    def __init__(self, evidence: list[Evidence] | None = None, fail: bool = False) -> None:
        self._evidence = evidence or []
        self._fail = fail

    def fetch(self):
        if self._fail:
            raise RuntimeError("exchange endpoint is down")
        return list(self._evidence), ok("nse-disclosures")


class StubNews:
    name = "news"

    def __init__(self, evidence: list[Evidence] | None = None, fail: bool = False) -> None:
        self._evidence = evidence or []
        self._fail = fail

    def fetch(self, companies):
        if self._fail:
            raise RuntimeError("news provider is down")
        return list(self._evidence), ok("news")


class QuotaExhaustedExtractor:
    """Stands in for Gemini once the daily budget is gone."""

    name = "google/stub/exhausted"

    def __init__(self) -> None:
        self.calls = 0

    def extract(self, evidence):
        self.calls += 1
        return None


def sources(**overrides) -> IngestionSources:
    base = {
        "market": StubMarket(),
        "disclosures": StubDisclosures(),
        "news": StubNews(),
        "extractor": RuleExtractor(),
        "fallback": None,
    }
    return IngestionSources(**{**base, **overrides})


# --- cycles -------------------------------------------------------------------


def test_a_successful_cycle_records_every_family(tmp_path) -> None:
    store = SqliteAssessmentStore(tmp_path / "s.db")

    result = run_cycle(sources(news=StubNews([article("a1")])), store, Clock())

    assert result.outcome == "succeeded"
    assert set(result.healthy_families) == {"market", "nse-disclosures", "news"}
    assert result.finished_at is not None
    for family in ("market", "nse-disclosures", "news"):
        run = store.latest_run(family)
        assert run is not None and run.status is RunStatus.COMPLETED


def test_a_zero_evidence_cycle_is_still_recorded_as_healthy(tmp_path) -> None:
    """A quiet fetch is a conclusion; only a failure is an admission."""
    store = SqliteAssessmentStore(tmp_path / "s.db")

    result = run_cycle(sources(), store, Clock())

    assert result.assessed == 0
    assert result.outcome == "succeeded"


@pytest.mark.parametrize("broken", ["news", "market", "disclosures"])
def test_one_family_failing_does_not_stop_the_others(tmp_path, broken) -> None:
    """A news outage is a fact about news, not a reason for market data to go stale."""
    store = SqliteAssessmentStore(tmp_path / "s.db")
    kinds = {
        "news": StubNews(fail=True),
        "market": StubMarket(fail=True),
        "disclosures": StubDisclosures(fail=True),
    }

    result = run_cycle(sources(**{broken: kinds[broken]}), store, Clock())

    assert result.outcome == "partial"
    assert result.healthy_families, "the healthy families still updated"
    assert result.failed_families


def test_a_failed_family_persists_a_failed_run(tmp_path) -> None:
    """The failure must be visible, not merely absent."""
    store = SqliteAssessmentStore(tmp_path / "s.db")

    run_cycle(sources(news=StubNews(fail=True)), store, Clock())

    run = store.latest_run("news")
    assert run is not None
    assert run.status is RunStatus.FAILED
    assert not run.is_healthy
    assert "RuntimeError" in run.detail, "the type, never the message"


def test_a_failed_cycle_does_not_leave_old_health_looking_current(tmp_path) -> None:
    """The Step 0 invariant, applied to scheduled runs."""
    store = SqliteAssessmentStore(tmp_path / "s.db")
    run_cycle(sources(news=StubNews([article("a1")])), store, Clock())
    assert store.latest_run("news").is_healthy  # type: ignore[union-attr]

    run_cycle(sources(news=StubNews(fail=True)), store, Clock())

    assert not store.latest_run("news").is_healthy  # type: ignore[union-attr]


def test_the_model_running_out_of_quota_degrades_to_the_fallback(tmp_path) -> None:
    """Gemini exhaustion must not fail the cycle, and must not borrow its provenance."""
    store = SqliteAssessmentStore(tmp_path / "s.db")
    exhausted = QuotaExhaustedExtractor()

    result = run_cycle(
        sources(news=StubNews([article("a1")]), extractor=exhausted, fallback=RuleExtractor()),
        store,
        Clock(),
    )

    assert result.outcome == "succeeded", "a model outage is not a source outage"
    assert exhausted.calls > 0
    assert store.latest_run("news").is_healthy  # type: ignore[union-attr]


# --- idempotency across runs ---------------------------------------------------


def test_the_same_article_across_two_cycles_stays_one_evidence_record(tmp_path) -> None:
    store = SqliteAssessmentStore(tmp_path / "s.db")
    feed = StubNews([article("same-ref")])

    run_cycle(sources(news=feed), store, Clock())
    first = len(store.recent(200))
    run_cycle(sources(news=feed), store, Clock())

    assert len(store.recent(200)) == first, "a re-fetched article is not a new event"


def test_a_retry_after_failure_does_not_duplicate(tmp_path) -> None:
    store = SqliteAssessmentStore(tmp_path / "s.db")

    run_cycle(sources(news=StubNews(fail=True)), store, Clock())
    run_cycle(sources(news=StubNews([article("a1")])), store, Clock())
    after_retry = len(store.recent(200))
    run_cycle(sources(news=StubNews([article("a1")])), store, Clock())

    assert len(store.recent(200)) == after_retry


def test_each_attempt_records_its_own_run(tmp_path) -> None:
    store = SqliteAssessmentStore(tmp_path / "s.db")

    run_cycle(sources(), store, Clock())
    run_cycle(sources(), store, Clock())

    news_runs = [r for r in store.recent_runs(50) if r.source == "news"]
    assert len(news_runs) == 2, "coverage records every attempt independently"


# --- crash safety --------------------------------------------------------------


def test_an_interrupted_run_is_reclassified_at_startup(tmp_path) -> None:
    """Only a crash can leave a run RUNNING, so finding one is proof of a death."""
    store = SqliteAssessmentStore(tmp_path / "s.db")
    store.save_run(
        IngestRun(
            run_id="news:crashed",
            source="news",
            started_at=START,
            coverage=Coverage_of("news"),
            assessed_count=0,
            status=RunStatus.RUNNING,
        )
    )
    assert not store.latest_run("news").is_healthy  # type: ignore[union-attr]

    reaped = store.reap_interrupted_runs()

    assert reaped == 1
    run = store.latest_run("news")
    assert run is not None and run.status is RunStatus.INTERRUPTED
    assert not run.is_healthy


def test_a_run_in_progress_never_reads_as_healthy(tmp_path) -> None:
    store = SqliteAssessmentStore(tmp_path / "s.db")
    store.save_run(
        IngestRun(
            run_id="news:inflight",
            source="news",
            started_at=START,
            coverage=Coverage_of("news"),
            assessed_count=0,
            status=RunStatus.RUNNING,
        )
    )

    assert not store.latest_run("news").is_healthy  # type: ignore[union-attr]


def Coverage_of(source: str):
    from smart_watchlist.core.models import Coverage

    return Coverage(
        records=(
            CoverageRecord(
                source=source,
                status=CoverageStatus.UNAVAILABLE,
                observed_at=START,
                detail="Run in progress; no result reported yet.",
            ),
        )
    )


def test_assessments_never_exist_without_their_run(tmp_path) -> None:
    """The run row is written before anything it produces can be persisted."""
    store = SqliteAssessmentStore(tmp_path / "s.db")

    run_cycle(sources(news=StubNews([article("a1")])), store, Clock())

    runs = {r.source for r in store.recent_runs(50)}
    for assessment in store.recent(200):
        source = assessment.event.evidence[0].source
        assert source in runs, f"{source} produced an assessment with no run record"


# --- overlap and lifecycle ------------------------------------------------------


@pytest.mark.asyncio
async def test_a_manual_trigger_during_an_active_cycle_is_refused(tmp_path) -> None:
    store = SqliteAssessmentStore(tmp_path / "s.db")
    scheduler = IngestionScheduler(
        sources(), store, SchedulerConfig(enabled=True, run_on_startup=False), Clock()
    )
    scheduler._running = True  # simulate a cycle in flight

    assert await scheduler.trigger() is None, "busy, not queued"


@pytest.mark.asyncio
async def test_a_slow_cycle_does_not_overlap_the_next_tick(tmp_path) -> None:
    """The guard is an in-process flag; a single process needs nothing more."""
    store = SqliteAssessmentStore(tmp_path / "s.db")
    scheduler = IngestionScheduler(sources(), store, SchedulerConfig(run_on_startup=False), Clock())

    first, second = await asyncio.gather(scheduler.trigger(), scheduler.trigger())

    assert (first is None) != (second is None), "exactly one of the two ran"


@pytest.mark.asyncio
async def test_a_disabled_scheduler_never_starts(tmp_path) -> None:
    store = SqliteAssessmentStore(tmp_path / "s.db")
    scheduler = IngestionScheduler(sources(), store, SchedulerConfig(enabled=False), Clock())

    await scheduler.start()

    assert not scheduler.is_started
    await scheduler.stop()


@pytest.mark.asyncio
async def test_graceful_shutdown_while_idle(tmp_path) -> None:
    store = SqliteAssessmentStore(tmp_path / "s.db")
    scheduler = IngestionScheduler(
        sources(),
        store,
        SchedulerConfig(run_on_startup=False, interval=timedelta(hours=1)),
        Clock(),
    )
    await scheduler.start()
    assert scheduler.is_started

    await scheduler.stop()

    assert not scheduler.is_started


@pytest.mark.asyncio
async def test_shutdown_waits_for_an_active_cycle_rather_than_killing_it(tmp_path) -> None:
    """Cancelling mid-cycle would leave the run RUNNING and its work half-written."""
    store = SqliteAssessmentStore(tmp_path / "s.db")
    scheduler = IngestionScheduler(sources(), store, SchedulerConfig(run_on_startup=False), Clock())
    await scheduler.start()

    cycle = asyncio.create_task(scheduler.trigger())
    await asyncio.sleep(0)
    await scheduler.stop(drain_timeout=5.0)
    await cycle

    assert not scheduler.is_running_cycle
    for family in ("market", "nse-disclosures", "news"):
        run = store.latest_run(family)
        assert run is not None and run.status is not RunStatus.RUNNING


@pytest.mark.asyncio
async def test_the_status_answers_the_operational_questions(tmp_path) -> None:
    store = SqliteAssessmentStore(tmp_path / "s.db")
    scheduler = IngestionScheduler(sources(), store, SchedulerConfig(run_on_startup=False), Clock())

    await scheduler.trigger()
    status = scheduler.status()

    assert status["enabled"] is True
    assert status["cycle_active"] is False
    assert status["cycles_completed"] == 1
    assert status["last_cycle"]["outcome"] == "succeeded"  # type: ignore[index]
    assert status["interval_seconds"]


def test_every_historical_schema_version_upgrades_to_head(tmp_path) -> None:
    """Migrations are append-only, and a stale database must reach head from anywhere.

    Regression: a migration inserted mid-list replayed the wrong statement against every
    database already past that index, so an existing store failed to open with
    "duplicate column name".
    """
    import sqlite3

    from smart_watchlist.adapters.sqlite_store import _MIGRATIONS

    for stop in range(1, len(_MIGRATIONS) + 1):
        path = tmp_path / f"v{stop}.db"
        connection = sqlite3.connect(path)
        for version, script in enumerate(_MIGRATIONS[:stop], start=1):
            connection.executescript(script)
            connection.execute(f"PRAGMA user_version = {version}")
        connection.commit()
        connection.close()

        SqliteAssessmentStore(path)  # must upgrade without raising

        connection = sqlite3.connect(path)
        at_head = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        connection.close()
        assert at_head == len(_MIGRATIONS), f"v{stop} did not reach head"
        assert "rejected_evidence" in tables
