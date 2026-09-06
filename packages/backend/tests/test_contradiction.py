"""Contradiction is a deterministic link, and the gates own it (D29).

Each gate gets a test, because a gate that silently stops refusing is how a false
contradiction reaches a reader — and a false contradiction discredits every verdict
beside it.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from support import NOW, make_evidence

from smart_watchlist.core.contradiction import judge_dispute, propose_dispute
from smart_watchlist.core.models import ContradictionState, Event, SourceTier


def event(
    *,
    event_id: str,
    title: str,
    symbol: str = "RELIANCE",
    event_type: str = "Agreements",
    offset: timedelta = timedelta(),
    tier: SourceTier = SourceTier.CREDIBLE_REPORTING,
    publisher: str = "Reuters",
) -> Event:
    evidence = replace(
        make_evidence(symbol=symbol, category=event_type, ref=event_id, tier=tier),
        source="news",
        publisher=publisher,
        title=title,
        body=title,
        published_at=NOW + offset,
    )
    return Event(
        event_id=event_id,
        security_symbol=symbol,
        company_name="Reliance Industries Limited",
        event_type=event_type,
        description=title,
        occurred_at=NOW + offset,
        evidence=(evidence,),
    )


ORIGINAL = event(event_id="original", title="Reliance signs supply agreement with a partner")


def test_a_denial_from_an_equal_source_disputes_the_original() -> None:
    later = event(
        event_id="denial",
        title="Reliance denies it signed any supply agreement",
        offset=timedelta(days=1),
    )

    judged = judge_dispute(ORIGINAL, later, propose_dispute(later.evidence))

    assert judged is not None
    assert judged.confirmed is True
    assert judged.state is ContradictionState.DISPUTED
    assert judged.disputed_by == "denial"
    assert "denies" in judged.detail, "the words we relied on must be quoted back"


def test_a_retraction_is_a_different_state_from_a_denial() -> None:
    later = event(
        event_id="retraction",
        title="Correction to an earlier report: Reliance signed no agreement",
        offset=timedelta(days=1),
    )

    judged = judge_dispute(ORIGINAL, later, propose_dispute(later.evidence))

    assert judged is not None
    assert judged.state is ContradictionState.WITHDRAWN


def test_an_ordinary_follow_up_proposes_nothing() -> None:
    """Silence is the common case. Most articles are not contradicting anything."""
    later = event(
        event_id="followup",
        title="Reliance agreement expected to close this quarter",
        offset=timedelta(days=1),
    )

    assert propose_dispute(later.evidence) is None
    assert judge_dispute(ORIGINAL, later, propose_dispute(later.evidence)) is None


def test_a_weaker_source_cannot_dispute_a_stronger_one() -> None:
    """A forum post never disputes a filing."""
    filing = event(
        event_id="filing",
        title="Reliance confirms supply agreement",
        tier=SourceTier.OFFICIAL_DISCLOSURE,
        publisher="NSE",
    )
    chatter = event(
        event_id="chatter",
        title="User denies the Reliance agreement is real",
        tier=SourceTier.SOCIAL_DISCUSSION,
        publisher="Forum",
        offset=timedelta(days=1),
    )

    judged = judge_dispute(filing, chatter, propose_dispute(chatter.evidence))

    assert judged is not None
    assert judged.confirmed is False
    assert judged.state is ContradictionState.STANDING
    assert "less authoritative" in judged.detail


def test_an_earlier_publication_cannot_dispute_a_later_one() -> None:
    earlier_denial = event(
        event_id="earlier",
        title="Reliance denies any such agreement",
        offset=timedelta(days=-1),
    )

    judged = judge_dispute(ORIGINAL, earlier_denial, propose_dispute(earlier_denial.evidence))

    assert judged is not None
    assert judged.confirmed is False
    assert "not published after" in judged.detail


def test_a_different_company_is_never_a_contradiction() -> None:
    other = event(
        event_id="other",
        title="Infosys denies the reported agreement",
        symbol="INFY",
        offset=timedelta(days=1),
    )

    judged = judge_dispute(ORIGINAL, other, propose_dispute(other.evidence))

    assert judged is not None
    assert judged.confirmed is False
    assert "different company" in judged.detail


def test_a_dispute_beyond_the_window_is_a_separate_occurrence() -> None:
    much_later = event(
        event_id="much-later",
        title="Reliance denies any such agreement",
        offset=timedelta(days=30),
    )

    judged = judge_dispute(ORIGINAL, much_later, propose_dispute(much_later.evidence))

    assert judged is not None
    assert judged.confirmed is False
    assert "too far apart" in judged.detail


def test_an_event_cannot_dispute_itself() -> None:
    denial = event(
        event_id="denial", title="Reliance denies the agreement", offset=timedelta(days=1)
    )

    assert judge_dispute(denial, denial, propose_dispute(denial.evidence)) is None


def test_an_unconfirmed_proposal_is_recorded_as_a_possible_relationship() -> None:
    """Both records stay visible. The reader is shown a maybe, never told a contradiction."""
    weak = event(
        event_id="weak",
        title="Trader denies the Reliance agreement",
        tier=SourceTier.SOCIAL_DISCUSSION,
        offset=timedelta(days=1),
    )

    judged = judge_dispute(ORIGINAL, weak, propose_dispute(weak.evidence))

    assert judged is not None
    assert judged.disputed_by == "weak", "the link is kept even when the claim is not"
    assert "not confirmed" in judged.detail


# --- through the pipeline -------------------------------------------------------


FEED = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Tata Motors signs supply agreement with Vertelo - The Economic Times</title>
<link>https://example.invalid/a</link><guid>guid-a</guid>
<pubDate>Fri, 04 Sep 2026 10:00:00 GMT</pubDate>
<source url="https://economictimes.com">The Economic Times</source></item>
<item><title>Tata Motors denies it signed any supply agreement with Vertelo - Reuters</title>
<link>https://example.invalid/b</link><guid>guid-b</guid>
<pubDate>Sat, 05 Sep 2026 10:00:00 GMT</pubDate>
<source url="https://reuters.com">Reuters</source></item>
</channel></rss>"""


