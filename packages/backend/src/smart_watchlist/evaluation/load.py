"""Repeatable local measurements for the current single-process architecture.

These are capacity observations, not production promises. External network and model
latency are deliberately excluded and named as exclusions in the report.
"""

from __future__ import annotations

import resource
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from statistics import median
from time import perf_counter

from ..adapters.rule_extractor import RuleExtractor
from ..adapters.sqlite_store import SqliteAssessmentStore
from ..adapters.user_store import SqliteUserStore
from ..core.extraction import validate
from ..core.market import Bar
from ..core.models import (
    Assessment,
    Attention,
    Confidence,
    Coverage,
    CoverageRecord,
    CoverageStatus,
    Event,
    Evidence,
    SourceTier,
)
from ..core.prices import build_comparison
from ..core.review import assemble
from ..core.userstate import Membership

__all__ = ["LoadReport", "run_load_validation"]

TARGET_USERS = 10_000
TARGET_WATCHLIST = 50
TARGET_SECURITIES = 50
TARGET_EVIDENCE_PER_CYCLE = 500
TARGET_INTERVAL_SECONDS = 900
TARGET_REVIEW_P95_MS = 300.0
TARGET_CHART_MS = 150.0


@dataclass(frozen=True)
class LoadReport:
    review_iterations: int
    review_p50_ms: float
    review_p95_ms: float
    sqlite_review_iterations: int
    sqlite_review_p50_ms: float
    sqlite_review_p95_ms: float
    concurrent_workers: int
    concurrent_reviews_per_second: float
    extraction_items: int
    extractions_per_second: float
    chart_sessions: int
    chart_build_ms: float
    peak_rss_mb: float

    def markdown(self) -> str:
        review_result = "PASS" if self.review_p95_ms < TARGET_REVIEW_P95_MS else "MISS"
        chart_result = "PASS" if self.chart_build_ms < TARGET_CHART_MS else "MISS"
        return f"""# Scalability validation

Measured locally on `{date.today().isoformat()}`. These numbers describe this machine and
the bounded domain/SQLite paths stated below; they are not production capacity claims.

## Target workload

- {TARGET_USERS:,} active users, with at most {TARGET_WATCHLIST} watched companies each.
- {TARGET_SECURITIES} covered securities in the next curated expansion.
- Up to {TARGET_EVIDENCE_PER_CYCLE} evidence records per ingestion cycle, every {TARGET_INTERVAL_SECONDS // 60} minutes.
- Review assembly p95 below {TARGET_REVIEW_P95_MS:.0f} ms at {TARGET_WATCHLIST} companies.
- Stored chart transformation below {TARGET_CHART_MS:.0f} ms for one year of daily bars.

## Measured

| Path | Workload | Result | Target |
|---|---:|---:|---:|
| Review assembly | {self.review_iterations} sequential runs, 50 companies / 500 shared assessments | p50 {self.review_p50_ms:.2f} ms · p95 {self.review_p95_ms:.2f} ms | {review_result} (< {TARGET_REVIEW_P95_MS:.0f} ms) |
| SQLite-backed review | {self.sqlite_review_iterations} runs, including membership/checkpoint/assessment reads and issued-review write | p50 {self.sqlite_review_p50_ms:.2f} ms · p95 {self.sqlite_review_p95_ms:.2f} ms | {"PASS" if self.sqlite_review_p95_ms < TARGET_REVIEW_P95_MS else "MISS"} (< {TARGET_REVIEW_P95_MS:.0f} ms) |
| Concurrent review assembly | {self.concurrent_workers} threads over the same shared intelligence | {self.concurrent_reviews_per_second:.1f} reviews/s | observation only |
| Rule extraction + grounding | {self.extraction_items} articles | {self.extractions_per_second:.1f} articles/s | CPU floor only |
| Chart alignment + rebasing | {self.chart_sessions} daily sessions x 3 series | {self.chart_build_ms:.2f} ms | {chart_result} (< {TARGET_CHART_MS:.0f} ms) |

Peak resident memory for the validation process was **{self.peak_rss_mb:.1f} MiB**. This is
a process high-water mark, not memory attributable only to one operation.

## Exclusions and limits

- Source HTTP time, provider throttling and LLM latency are excluded. They dominate a live ingestion cycle, so this run does **not** prove that 500 live articles finish inside 15 minutes.
- The SQLite-backed review includes the persistence operations used by a request but not FastAPI/Pydantic serialization, a deployed HTTP server, TLS, process contention or device latency.
- The current product has nine curated companies and demonstration-scale accounts. The 50-company set here is synthetic and exercises algorithmic shape, not coverage quality.
- SQLite multi-writer contention is not exercised. D10's migration triggers remain multiple app instances, sustained concurrent writers or measured lock contention.

## Recommendation

The per-user read path is cheap enough that user count alone does not justify Postgres,
Redis or a queue. Measure one complete live 500-article cycle next. Split ingestion into
workers only if it cannot finish within the 15-minute interval; move from SQLite only
when a stated D10 trigger is observed.

## Evidence-based production path

1. Keep SQLite and the in-process scheduler for one application instance. Source-native
   evidence ids, stable event ids, upserted market bars and the single-cycle lock make
   retries idempotent at this scale.
2. Move to Postgres only after measured lock contention, sustained concurrent writers,
   multiple application instances, or a deployment that cannot use a durable local file.
   Preserve the existing uniqueness constraints and repository boundary during migration.
3. Move scheduling out of the web process when there is more than one web instance. Use
   one managed trigger or a leased job row keyed by source and time window; do not let every
   replica start the same cycle.
4. Add bounded workers or a queue only if a measured live cycle cannot finish inside 15
   minutes. Partition by company/source while retaining source-native idempotency keys.
5. Notifications do not exist today, so none can repeat. If introduced later, write a
   transactional outbox with a unique `(user, event, review window, channel)` key before
   delivery; a queue by itself does not prevent duplicate sends.
"""


