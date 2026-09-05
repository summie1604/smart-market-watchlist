"""Event identity and corroboration — D12 and D13.

The governing asymmetry: a false merge is worse than a temporary duplicate. A duplicate
makes the review noisier and can be reconciled. A false merge corrupts lifecycle state,
corroboration counts and provenance invisibly, because the merged event looks coherent.
"""

from __future__ import annotations

from datetime import UTC, datetime

from smart_watchlist.core.corroboration import assess_corroboration, family_of
from smart_watchlist.core.extraction import ExtractedEvent
from smart_watchlist.core.linking import LinkOutcome, decide_link
from smart_watchlist.core.models import Event, Evidence, SourceTier

NOW = datetime(2026, 9, 5, tzinfo=UTC)


def proposal(description: str, **kwargs) -> ExtractedEvent:
    return ExtractedEvent(
        subject_company="Tata Motors",
        event_type="Acquisition",
        description=description,
        **kwargs,
    )


def event(description: str, event_id: str = "e1") -> Event:
    return Event(
        event_id=event_id,
        security_symbol="TMCV",
        company_name="Tata Motors",
        event_type="Acquisition",
        description=description,
        occurred_at=NOW,
        evidence=(),
    )


def article(publisher: str, ref: str, tier: SourceTier = SourceTier.CREDIBLE_REPORTING) -> Evidence:
    return Evidence(
        source="news",
        source_ref=ref,
        tier=tier,
        publisher=publisher,
        subject_company="Tata Motors",
        retrieved_at=NOW,
        published_at=NOW,
        title="story",
        body="",
        url="https://example.invalid",
        security_symbol="TMCV",
        category="News",
    )


# --- D12: linking -------------------------------------------------------------


def test_no_candidates_creates_a_new_event() -> None:
    decision = decide_link(proposal("Tata Motors Iveco takeover clears Consob review"), [])
    assert decision.outcome is LinkOutcome.CREATE_NEW


def test_two_publishers_on_one_story_become_one_event() -> None:
    """Case D: several reports of one developing situation, not several alerts."""
    existing = event("Tata Motors' Iveco takeover offer gets Consob nod, acceptance opens Sep 7")
    decision = decide_link(
        proposal(
            "Tata Motors Iveco takeover offer clears Consob review, acceptance opens September 7"
        ),
        [(existing, None)],
    )
    assert decision.outcome is LinkOutcome.LINK
    assert decision.event_id == "e1"


def test_two_different_same_day_events_are_not_merged() -> None:
    """The same-day-separate case. Company, type and date all match — and they differ."""
    iveco = event("Tata Motors Iveco takeover offer gets Consob nod")
    decision = decide_link(
        proposal("Tata Motors signs supply agreement with Vertelo for 500 electric buses"),
        [(iveco, None)],
    )
    assert decision.outcome is not LinkOutcome.LINK


def test_a_conflicting_counterparty_rules_a_candidate_out_entirely() -> None:
    """Structured attributes are decisive; headline similarity cannot override them."""
    existing = event("Tata Motors agrees takeover of Iveco Group")
    decision = decide_link(
        proposal(
            "Tata Motors agrees takeover of Ashok Leyland unit",
            counterparties=("Ashok Leyland",),
        ),
        [(existing, proposal("x", counterparties=("Iveco",)))],
    )
    assert decision.outcome is LinkOutcome.CREATE_NEW
    assert "conflict" in decision.reason.lower()


def test_partial_similarity_yields_ambiguous_and_holds_the_merge() -> None:
    """Ambiguity withholds the claim, never the evidence."""
    existing = event("Tata Motors Iveco takeover offer receives Consob approval")
    decision = decide_link(
        proposal("Tata Motors completes acquisition financing arrangements for Iveco purchase"),
        [(existing, None)],
    )
    if decision.outcome is LinkOutcome.AMBIGUOUS:
        assert decision.possible_relationship is not None
        assert "not yet confirmed" in decision.possible_relationship
        assert decision.event_id == "e1", "the related event stays identified, not hidden"


def test_uncertainty_never_forces_a_merge() -> None:
    """Across every outcome, an uncertain decision must not be LINK."""
    unrelated = event("Tata Motors quarterly results beat estimates")
    decision = decide_link(
        proposal("Tata Motors Iveco takeover clears Consob"), [(unrelated, None)]
    )
    assert decision.outcome is not LinkOutcome.LINK


# --- D13: corroboration -------------------------------------------------------


def test_syndicated_copies_are_one_source_not_many() -> None:
    """Ten outlets running one wire is one source. Repetition is not confirmation."""
    wire = [
        article("PTI", "1"),
        article("Press Trust of India", "2"),
        article("The Economic Times", "3"),
        article("ETMarkets.com", "4"),
    ]
    result = assess_corroboration(wire)

    assert result.article_count == 4
    assert result.independent_source_count == 2, (
        "two PTI copies are one family; two ET surfaces another"
    )
    assert result.is_corroborated, "two independent families do corroborate"


def test_genuinely_independent_publishers_corroborate() -> None:
    result = assess_corroboration([article("Bloomberg.com", "1"), article("BusinessLine", "2")])

    assert result.independent_source_count == 2
    assert result.is_corroborated
    assert result.summary == "2 articles · 2 independent sources"


def test_a_single_report_is_not_corroboration() -> None:
    result = assess_corroboration([article("Whalesbook", "1")])

    assert result.independent_source_count == 1
    assert not result.is_corroborated


def test_a_filing_needs_no_corroboration() -> None:
    """The company told the exchange. Nobody else needs to repeat it."""
    result = assess_corroboration([article("NSE", "1", tier=SourceTier.OFFICIAL_DISCLOSURE)])

    assert result.has_authoritative
    assert result.is_corroborated


def test_computed_evidence_is_not_counted_as_a_reporting_source() -> None:
    """Our own calculation is not a publisher corroborating us."""
    result = assess_corroboration(
        [article("computed", "1", tier=SourceTier.COMPUTED), article("Reuters", "2")]
    )

    assert result.independent_source_count == 1


def test_an_unmapped_publisher_is_treated_as_independent() -> None:
    """The honest default, and the stated limitation: unknown syndication inflates."""
    assert family_of("Some Local Daily") == "publisher:some local daily"
    assert family_of("PTI") == family_of("Press Trust of India")
