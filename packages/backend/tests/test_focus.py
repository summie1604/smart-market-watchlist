"""Interests filter and annotate; they never score (D27).

The property under test is a boundary, not a feature: whatever a user says they are
watching for, the verdict and its place in the order must be identical to what another
user sees. What changes is only whether we can say *why* it was relevant to them.
"""

from __future__ import annotations

from support import NOW, coverage, make_evidence

from smart_watchlist.core.focus import known_tags, matches_focus, normalise_tags
from smart_watchlist.core.models import Assessment, Attention, Confidence, Event


def assessment(*, event_type: str, description: str = "") -> Assessment:
    evidence = make_evidence(symbol="RELIANCE", category=event_type)
    return Assessment(
        event=Event(
            event_id="evt",
            security_symbol="RELIANCE",
            company_name="Reliance Industries Limited",
            event_type=event_type,
            description=description or f"Reliance {event_type}",
            occurred_at=NOW,
            evidence=(evidence,),
        ),
        attention=Attention.MEDIUM,
        confidence=Confidence.MEDIUM,
        reasons=(),
        coverage=coverage(),
        scoring_version="test",
        assessed_at=NOW,
        score=3,
    )


def test_a_matching_event_is_annotated_with_why() -> None:
    matched = matches_focus(assessment(event_type="Regulatory Action"), ("regulation",))

    assert [m.tag for m in matched] == ["regulation"]
    assert "regulator" in matched[0].why.lower()


def test_an_unmatched_event_is_left_unannotated_rather_than_guessed_at() -> None:
    assert matches_focus(assessment(event_type="Product Launch"), ("dividends",)) == ()


def test_no_tags_means_no_annotation() -> None:
    """A user who said nothing is not told what they were interested in."""
    assert matches_focus(assessment(event_type="Regulatory Action"), ()) == ()


def test_only_the_tags_the_user_chose_can_match() -> None:
    """A regulatory event does not get annotated as a contract because it could be."""
    matched = matches_focus(
        assessment(event_type="Regulatory Action", description="SEBI opens a probe"),
        ("contracts",),
    )

    assert matched == ()


def test_matching_is_token_bounded() -> None:
    """ "cci" must not match "accident" — a substring match is an unexplainable match."""
    matched = matches_focus(
        assessment(event_type="Product Launch", description="Plant accident reported"),
        ("regulation",),
    )

    assert matched == ()


def test_unknown_tags_are_dropped_rather_than_stored() -> None:
    """A tag with no mapping could never be explained, so it is never accepted."""
    assert normalise_tags(["earnings", "vibes", "EARNINGS"]) == ("earnings",)
    assert normalise_tags("earnings") == ()
    assert set(normalise_tags(list(known_tags()))) == set(known_tags())


def test_focus_does_not_touch_the_verdict() -> None:
    """The whole point: two readers, opposite interests, identical assessment."""
    subject = assessment(event_type="Financial Result Updates")
    before = (subject.attention, subject.confidence, subject.score)

    matches_focus(subject, ("earnings",))
    matches_focus(subject, ("commodities",))

    assert (subject.attention, subject.confidence, subject.score) == before