def run_load_validation(iterations: int = 500, workers: int = 20) -> LoadReport:
    now = datetime.now(UTC)
    coverage = _coverage(now)
    memberships = [
        Membership(user_id="load-user", symbol=f"LOAD{i:02d}", added_at=now - timedelta(days=2))
        for i in range(TARGET_WATCHLIST)
    ]
    assessments = [
        _assessment(symbol=f"LOAD{company:02d}", number=event, now=now, coverage=coverage)
        for company in range(TARGET_WATCHLIST)
        for event in range(10)
    ]

    def review_once() -> None:
        assemble(
            user_id="load-user",
            memberships=memberships,
            previous_checkpoint=now - timedelta(days=1),
            review_cutoff=now,
            assessments=assessments,
            coverage=coverage,
        )

    review_timings = [_timed(review_once) for _ in range(iterations)]
    sqlite_timings = _sqlite_reviews(assessments, coverage, min(iterations, 200), now)
    concurrent_started = perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda _index: review_once(), range(iterations)))
    concurrent_elapsed = perf_counter() - concurrent_started

    extractor = RuleExtractor()
    extraction_evidence = [_news_item(number, now) for number in range(TARGET_EVIDENCE_PER_CYCLE)]
    extraction_started = perf_counter()
    for item in extraction_evidence:
        proposal = extractor.extract(item)
        if proposal is not None:
            validate(proposal, item, extractor.name)
    extraction_elapsed = perf_counter() - extraction_started

    bars = _bars(252)
    chart_started = perf_counter()
    build_comparison(
        "RELIANCE",
        "Reliance Industries",
        {"RELIANCE": bars, "^CNXENERGY": bars, "^NSEI": bars},
        sector_index="^CNXENERGY",
        sector_label="Nifty Energy",
        broad_index="^NSEI",
        broad_label="Nifty 50",
    )
    chart_elapsed = (perf_counter() - chart_started) * 1000

    ordered = sorted(review_timings)
    return LoadReport(
        review_iterations=iterations,
        review_p50_ms=median(ordered),
        review_p95_ms=_percentile(ordered, 0.95),
        sqlite_review_iterations=len(sqlite_timings),
        sqlite_review_p50_ms=median(sqlite_timings),
        sqlite_review_p95_ms=_percentile(sorted(sqlite_timings), 0.95),
        concurrent_workers=workers,
        concurrent_reviews_per_second=iterations / concurrent_elapsed,
        extraction_items=len(extraction_evidence),
        extractions_per_second=len(extraction_evidence) / extraction_elapsed,
        chart_sessions=len(bars),
        chart_build_ms=chart_elapsed,
        peak_rss_mb=_peak_rss_mb(),
    )


