"""Source standing, and what news without a market reaction is worth (D36).

Two separate axes are under test and the tests keep them separate on purpose. Standing
says *what kind of source* said something. Attention says *how much it matters*. A story
from an unrecognised publisher is not automatically unimportant, and a story in a national
daily is not automatically important — conflating the two is the failure this splits apart.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from support import NOW, coverage, make_evidence

from smart_watchlist.core.engine import assess
from smart_watchlist.core.extraction import ExtractedEvent, Extraction
from smart_watchlist.core.market import MarketObservation
from smart_watchlist.core.models import Event, SourceTier
from smart_watchlist.core.standing import SourceStanding, standing_label, standing_of


def article(publisher: str, ref: str = "a1", tier: SourceTier = SourceTier.CREDIBLE_REPORTING):
    return replace(
        make_evidence(symbol="RELIANCE", category="News", ref=ref, tier=tier),
        source="news",
        publisher=publisher,
        title="Reliance signs a supply agreement",
        body="Reliance signs a supply agreement",
    )


# --- what a source is ------------------------------------------------------------


@pytest.mark.parametrize(
    ("publisher", "expected"),
    [
        ("The Economic Times", SourceStanding.ESTABLISHED),
        ("Reuters", SourceStanding.ESTABLISHED),
        ("moneycontrol.com", SourceStanding.ESTABLISHED),
        ("PR Newswire", SourceStanding.SYNDICATED_RELEASE),
        ("GlobeNewswire", SourceStanding.SYNDICATED_RELEASE),
        ("Whalesbook", SourceStanding.UNRECOGNISED),
        ("ascendants.in", SourceStanding.UNRECOGNISED),
        ("MarketBeat", SourceStanding.UNRECOGNISED),
    ],
)
def test_publishers_are_placed_by_a_curated_registry(publisher, expected) -> None:
    assert standing_of([article(publisher)]) is expected


def test_a_filing_is_official_whoever_relayed_it():
    """The tier decides before the registry does."""
    filing = make_evidence(symbol="RELIANCE", tier=SourceTier.OFFICIAL_DISCLOSURE)

    assert standing_of([filing]) is SourceStanding.OFFICIAL


def test_an_event_takes_the_strongest_thing_backing_it() -> None:
    """A filing plus an aggregator is still supported by a filing."""
    filing = make_evidence(symbol="RELIANCE", ref="f1", tier=SourceTier.OFFICIAL_DISCLOSURE)

    assert standing_of([article("Whalesbook"), filing]) is SourceStanding.OFFICIAL
    assert (
        standing_of([article("Whalesbook"), article("The Hindu", "a2")])
        is SourceStanding.ESTABLISHED
    )


def test_our_own_measurement_is_neither_official_nor_unrecognised() -> None:
    """A market observation has no publisher. Calling it a filing would claim authority."""
    computed = replace(
        make_evidence(symbol="RELIANCE", tier=SourceTier.COMPUTED),
        source="market",
        publisher="computed",
    )

    assert standing_of([computed]) is SourceStanding.COMPUTED


def test_labels_describe_rather_than_rate() -> None:
    """ "Unrecognised" is an absence in our list, and the wording has to say that."""
    assert standing_label(SourceStanding.UNRECOGNISED) == "unrecognised publisher"
    assert standing_label(SourceStanding.OFFICIAL) == "exchange filing"
    assert "verified" not in " ".join(standing_label(s) for s in SourceStanding).lower()


# --- what it does to attention ----------------------------------------------------


def extraction() -> Extraction:
    return Extraction(
        event=ExtractedEvent(
            subject_company="Reliance Industries",
            event_type="Agreements",
            description="Reliance signs a supply agreement",
        ),
        evidence_ref="a1",
        extractor="test",
    )


def news_event(*evidence) -> Event:
    return Event(
        event_id="e1",
        security_symbol="RELIANCE",
        company_name="Reliance Industries",
        event_type="Agreements",
        description="Reliance signs a supply agreement",
        occurred_at=NOW,
        evidence=tuple(evidence),
    )


def observation(*, unusual: bool) -> MarketObservation:
    """A real observation. ``is_unusual`` is derived from the security's own baseline, so
    it is produced by the numbers rather than set by the test."""
    return MarketObservation(
        symbol="RELIANCE",
        as_of=NOW.date(),
        close=100.0,
        return_pct=6.0 if unusual else 0.2,
        raw_return_pct=6.0 if unusual else 0.2,
        volume=1_000_000.0,
        volume_ratio=1.0,
        baseline_sessions=120,
        baseline_sigma=1.5,
        sigma_multiple=4.0 if unusual else 0.2,
        sector_index="^NSEI",
        sector_return_pct=0.1,
        residual_pct=5.9 if unusual else 0.1,
        corporate_action=None,
    )


def codes(assessment) -> set[str]:
    return {r.code for r in assessment.reasons}


def test_a_quiet_market_is_recorded_when_we_actually_looked() -> None:
    assessed = assess(
        news_event(article("The Economic Times")),
        coverage(),
        observation(unusual=False),
        extraction=extraction(),
    )

    assert "NO_MARKET_REACTION" in codes(assessed)
    assert "NEWS_COINCIDES_WITH_MOVE" not in codes(assessed)


def test_a_market_we_did_not_observe_infers_nothing_from_the_silence() -> None:
    """ "We did not look" and "we looked and it was calm" license different conclusions.

    Only the second may lower what is claimed. The first is recorded as missing coverage,
    which is a different reason code entirely.
    """
    unobserved = assess(
        news_event(article("The Economic Times")),
        coverage(market=False),
        None,
        extraction=extraction(),
    )

    assert "NO_MARKET_REACTION" not in codes(unobserved)
    assert "NO_MARKET_OBSERVATION" in codes(unobserved)


def test_the_two_market_codes_are_mutually_exclusive() -> None:
    moved = assess(
        news_event(article("The Economic Times")),
        coverage(),
        observation(unusual=True),
        extraction=extraction(),
    )

    assert "NEWS_COINCIDES_WITH_MOVE" in codes(moved)
    assert "NO_MARKET_REACTION" not in codes(moved)


def test_a_story_carried_only_by_unrecognised_publishers_is_weaker_evidence() -> None:
    assessed = assess(news_event(article("MarketBeat")), coverage(), extraction=extraction())

    assert "UNRECOGNISED_PUBLISHER_ONLY" in codes(assessed)


def test_one_recognised_publisher_is_enough_to_clear_it() -> None:
    assessed = assess(
        news_event(article("MarketBeat"), article("The Economic Times", "a2")),
        coverage(),
        extraction=extraction(),
    )

    assert "UNRECOGNISED_PUBLISHER_ONLY" not in codes(assessed)


def test_an_unrecognised_publisher_is_not_silenced_by_corroboration() -> None:
    """A real story broken outside our list is promoted by independent reporting, which
    is the corroboration model working rather than the registry overriding it."""
    from smart_watchlist.core.corroboration import assess_corroboration

    evidence = (
        article("Whalesbook"),
        article("ascendants.in", "a2"),
        article("Trade Brains", "a3"),
    )
    assessed = assess(
        news_event(*evidence),
        coverage(),
        extraction=extraction(),
        corroboration=assess_corroboration(evidence),
    )

    assert "INDEPENDENT_CORROBORATION" in codes(assessed)
    assert assessed.attention.value in ("LOW", "MEDIUM", "HIGH"), (
        "three independent reports still reach the reader"
    )


def test_neither_new_code_can_decide_an_attention_level_alone() -> None:
    """Both are nudges. Price is often the slowest signal, so a quiet market must never
    be able to bury a development on its own (VISION §5)."""
    from smart_watchlist.core.scoring import THRESHOLDS, WEIGHTS

    assert WEIGHTS["NO_MARKET_REACTION"] == -1
    assert WEIGHTS["UNRECOGNISED_PUBLISHER_ONLY"] == -1
    combined = abs(WEIGHTS["NO_MARKET_REACTION"] + WEIGHTS["UNRECOGNISED_PUBLISHER_ONLY"])
    assert (
        combined
        < THRESHOLDS[
            __import__("smart_watchlist.core.models", fromlist=["Attention"]).Attention.MEDIUM
        ]
    )


def test_standing_is_not_a_scoring_input_twice_over() -> None:
    """The registry is expressed in the ledger exactly once, as one reason code."""
    assessed = assess(news_event(article("MarketBeat")), coverage(), extraction=extraction())
    standing_codes = [c for c in codes(assessed) if "PUBLISHER" in c or "STANDING" in c]

    assert standing_codes == ["UNRECOGNISED_PUBLISHER_ONLY"]


def test_a_hyphenated_masthead_is_not_truncated() -> None:
    """ "Mid-Day" is a publisher, not "Mid" with a suffix. Stripping a section marker must
    require whitespace around it, or the registry silently stops recognising names."""
    assert standing_of([article("Mid-Day")]) is SourceStanding.ESTABLISHED
    assert standing_of([article("The Hindu - Business")]) is SourceStanding.ESTABLISHED
