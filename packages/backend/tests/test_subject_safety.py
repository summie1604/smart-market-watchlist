"""Deterministic subject grounding for the rule fallback.

The live failure this exists for: "Goodluck India alters MoA and appoints new Group CFO"
arrived from the RELIANCE feed and was surfaced as a RELIANCE event, because the fallback
copied the retrieval context into the subject. **Retrieval context is a hint, not proof**
(D21). Feed scope says where we looked, never who an article is about.

False attribution is worse than a missed article, so every rule here fails closed.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from smart_watchlist.adapters.rule_extractor import RuleExtractor
from smart_watchlist.core.models import Evidence, SourceTier


def from_feed(
    headline: str, symbol: str = "RELIANCE", company: str = "Reliance Industries", body: str = ""
) -> Evidence:
    """An article as the news adapter produces it: subject_company is the feed we queried."""
    return Evidence(
        source="news",
        source_ref=headline[:40],
        tier=SourceTier.CREDIBLE_REPORTING,
        publisher="Some Publisher",
        subject_company=company,
        retrieved_at=datetime.now(UTC),
        published_at=datetime.now(UTC),
        title=headline,
        body=body,
        url="https://example.invalid",
        security_symbol=symbol,
        category="News",
    )


EXTRACTOR = RuleExtractor()


# --- the live failure ---------------------------------------------------------


def test_the_goodluck_regression_is_rejected() -> None:
    """The exact article that was misattributed in production."""
    evidence = from_feed("Goodluck India alters MoA and appoints new Group CFO")

    assert EXTRACTOR.extract(evidence) is None
    assert EXTRACTOR.last_rejection == "subject-not-named-in-headline"


# --- clear, company-specific headlines must still work ------------------------


@pytest.mark.parametrize(
    ("headline", "symbol", "company"),
    [
        ("Reliance Industries appoints new CFO", "RELIANCE", "Reliance Industries"),
        ("RIL signs agreement with a technology partner", "RELIANCE", "Reliance Industries"),
        ("HDFC Bank reports quarterly profit", "HDFCBANK", "HDFC Bank"),
        ("Infosys wins a large contract", "INFY", "Infosys"),
        ("Tata Motors launches an expansion in Karnataka", "TMCV", "Tata Motors"),
        ("Hindalco announces a capacity expansion", "HINDALCO", "Hindalco Industries Limited"),
        ("TCS signs an agreement with a European bank", "TCS", "Tata Consultancy Services"),
    ],
)
def test_clear_company_specific_headlines_still_pass(headline, symbol, company) -> None:
    """Not a RELIANCE-specific patch — the rule must hold across the curated universe."""
    result = EXTRACTOR.extract(from_feed(headline, symbol, company))

    assert result is not None, f"{headline!r} should still be extractable"
    assert result.concerns_subject


# --- multi-company, incidental and roundup cases ------------------------------


@pytest.mark.parametrize(
    ("headline", "why"),
    [
        ("Goodluck India alters MoA and appoints new Group CFO", "another company's event"),
        (
            "Konstelec Engineers receives amended Rs 9.19 crore order from Reliance Industries",
            "target named as counterparty, not subject",
        ),
        (
            "Kwality Wall's, Vadilal Industries: Why ice cream stocks fell after Reliance entry",
            "list headline; target appears after the colon",
        ),
        (
            "Sensex jumps 660 pts, Nifty nears 24,000; Reliance up",
            "market roundup; target is a trailing mention",
        ),
        (
            "Stocks to watch: Reliance Industries, Wipro, Tata Motors in focus",
            "a list of companies",
        ),
        ("Reliance-backed startup raises a funding round", "incidental qualifier"),
        ("A supplier to Reliance Industries halts production", "target is the counterparty"),
        ("Adani Group announces a port expansion", "no mention of the target at all"),
    ],
)
def test_ambiguous_and_incidental_headlines_are_rejected(headline, why) -> None:
    assert EXTRACTOR.extract(from_feed(headline)) is None, why
    assert EXTRACTOR.last_rejection, "the refusal must record why"


def test_a_body_only_mention_is_not_enough_for_the_fallback() -> None:
    """Gemini can read a body. Bounded rules cannot, so the fallback fails closed."""
    evidence = from_feed(
        "Ice cream market heats up as new entrants arrive",
        body="Reliance Industries launched Bombay Creamery this week.",
    )

    assert EXTRACTOR.extract(evidence) is None
    assert EXTRACTOR.last_rejection == "subject-not-named-in-headline"


def test_a_company_name_inside_another_phrase_does_not_count() -> None:
    """Token-boundary matching: "Relianceable Ltd" is not Reliance."""
    assert EXTRACTOR.extract(from_feed("Relianceable Systems reports higher revenue")) is None


def test_the_ticker_and_curated_aliases_are_accepted() -> None:
    for headline in (
        "RELIANCE signs a new supply agreement",
        "RIL announces an acquisition",
        "Reliance Industries announces an acquisition",
    ):
        assert EXTRACTOR.extract(from_feed(headline)) is not None, headline


def test_feed_scope_alone_never_establishes_the_subject() -> None:
    """The property under test, stated directly."""
    evidence = from_feed("An unrelated company announces a merger")

    assert evidence.subject_company == "Reliance Industries", "the hint is present"
    assert EXTRACTOR.extract(evidence) is None, "and it is not sufficient"


# --- evidence preservation and correction --------------------------------------


def test_a_refused_article_keeps_its_evidence_and_its_reason(tmp_path) -> None:
    """Refusing to make a claim is an outcome, not a gap. It has to be auditable."""
    from smart_watchlist.adapters.sqlite_store import SqliteAssessmentStore
    from smart_watchlist.core.models import CoverageRecord, CoverageStatus
    from smart_watchlist.core.pipeline import run_news_pipeline

    class DeadModel:
        name = "google/stub/quota-exhausted"

        def extract(self, evidence):
            return None

    class Feed:
        name = "news"

        def fetch(self, companies):
            return [from_feed("Goodluck India alters MoA and appoints new Group CFO")], (
                CoverageRecord(
                    source="news",
                    status=CoverageStatus.OK,
                    observed_at=datetime.now(UTC),
                    detail="one article",
                )
            )

    store = SqliteAssessmentStore(tmp_path / "r.db")

    run, assessed = run_news_pipeline(Feed(), DeadModel(), store, fallback=RuleExtractor())

    assert assessed == [], "no RELIANCE event was produced"
    assert store.recent(50) == [], "and none was persisted"
    assert run.is_healthy, "acquisition succeeded; only interpretation declined"

    rejections = store.rejections(symbol="RELIANCE")
    assert len(rejections) == 1
    assert rejections[0]["reason"] == "subject-not-named-in-headline"
    assert rejections[0]["extractor"].startswith("rules/"), "the refusal is the fallback's"
    assert "Goodluck" in str(rejections[0]["title"]), "the evidence itself is preserved"


def test_correction_withdraws_an_unsupported_attribution_but_keeps_the_evidence(
    tmp_path,
) -> None:
    """The narrowest safe repair: remove the claim, keep the article."""
    from smart_watchlist.adapters.sqlite_store import SqliteAssessmentStore
    from smart_watchlist.core.correction import correct_unsupported_attribution
    from smart_watchlist.core.engine import assess
    from smart_watchlist.core.models import (
        Coverage,
        CoverageRecord,
        CoverageStatus,
        Event,
    )

    store = SqliteAssessmentStore(tmp_path / "c.db")
    now = datetime.now(UTC)
    coverage = Coverage(
        records=(
            CoverageRecord(source="news", status=CoverageStatus.OK, observed_at=now, detail=""),
        )
    )

    def store_event(event_id: str, headline: str) -> None:
        evidence = from_feed(headline)
        store.save(
            assess(
                Event(
                    event_id=event_id,
                    security_symbol="RELIANCE",
                    company_name="Reliance Industries",
                    event_type="Agreements",
                    description=headline,
                    occurred_at=now,
                    evidence=(evidence,),
                ),
                coverage,
            )
        )

    store_event("bad", "Goodluck India alters MoA and appoints new Group CFO")
    store_event("good", "Reliance Industries signs a supply agreement")
    assert len(store.recent(50)) == 2

    report = correct_unsupported_attribution(store)

    assert report.removed_count == 1
    assert report.removed[0][0] == "bad"
    remaining = {a.event.event_id for a in store.recent(50)}
    assert remaining == {"good"}, "only the unsupported claim was withdrawn"
    assert any("Goodluck" in str(r["title"]) for r in store.rejections()), "evidence preserved"


def test_correction_leaves_market_and_disclosure_assessments_alone(tmp_path) -> None:
    """Only headline-attributed news is re-judged by a headline rule."""
    from smart_watchlist.adapters.sqlite_store import SqliteAssessmentStore
    from smart_watchlist.core.correction import correct_unsupported_attribution
    from smart_watchlist.core.engine import assess
    from smart_watchlist.core.models import Coverage, Event

    store = SqliteAssessmentStore(tmp_path / "m.db")
    now = datetime.now(UTC)
    computed = Evidence(
        source="market",
        source_ref="market:RELIANCE:2026-09-05",
        tier=SourceTier.COMPUTED,
        publisher="computed",
        subject_company="Reliance Industries",
        retrieved_at=now,
        published_at=now,
        title="RELIANCE moved +4.8%",
        body="",
        url="",
        security_symbol="RELIANCE",
        category="Unusual price movement",
    )
    store.save(
        assess(
            Event(
                event_id="computed-1",
                security_symbol="RELIANCE",
                company_name="Reliance Industries",
                event_type="Unusual price movement",
                description="RELIANCE moved +4.8%",
                occurred_at=now,
                evidence=(computed,),
            ),
            Coverage(records=()),
        )
    )

    report = correct_unsupported_attribution(store)

    assert report.checked == 0
    assert len(store.recent(50)) == 1