def _timed(action) -> float:
    started = perf_counter()
    action()
    return (perf_counter() - started) * 1000


def _percentile(values: list[float], fraction: float) -> float:
    return values[min(len(values) - 1, round((len(values) - 1) * fraction))]


def _peak_rss_mb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    bytes_used = peak if sys.platform == "darwin" else peak * 1024
    return bytes_used / (1024 * 1024)


def _sqlite_reviews(
    assessments: list[Assessment], coverage: Coverage, iterations: int, now: datetime
) -> list[float]:
    """Exercise the persistence work surrounding one review against disposable SQLite."""
    with tempfile.TemporaryDirectory(prefix="watchlist-load-") as directory:
        path = Path(directory) / "load.db"
        intelligence = SqliteAssessmentStore(path)
        users = SqliteUserStore(path)
        for assessment in assessments:
            intelligence.save(assessment)
        user = users.create_user("load@example.test", "load-test-password")
        if user is None:
            raise RuntimeError("load user could not be created")
        for company in range(TARGET_WATCHLIST):
            users.add_membership(user.user_id, f"LOAD{company:02d}")

        def open_review() -> None:
            previous = users.checkpoint(user.user_id)
            users.issue_review(user.user_id, previous, now)
            assemble(
                user_id=user.user_id,
                memberships=users.memberships(user.user_id),
                previous_checkpoint=previous,
                review_cutoff=now,
                assessments=intelligence.recent(TARGET_EVIDENCE_PER_CYCLE),
                coverage=coverage,
            )

        return [_timed(open_review) for _ in range(iterations)]


def _coverage(now: datetime) -> Coverage:
    return Coverage(
        records=tuple(
            CoverageRecord(source=source, status=CoverageStatus.OK, observed_at=now)
            for source in ("market", "news", "nse-disclosures")
        )
    )


def _assessment(symbol: str, number: int, now: datetime, coverage: Coverage) -> Assessment:
    occurred = now - timedelta(minutes=number)
    item = Evidence(
        source="news",
        source_ref=f"{symbol}-{number}",
        tier=SourceTier.CREDIBLE_REPORTING,
        publisher="Load fixture",
        subject_company=symbol,
        retrieved_at=occurred,
        published_at=occurred,
        title=f"{symbol} signs agreement {number}",
        body="",
        url="fixture://load",
        security_symbol=symbol,
        category="News",
    )
    return Assessment(
        event=Event(
            event_id=item.source_ref,
            security_symbol=symbol,
            company_name=symbol,
            event_type="Agreements",
            description=item.title,
            occurred_at=occurred,
            evidence=(item,),
        ),
        attention=Attention.MEDIUM,
        confidence=Confidence.MEDIUM,
        reasons=(),
        coverage=coverage,
        scoring_version="load-fixture",
        assessed_at=occurred,
    )


def _news_item(number: int, now: datetime) -> Evidence:
    return Evidence(
        source="news",
        source_ref=f"load-news-{number}",
        tier=SourceTier.CREDIBLE_REPORTING,
        publisher="Load fixture",
        subject_company="Reliance Industries",
        retrieved_at=now,
        published_at=now,
        title=f"Reliance signs supply agreement number {number}",
        body="",
        url="fixture://load-news",
        security_symbol="RELIANCE",
        category="News",
    )


def _bars(count: int) -> list[Bar]:
    start = date(2025, 1, 1)
    return [
        Bar(
            on=start + timedelta(days=index),
            close=100 + index / 10,
            adjusted_close=100 + index / 10,
            volume=1_000_000,
        )
        for index in range(count)
    ]
