"""Failure paths for the news pipeline.

Step 0 established why these are not optional: the blocking defect there was invisible
on the happy path. Every case below asks the same question — when something breaks, does
the system say so, or does it quietly look healthy?
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from smart_watchlist.adapters.claude_extractor import ClaudeExtractor
from smart_watchlist.adapters.google_news import GoogleNewsSource
from smart_watchlist.adapters.rule_extractor import RuleExtractor
from smart_watchlist.adapters.sqlite_store import SqliteAssessmentStore
from smart_watchlist.core.models import CoverageRecord, CoverageStatus, Evidence, SourceTier
from smart_watchlist.core.pipeline import run_news_pipeline

NOW = datetime(2026, 9, 5, tzinfo=UTC)

FEED = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Tata Motors signs supply agreement with Vertelo - The Economic Times</title>
<link>https://example.invalid/a</link><guid>guid-a</guid>
<pubDate>Fri, 04 Sep 2026 10:00:00 GMT</pubDate>
<source url="https://economictimes.com">The Economic Times</source></item>
</channel></rss>"""


def feed_source(body: str = FEED, status: int = 200) -> GoogleNewsSource:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=body, headers={"content-type": "application/xml"})

    return GoogleNewsSource(transport=httpx.MockTransport(handler))


class DeadExtractor:
    """Stands in for a model that is down, rate limited, or returning nonsense."""

    name = "dead"

    def extract(self, evidence: Evidence):
        return None


class ExplodingSource:
    name = "news"

    def fetch(self, companies):
        return [], CoverageRecord(
            source="news",
            status=CoverageStatus.UNAVAILABLE,
            observed_at=datetime.now(UTC),
            detail="Fetch failed: ConnectError",
        )


# --- provider failures ---------------------------------------------------------


def test_a_news_outage_persists_coverage_even_with_zero_articles(tmp_path) -> None:
    """D20 applies to news exactly as it applies to disclosures."""
    store = SqliteAssessmentStore(tmp_path / "n.db")

    run, assessed = run_news_pipeline(ExplodingSource(), RuleExtractor(), store)

    assert assessed == []
    assert not run.is_healthy
    persisted = store.latest_run("news")
    assert persisted is not None and not persisted.is_healthy


def test_yesterdays_news_success_does_not_imply_todays_health(tmp_path) -> None:
    """The Step 0 defect, re-checked on the news path."""
    store = SqliteAssessmentStore(tmp_path / "n.db")

    run_news_pipeline(feed_source(), RuleExtractor(), store)
    assert store.latest_run("news").is_healthy  # type: ignore[union-attr]

    run_news_pipeline(ExplodingSource(), RuleExtractor(), store)

    latest = store.latest_run("news")
    assert latest is not None and not latest.is_healthy


def test_an_http_error_is_coverage_not_an_exception(tmp_path) -> None:
    store = SqliteAssessmentStore(tmp_path / "n.db")

    run, assessed = run_news_pipeline(feed_source(status=503), RuleExtractor(), store)

    assert assessed == []
    assert not run.is_healthy


def test_an_empty_feed_is_healthy_but_produces_nothing(tmp_path) -> None:
    """A quiet news day is a conclusion; an outage is an admission. Not the same."""
    empty = '<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>'
    store = SqliteAssessmentStore(tmp_path / "n.db")

    run, assessed = run_news_pipeline(feed_source(empty), RuleExtractor(), store)

    assert assessed == []
    assert run.is_healthy


def test_malformed_xml_does_not_raise(tmp_path) -> None:
    store = SqliteAssessmentStore(tmp_path / "n.db")

    run, assessed = run_news_pipeline(feed_source("<rss><channel><item>"), RuleExtractor(), store)

    assert assessed == []
    assert run is not None


def test_a_malformed_item_is_skipped_and_counted() -> None:
    """One unusable item must not discard the rest of the feed."""
    body = FEED.replace("<guid>guid-a</guid>", "") + ""
    _evidence, coverage = feed_source(body).fetch([("TMCV", "Tata Motors")])

    assert coverage.status is CoverageStatus.OK
    assert "skipped" in coverage.detail


def test_fetching_the_same_article_twice_yields_one_event(tmp_path) -> None:
    store = SqliteAssessmentStore(tmp_path / "n.db")

    run_news_pipeline(feed_source(), RuleExtractor(), store)
    first = len(store.recent(100))
    run_news_pipeline(feed_source(), RuleExtractor(), store)

    assert len(store.recent(100)) == first, "a re-fetched article must not duplicate the event"


# --- extractor failures --------------------------------------------------------


def test_an_llm_outage_falls_back_rather_than_stopping(tmp_path) -> None:
    """D5: news keeps reaching the domain, with a plainly weaker reading of it."""
    store = SqliteAssessmentStore(tmp_path / "n.db")

    _run, assessed = run_news_pipeline(
        feed_source(), DeadExtractor(), store, fallback=RuleExtractor()
    )

    assert assessed, "the rule extractor should still produce an event"


def test_an_llm_outage_with_no_fallback_produces_no_fabricated_event(tmp_path) -> None:
    store = SqliteAssessmentStore(tmp_path / "n.db")

    run, assessed = run_news_pipeline(feed_source(), DeadExtractor(), store, fallback=None)

    assert assessed == []
    assert run.is_healthy, "news itself was fine; it is the reading of it that failed"


