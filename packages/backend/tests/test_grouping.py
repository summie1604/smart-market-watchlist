"""Presentation grouping (D43).

The rule is deliberately weaker than event identity and deliberately narrow. Most of these
tests are about what it refuses to group, because a false merge on the board is the one
outcome that would make the product actively misleading — and mild duplication is the
failure it is allowed to have.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from support import coverage, make_evidence

from smart_watchlist.core.engine import assess
from smart_watchlist.core.grouping import development_ids
from smart_watchlist.core.models import Event
from smart_watchlist.core.ranking import canonical_order

NOW = datetime(2026, 9, 6, 12, tzinfo=UTC)


def item(
    event_id: str,
    description: str,
    *,
    symbol: str = "RELIANCE",
    event_type: str = "Agreements",
    minutes_ago: int = 0,
    source: str = "news",
):
    from dataclasses import replace

    when = NOW - timedelta(minutes=minutes_ago)
    evidence = replace(
        make_evidence(symbol=symbol, category=event_type, ref=event_id),
        source=source,
        title=description,
        body=description,
        published_at=when,
    )
    return assess(
        Event(
            event_id=event_id,
            security_symbol=symbol,
            company_name=symbol,
            event_type=event_type,
            description=description,
            occurred_at=when,
            evidence=(evidence,),
        ),
        coverage(),
    )


def grouped(*items) -> dict[str, str]:
    return development_ids(canonical_order(list(items)))


def count_groups(mapping: dict[str, str]) -> int:
    return len(set(mapping.values()))


# --- what it groups ---------------------------------------------------------------


def test_reports_of_one_story_group_across_event_types() -> None:
    """The case that prompted this: one announcement, three classifications.

    The rule extractor put these in three D12 buckets, so linking could never consider
    them — while a reader sees one story reported three ways.
    """
    mapping = grouped(
        item("a", "Reliance Industries approves refining joint venture acquisition deal"),
        item(
            "b",
            "Reliance Industries approves refining joint venture acquisition",
            event_type="Acquisition",
            minutes_ago=30,
        ),
        item(
            "c",
            "Board approves acquisition of a refining joint venture stake",
            event_type="Outcome of Board Meeting",
            minutes_ago=60,
            source="nse-disclosures",
        ),
    )

    assert count_groups(mapping) == 1


def test_an_ungrouped_item_points_at_itself() -> None:
    """So a caller never has to special-case the ungrouped case."""
    mapping = grouped(item("solo", "Reliance opens a new petrochemical plant in Jamnagar"))

    assert mapping == {"solo": "solo"}


def test_the_primary_is_the_first_in_canonical_order() -> None:
    """Presentation reuses the backend's one ranking answer rather than inventing another."""
    ordered = canonical_order(
        [
            item("older", "Reliance approves refining joint venture acquisition", minutes_ago=90),
            item("newer", "Reliance approves refining joint venture acquisition", minutes_ago=5),
        ]
    )

    mapping = development_ids(ordered)

    assert set(mapping.values()) == {ordered[0].event.event_id}
    assert ordered[0].event.event_id == "newer", "canonical order is severity then recency"


# --- what it refuses to group ------------------------------------------------------


def test_different_companies_never_group() -> None:
    """The one error that would make the board actively misleading."""
    mapping = grouped(
        item("r", "Board approves refining joint venture acquisition", symbol="RELIANCE"),
        item("i", "Board approves refining joint venture acquisition", symbol="INFY"),
    )

    assert count_groups(mapping) == 2


def test_similar_timing_alone_does_not_group() -> None:
    mapping = grouped(
        item("a", "Reliance completes a rights issue of equity shares", minutes_ago=10),
        item("b", "Reliance opens a new retail distribution centre", minutes_ago=12),
    )

    assert count_groups(mapping) == 2


def test_distance_in_time_separates_otherwise_similar_reports() -> None:
    """Beyond D12's window the same words are more likely a second occurrence."""
    mapping = grouped(
        item("a", "Reliance approves refining joint venture acquisition"),
        item("b", "Reliance approves refining joint venture acquisition", minutes_ago=60 * 24 * 9),
    )

    assert count_groups(mapping) == 2


def test_two_distinct_disclosures_stay_distinct() -> None:
    mapping = grouped(
        item("a", "Board approves acquisition of a refining stake", source="nse-disclosures"),
        item("b", "Board declares an interim dividend for shareholders", source="nse-disclosures"),
    )

    assert count_groups(mapping) == 2


def test_a_market_observation_does_not_join_the_story_it_coincides_with() -> None:
    """Different kind of claim, and the words do not overlap. It stays its own item."""
    mapping = grouped(
        item("story", "Reliance approves refining joint venture acquisition"),
        item(
            "move",
            "RELIANCE moved +6.4% (+35.3 times its own typical session).",
            event_type="Unusual price movement",
            source="market",
        ),
    )

    assert count_groups(mapping) == 2


def test_similarity_does_not_chain_through_a_middle_item() -> None:
    """A candidate is compared against a group's primary, never against any member, so
    A~B and B~C cannot drag in a C that is unlike A."""
    mapping = grouped(
        item("a", "Reliance approves refining joint venture acquisition agreement"),
        item("b", "Reliance approves refining joint venture stake purchase", minutes_ago=10),
        item("c", "Reliance stake purchase in a telecom tower company", minutes_ago=20),
    )

    assert mapping["c"] == "c", "the far end of a chain keeps its own development"


def test_grouping_is_deterministic() -> None:
    items = [
        item("a", "Reliance approves refining joint venture acquisition"),
        item("b", "Reliance approves refining joint venture acquisition", minutes_ago=20),
        item("c", "Reliance opens a new retail distribution centre", minutes_ago=40),
    ]

    assert development_ids(canonical_order(items)) == development_ids(canonical_order(items))
