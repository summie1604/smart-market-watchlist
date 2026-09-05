"""Cases B and C — news combining with market and disclosure evidence.

This is where the product is supposed to become more than the sum of its feeds: two
weak signals pointing the same way are worth more than either alone, and an
authoritative filing outranks reporting about it without duplicating the event.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from smart_watchlist.core.corroboration import assess_corroboration
from smart_watchlist.core.engine import assess
from smart_watchlist.core.extraction import ExtractedEvent, Extraction
from smart_watchlist.core.market import Bar, observe
from smart_watchlist.core.models import (
    Attention,
    Confidence,
    Coverage,
    CoverageRecord,
    CoverageStatus,
    Event,
    Evidence,
    SourceTier,
)

NOW = datetime(2026, 9, 5, tzinfo=UTC)
START = NOW.date() - timedelta(days=60)


def healthy_coverage() -> Coverage:
    return Coverage(
        records=tuple(
            CoverageRecord(source=s, status=CoverageStatus.OK, observed_at=NOW, detail="")
            for s in ("news", "market", "nse-disclosures")
        )
    )


def article(publisher: str, ref: str, tier: SourceTier = SourceTier.CREDIBLE_REPORTING) -> Evidence:
    return Evidence(
        source="nse-disclosures" if tier is SourceTier.OFFICIAL_DISCLOSURE else "news",
        source_ref=ref,
        tier=tier,
        publisher=publisher,
        subject_company="Tata Motors",
        retrieved_at=NOW,
        published_at=NOW,
        title="Tata Motors agrees Iveco acquisition",
        body="",
        url="https://example.invalid",
        security_symbol="TMCV",
        category="News",
    )


def event_with(*evidence: Evidence) -> Event:
    return Event(
        event_id="e1",
        security_symbol="TMCV",
        company_name="Tata Motors",
        event_type="Acquisition",
        description="Tata Motors agrees Iveco acquisition",
        occurred_at=NOW,
        evidence=evidence,
    )


def extraction(**kwargs) -> Extraction:
    return Extraction(
        event=ExtractedEvent(
            subject_company="Tata Motors",
            event_type="Acquisition",
            description="Tata Motors agrees Iveco acquisition",
            **kwargs,
        ),
        evidence_ref="r",
        extractor="test",
    )


def unusual_move() -> object:
    bars = [
        Bar(
            on=START + timedelta(days=i),
            close=100 + (0.2 if i % 2 else -0.2),
            adjusted_close=100 + (0.2 if i % 2 else -0.2),
            volume=1_000_000,
        )
        for i in range(40)
    ]
    bars.append(Bar(on=NOW.date(), close=105.0, adjusted_close=105.0, volume=3_000_000))
    return observe("TMCV", bars)


def test_case_b_event_plus_move_plus_corroboration_outranks_the_event_alone() -> None:
    """Independent signals pointing the same way are worth more than either alone."""
    evidence = (article("Bloomberg.com", "1"), article("BusinessLine", "2"))
    event = event_with(*evidence)

    alone = assess(
        event, healthy_coverage(), None, assess_corroboration(evidence[:1]), extraction()
    )
    combined = assess(
        event, healthy_coverage(), unusual_move(), assess_corroboration(evidence), extraction()
    )

    assert combined.score > alone.score
    assert combined.attention is Attention.HIGH
    codes = {r.code for r in combined.reasons}
    assert {
        "COMPANY_SPECIFIC_EVENT",
        "INDEPENDENT_CORROBORATION",
        "NEWS_COINCIDES_WITH_MOVE",
    } <= codes


def test_case_b_states_coincidence_and_never_causation() -> None:
    """VISION.md §13. The wording is the guarantee, so the wording is tested."""
    evidence = (article("Bloomberg.com", "1"), article("BusinessLine", "2"))
    combined = assess(
        event_with(*evidence),
        healthy_coverage(),
        unusual_move(),
        assess_corroboration(evidence),
        extraction(),
    )

    text = " ".join(r.detail for r in combined.reasons).lower()
    assert "same period" in text or "context" in text
    for causal in ("because", "caused by", "due to", "driven by"):
        assert causal not in text, f"{causal!r} asserts causation the evidence does not support"


def test_case_c_a_filing_outranks_reporting_about_it() -> None:
    """Authoritative provenance is stronger, and needs no corroboration to be certain."""
    filing = article("NSE", "f1", tier=SourceTier.OFFICIAL_DISCLOSURE)
    reports = (article("Livemint", "1"), article("Reuters", "2"))

    disclosed = assess(
        event_with(filing, *reports),
        healthy_coverage(),
        None,
        assess_corroboration((filing, *reports)),
        extraction(),
    )
    reported_only = assess(
        event_with(*reports), healthy_coverage(), None, assess_corroboration(reports), extraction()
    )

    assert disclosed.confidence is Confidence.HIGH
    assert reported_only.confidence is Confidence.MEDIUM
    assert {r.code for r in disclosed.reasons} >= {"AUTHORITATIVE_DISCLOSURE"}


def test_case_c_one_event_carries_all_three_kinds_of_evidence() -> None:
    """A filing plus news about it is one event, not two alerts."""
    filing = article("NSE", "f1", tier=SourceTier.OFFICIAL_DISCLOSURE)
    event = event_with(filing, article("Livemint", "1"), article("Reuters", "2"))

    result = assess(
        event, healthy_coverage(), None, assess_corroboration(event.evidence), extraction()
    )

    assert len(result.event.evidence) == 3
    corroboration = assess_corroboration(event.evidence)
    assert corroboration.article_count == 3
    assert corroboration.independent_source_count == 3


def test_a_rumour_can_be_significant_and_uncertain_at_once() -> None:
    """Attention and confidence are different axes and must not collapse."""
    reports = (article("Livemint", "1"), article("Reuters", "2"))
    speculative = assess(
        event_with(*reports),
        healthy_coverage(),
        unusual_move(),
        assess_corroboration(reports),
        extraction(is_speculative=True),
    )

    assert speculative.attention in (Attention.HIGH, Attention.MEDIUM)
    assert speculative.confidence is Confidence.MEDIUM
    assert any(r.code == "SPECULATIVE_REPORT" for r in speculative.reasons)


def test_syndicated_repetition_does_not_raise_the_score() -> None:
    """Ten copies of one wire must not outscore two independent reports."""
    wire = tuple(article(p, str(i)) for i, p in enumerate(["PTI", "Press Trust of India", "PTI"]))
    independent = (article("Bloomberg.com", "a"), article("BusinessLine", "b"))

    syndicated = assess(
        event_with(*wire), healthy_coverage(), None, assess_corroboration(wire), extraction()
    )
    genuine = assess(
        event_with(*independent),
        healthy_coverage(),
        None,
        assess_corroboration(independent),
        extraction(),
    )

    assert genuine.score > syndicated.score
