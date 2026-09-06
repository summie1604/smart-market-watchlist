"""The attention evaluation harness.

Tests prove an implementation matches its specification. They do not prove the ranking is
useful — that needs labels, and the set ships empty on purpose. What is pinned here is
that the harness computes the right arithmetic and refuses to flatter an empty set.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from support import coverage, make_evidence

from smart_watchlist.core.models import Assessment, Attention, Confidence, Event, ReasonCode
from smart_watchlist.evaluation.attention import (
    LabelledCase,
    evaluate_attention,
    render_report,
)
from smart_watchlist.evaluation.labelled import LABELLED


def assessed(event_id: str, level: Attention, code: str) -> Assessment:
    return Assessment(
        event=Event(
            event_id=event_id,
            security_symbol="RELIANCE",
            company_name="Reliance",
            event_type="News",
            description=event_id,
            occurred_at=datetime.now(UTC),
            evidence=(make_evidence(ref=event_id),),
        ),
        attention=level,
        confidence=Confidence.MEDIUM,
        reasons=(ReasonCode(code=code, contribution=1, detail=""),),
        coverage=coverage(),
        scoring_version="test",
        assessed_at=datetime.now(UTC),
    )


def test_the_shipped_set_is_empty_on_purpose() -> None:
    """Inventing labels produces a number that looks like evidence and is not."""
    assert LABELLED == ()


def test_an_empty_set_is_reported_honestly():
    report = evaluate_attention([], [])

    assert report.cases == 0
    assert report.precision is None, "nothing demanded is not perfect precision"
    assert report.recall is None
    assert "No labelled cases" in render_report(report, "test")


def test_the_harness_measures_the_demanding_levels() -> None:
    """One of each outcome, so the arithmetic is pinned before real labels arrive."""
    labelled = [
        LabelledCase("hit", "RELIANCE", "", Attention.HIGH),
        LabelledCase("noise", "RELIANCE", "", Attention.NONE),
        LabelledCase("missed", "RELIANCE", "", Attention.HIGH),
        LabelledCase("never-assessed", "RELIANCE", "", Attention.HIGH),
    ]
    produced = [
        assessed("hit", Attention.HIGH, "GOOD"),
        assessed("noise", Attention.MEDIUM, "OVEREAGER"),
        assessed("missed", Attention.LOW, "TOO_QUIET"),
    ]

    report = evaluate_attention(labelled, produced)

    assert report.cases == 3, "an unassessed case is an ingestion gap, not a ranking failure"
    assert (report.true_positives, report.false_positives, report.false_negatives) == (1, 1, 1)
    assert report.precision == 0.5
    assert report.recall == 0.5
    assert report.agreement == pytest.approx(1 / 3)


def test_failures_carry_the_reason_codes_that_caused_them() -> None:
    """A failure is only actionable if you can see which contribution carried it."""
    report = evaluate_attention(
        [
            LabelledCase("noise", "RELIANCE", "", Attention.NONE),
            LabelledCase("missed", "RELIANCE", "", Attention.HIGH),
        ],
        [
            assessed("noise", Attention.HIGH, "OVEREAGER"),
            assessed("missed", Attention.NONE, "TOO_QUIET"),
        ],
    )

    assert "OVEREAGER" in report.false_positive_codes
    assert "TOO_QUIET" in report.false_negative_codes
    assert {d.case.event_id for d in report.disagreements} == {"noise", "missed"}


def test_a_populated_report_states_it_is_fixture_performance() -> None:
    report = evaluate_attention(
        [LabelledCase("hit", "RELIANCE", "", Attention.HIGH)],
        [assessed("hit", Attention.HIGH, "GOOD")],
    )

    rendered = render_report(report, "2026-09-06.a")
    assert "not a claim about live ranking" in rendered
    assert "100.0%" in rendered
