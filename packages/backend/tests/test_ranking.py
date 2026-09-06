"""Canonical order: severity, then recency (D26).

The order a reader sees is a product decision, so it is pinned here rather than left to
whichever client renders it. Two properties matter and are tested separately: severity
always leads, and score never breaks a tie.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from support import NOW, coverage, make_evidence

from smart_watchlist.core.models import Assessment, Attention, Confidence, Event
from smart_watchlist.core.ranking import canonical_order


def assessment(
    *,
    event_id: str,
    attention: Attention,
    occurred_at: datetime,
    score: int = 0,
    symbol: str = "RELIANCE",
) -> Assessment:
    evidence = make_evidence(symbol=symbol, ref=event_id)
    return Assessment(
        event=Event(
            event_id=event_id,
            security_symbol=symbol,
            company_name=symbol,
            event_type="Contract Win",
            description=event_id,
            occurred_at=occurred_at,
            evidence=(evidence,),
        ),
        attention=attention,
        confidence=Confidence.MEDIUM,
        reasons=(),
        coverage=coverage(),
        scoring_version="test",
        assessed_at=NOW,
        score=score,
    )


def test_severity_leads_whatever_the_dates_say() -> None:
    """A week-old HIGH still outranks a MEDIUM from an hour ago."""
    old_high = assessment(
        event_id="old-high", attention=Attention.HIGH, occurred_at=NOW - timedelta(days=7)
    )
    fresh_medium = assessment(event_id="fresh-medium", attention=Attention.MEDIUM, occurred_at=NOW)

    ordered = canonical_order([fresh_medium, old_high])

    assert [a.event.event_id for a in ordered] == ["old-high", "fresh-medium"]


def test_within_a_level_the_newest_occurrence_leads() -> None:
    older = assessment(
        event_id="older", attention=Attention.HIGH, occurred_at=NOW - timedelta(days=2)
    )
    newer = assessment(event_id="newer", attention=Attention.HIGH, occurred_at=NOW)

    ordered = canonical_order([older, newer])

    assert [a.event.event_id for a in ordered] == ["newer", "older"]


def test_score_does_not_break_a_tie() -> None:
    """Ordering two same-level items by score would claim a precision we do not have.

    The higher-scoring item is deliberately the older one: if score still ranked, it
    would lead.
    """
    high_score_older = assessment(
        event_id="older",
        attention=Attention.HIGH,
        occurred_at=NOW - timedelta(days=1),
        score=99,
    )
    low_score_newer = assessment(
        event_id="newer", attention=Attention.HIGH, occurred_at=NOW, score=1
    )

    ordered = canonical_order([high_score_older, low_score_newer])

    assert [a.event.event_id for a in ordered] == ["newer", "older"]


def test_an_admission_never_outranks_a_finding() -> None:
    """UNABLE is a statement about our coverage, not a finding about the company."""
    unable = assessment(event_id="unable", attention=Attention.UNABLE, occurred_at=NOW)
    low = assessment(event_id="low", attention=Attention.LOW, occurred_at=NOW - timedelta(days=30))

    ordered = canonical_order([unable, low])

    assert [a.event.event_id for a in ordered] == ["low", "unable"]


def test_the_order_is_total_so_two_renderings_match() -> None:
    """Symbol breaks an exact tie: no phantom movement between identical requests."""
    same_moment = datetime(2026, 9, 1, 10, tzinfo=UTC)
    a = assessment(event_id="a", attention=Attention.HIGH, occurred_at=same_moment, symbol="TCS")
    b = assessment(event_id="b", attention=Attention.HIGH, occurred_at=same_moment, symbol="INFY")

    assert canonical_order([a, b]) == canonical_order([b, a])