def test_malformed_model_output_yields_nothing_rather_than_garbage() -> None:
    """Any deviation from the expected shape resolves to None, never a partial guess."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"content": [{"type": "text", "text": "not json at all"}]})

    extractor = ClaudeExtractor(api_key="test", transport=httpx.MockTransport(handler))
    evidence = Evidence(
        source="news",
        source_ref="r",
        tier=SourceTier.CREDIBLE_REPORTING,
        publisher="Reuters",
        subject_company="Tata Motors",
        retrieved_at=NOW,
        published_at=NOW,
        title="t",
        body="",
        url="u",
        security_symbol="TMCV",
        category="News",
    )

    assert extractor.extract(evidence) is None


def test_an_unconfigured_model_is_not_an_error() -> None:
    """Absence of a credential is a coverage fact, not a crash."""
    extractor = ClaudeExtractor(api_key="")

    assert not extractor.is_configured
    assert (
        extractor.extract(
            Evidence(
                source="news",
                source_ref="r",
                tier=SourceTier.CREDIBLE_REPORTING,
                publisher="Reuters",
                subject_company="Tata Motors",
                retrieved_at=NOW,
                published_at=NOW,
                title="t",
                body="",
                url="u",
                security_symbol="TMCV",
                category="News",
            )
        )
        is None
    )


def test_market_evidence_survives_a_news_failure(tmp_path) -> None:
    """One source family failing must not take the others down with it."""
    store = SqliteAssessmentStore(tmp_path / "n.db")

    run, _ = run_news_pipeline(ExplodingSource(), RuleExtractor(), store)

    sources = {r.source: r.status for r in run.coverage.records}
    assert sources["news"] is CoverageStatus.UNAVAILABLE
    assert "market" in sources, "market coverage is still reported, not omitted"


def test_linking_reaches_an_event_older_than_the_recent_window(tmp_path) -> None:
    """Merging must not lose the evidence an event already holds.

    The regression: the link target was looked up by scanning a recent window, so an
    older event was not found and its id was reused for a fresh single-evidence event —
    silently destroying accumulated provenance and the corroboration count built on it.
    """
    from datetime import timedelta

    from smart_watchlist.core.corroboration import assess_corroboration
    from smart_watchlist.core.engine import assess
    from smart_watchlist.core.models import Coverage, Event
    from smart_watchlist.core.pipeline import _merge_into

    store = SqliteAssessmentStore(tmp_path / "m.db")
    coverage = Coverage(
        records=(
            CoverageRecord(source="news", status=CoverageStatus.OK, observed_at=NOW, detail=""),
        )
    )

    def article_at(ref: str, publisher: str, when: datetime) -> Evidence:
        return Evidence(
            source="news",
            source_ref=ref,
            tier=SourceTier.CREDIBLE_REPORTING,
            publisher=publisher,
            subject_company="Tata Motors",
            retrieved_at=NOW,
            published_at=when,
            title="Iveco deal",
            body="",
            url="u",
            security_symbol="TMCV",
            category="News",
        )

    old = NOW - timedelta(days=40)
    target = Event(
        event_id="target",
        security_symbol="TMCV",
        company_name="Tata Motors",
        event_type="Acquisition",
        description="Iveco deal",
        occurred_at=old,
        evidence=(article_at("a", "Reuters", old), article_at("b", "Bloomberg", old)),
    )
    store.save(assess(target, coverage, corroboration=assess_corroboration(target.evidence)))

    # Bury it well outside any recent window.
    for i in range(250):
        filler_evidence = article_at(f"n{i}", "Filler", NOW - timedelta(minutes=i))
        store.save(
            assess(
                Event(
                    event_id=f"f{i}",
                    security_symbol="X",
                    company_name="X",
                    event_type="News",
                    description="x",
                    occurred_at=NOW - timedelta(minutes=i),
                    evidence=(filler_evidence,),
                ),
                coverage,
            )
        )

    from smart_watchlist.core.extraction import ExtractedEvent

    merged = _merge_into(
        store,
        "target",
        article_at("c", "Livemint", NOW),
        ExtractedEvent(
            subject_company="Tata Motors", event_type="Acquisition", description="Iveco deal"
        ),
    )

    assert len(merged.evidence) == 3, "the two earlier reports must survive the merge"
    assert {e.publisher for e in merged.evidence} == {"Reuters", "Bloomberg", "Livemint"}


def test_fallback_output_is_never_labelled_as_model_output(tmp_path) -> None:
    """D25: fallback output must never be represented as Gemini output.

    Provenance is what lets a stored assessment be evaluated against the extractor that
    actually produced it. Mislabelling would make the model look better than it is.
    """
    import json
    import sqlite3

    from smart_watchlist.adapters.rule_extractor import EXTRACTOR_NAME as RULE_NAME

    path = tmp_path / "p.db"
    store = SqliteAssessmentStore(path)

    run_news_pipeline(feed_source(), DeadExtractor(), store, fallback=RuleExtractor())

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        "SELECT extraction FROM assessments WHERE extraction IS NOT NULL"
    ).fetchall()
    connection.close()

    assert rows, "the fallback should have produced a persisted extraction"
    for row in rows:
        extractor = json.loads(row["extraction"])["extractor"]
        assert extractor == RULE_NAME
        assert "google/" not in extractor
        assert "gemini" not in extractor.lower()
