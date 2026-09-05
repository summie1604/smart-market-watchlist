"""Engine behaviour, and the seed of the calibration fixture set (DESIGN.md D4).

These run with no network, no model and no database — which is the point of keeping
the engine pure.
"""

from __future__ import annotations

from support import coverage, make_event, make_evidence

from smart_watchlist.core.engine import assess
from smart_watchlist.core.models import Attention, Confidence, SourceTier


def test_material_disclosure_under_full_coverage_earns_attention() -> None:
    assessment = assess(make_event(make_evidence()), coverage())

    assert assessment.attention in (Attention.HIGH, Attention.MEDIUM)
    codes = {r.code for r in assessment.reasons}
    assert "AUTHORITATIVE_DISCLOSURE" in codes
    assert "MATERIAL_EVENT_TYPE" in codes


def test_every_verdict_carries_the_reasons_that_produced_it() -> None:
    """An attention level that cannot explain itself must not exist."""
    assessment = assess(make_event(make_evidence()), coverage())

    assert assessment.reasons
    assert assessment.score == sum(r.contribution for r in assessment.reasons)
    assert assessment.scoring_version


def test_routine_disclosure_is_argued_down() -> None:
    evidence = make_evidence(category="Shareholders meeting")
    assessment = assess(make_event(evidence), coverage())

    negatives = [r for r in assessment.reasons if r.contribution < 0]
    assert any(r.code == "ROUTINE_EVENT_TYPE" for r in negatives)
    assert assessment.attention is not Attention.HIGH


def test_a_quiet_verdict_is_withheld_when_we_could_not_look() -> None:
    """ "Nothing meaningful changed" and "we could not look" are different statements."""
    evidence = make_evidence(category="Shareholders meeting")

    seeing = assess(make_event(evidence), coverage())
    blind = assess(make_event(evidence), coverage(market=False, news=False))

    assert seeing.attention is Attention.NONE
    assert blind.attention is Attention.UNABLE


def test_missing_coverage_is_scored_not_ignored() -> None:
    evidence = make_evidence()
    complete = assess(make_event(evidence), coverage())
    partial = assess(make_event(evidence), coverage(market=False, news=False))

    assert partial.score < complete.score
    codes = {r.code for r in partial.reasons}
    assert {"NO_MARKET_OBSERVATION", "NO_NEWS_CORROBORATION"} <= codes


def test_a_company_outside_the_curated_universe_says_so() -> None:
    assessment = assess(make_event(make_evidence(symbol="ABMINTLLTD")), coverage())

    assert any(r.code == "LIMITED_COMPANY_COVERAGE" for r in assessment.reasons)


def test_confidence_tracks_evidence_not_score() -> None:
    """A weak claim from a filing is still certain; a strong one from a forum is not."""
    disclosed = assess(make_event(make_evidence(category="Shareholders meeting")), coverage())
    chatter = assess(
        make_event(make_evidence(tier=SourceTier.SOCIAL_DISCUSSION)),
        coverage(),
    )

    # The filing scores lower yet is the more certain of the two — which is the whole
    # point of keeping the axes apart.
    assert disclosed.score < chatter.score
    assert disclosed.confidence is Confidence.HIGH
    assert chatter.confidence is Confidence.LOW