def news_source(body: str = FEED):
    import httpx

    from smart_watchlist.adapters.google_news import GoogleNewsSource

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body, headers={"content-type": "application/xml"})

    return GoogleNewsSource(transport=httpx.MockTransport(handler))


def test_a_denial_marks_the_original_disputed_without_deleting_it(tmp_path) -> None:
    """Both records readable, linked, and neither rewritten (D29)."""
    from smart_watchlist.adapters.rule_extractor import RuleExtractor
    from smart_watchlist.adapters.sqlite_store import SqliteAssessmentStore
    from smart_watchlist.core.pipeline import run_news_pipeline

    store = SqliteAssessmentStore(tmp_path / "disputes.db")

    _run, assessed = run_news_pipeline(news_source(), RuleExtractor(), store)

    claims = [a for a in assessed if "denies" not in a.event.description]
    denials = [a for a in assessed if "denies" in a.event.description]
    assert claims and denials, "a denial is a separate record, not evidence for the claim"

    original = store.get(claims[0].event.event_id)
    assert original is not None
    assert original.event.contradiction is ContradictionState.DISPUTED
    assert original.event.disputed_by == denials[0].event.event_id
    assert store.get(denials[0].event.event_id) is not None, "nothing is deleted"


def test_a_dispute_leaves_the_verdict_it_disputes_untouched(tmp_path) -> None:
    """Confidence is the axis a dispute moves; attention is not."""
    from smart_watchlist.adapters.rule_extractor import RuleExtractor
    from smart_watchlist.adapters.sqlite_store import SqliteAssessmentStore
    from smart_watchlist.core.pipeline import run_news_pipeline

    store = SqliteAssessmentStore(tmp_path / "untouched.db")

    _run, assessed = run_news_pipeline(news_source(), RuleExtractor(), store)
    claim = next(a for a in assessed if "denies" not in a.event.description)

    stored = store.get(claim.event.event_id)

    assert stored is not None
    assert stored.attention is claim.attention
    assert stored.score == claim.score
    assert stored.reasons == claim.reasons


def test_a_recorded_dispute_survives_re_ingesting_the_article(tmp_path) -> None:
    """Re-fetching the article a correction was about must not un-say the correction."""
    from smart_watchlist.adapters.rule_extractor import RuleExtractor
    from smart_watchlist.adapters.sqlite_store import SqliteAssessmentStore
    from smart_watchlist.core.pipeline import run_news_pipeline

    store = SqliteAssessmentStore(tmp_path / "again.db")
    _run, assessed = run_news_pipeline(news_source(), RuleExtractor(), store)
    claim = next(a for a in assessed if "denies" not in a.event.description)

    run_news_pipeline(news_source(), RuleExtractor(), store)

    stored = store.get(claim.event.event_id)
    assert stored is not None
    assert stored.event.contradiction is ContradictionState.DISPUTED
