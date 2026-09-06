"""The scenario: six companies, one coherent day, fixed relationships.

Every timestamp is an offset from the moment the fixture is seeded, so the demo never
looks stale, and the *relationships* between events are constant — the disclosure always
precedes the move, which always precedes the reporting. That ordering is the point of the
timeline, so it is data rather than an accident of when the seed ran.

Nothing here asserts an attention level. The scenario supplies evidence; the engine
decides what it is worth, which is exactly what a judge should be able to check.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

__all__ = ["SCENARIO", "ScenarioArticle", "ScenarioCompany", "ScenarioDisclosure"]

SIMULATED_URL = "https://fixture.invalid"
"""A reserved, unresolvable host. Fixture evidence must never carry a link that implies
the simulated event actually happened somewhere real."""


@dataclass(frozen=True)
class ScenarioDisclosure:
    """An exchange filing the fixture exchange will return."""

    category: str
    title: str
    minutes_ago: int


@dataclass(frozen=True)
class ScenarioArticle:
    """One report. The publisher decides its source standing (D36), so the mix here is
    what makes established-versus-unrecognised visible in the UI."""

    publisher: str
    title: str
    minutes_ago: int


@dataclass(frozen=True)
class ScenarioCompany:
    """One company's simulated day.

    ``intent`` is a note for humans reading the fixture — never an input to scoring, and
    never rendered as a verdict. The engine may disagree with it, and if it does that is a
    finding about the engine rather than something to paper over here.
    """

    symbol: str
    intent: str
    closes: tuple[float, ...] = ()
    """Fourteen sessions of end-of-day closes, oldest first. Empty means the market source
    holds nothing for this company — a real coverage gap, visible as an unavailable price
    and a ``NO_MARKET_OBSERVATION`` reason code."""
    disclosures: tuple[ScenarioDisclosure, ...] = ()
    articles: tuple[ScenarioArticle, ...] = ()
    watch_margin_pct: float | None = None
    """Where to place a watch point, as a percentage above the second-to-last close.

    Relative rather than absolute because the close series compounds: a hardcoded ₹715 was
    far below the price the drift actually reached, so the point resolved to BELOW and
    never triggered. The level is derived from the same series the evaluator reads.
    """
    watch_note: str = ""
    interests: tuple[str, ...] = ()


def _drift(start: float, steps: tuple[float, ...]) -> tuple[float, ...]:
    """Compose a close series from percentage steps. Deterministic and readable."""
    closes = [start]
    for step in steps:
        closes.append(round(closes[-1] * (1 + step / 100), 2))
    return tuple(closes[1:])


BASELINE_SESSIONS = 130
"""Long enough for a real trailing distribution.

The first attempt used thirteen sessions and every assessment came back carrying
``THIN_BASELINE`` — the engine correctly refusing to call anything unusual against a
baseline it did not trust. The fixture was wrong, not the engine, and this is the fix.
"""

_STEPS = (0.2, -0.1, 0.3, -0.2, 0.1, 0.2, -0.3, 0.1, 0.2, -0.1, 0.1, 0.2)


def _flat(sessions: int = BASELINE_SESSIONS) -> tuple[float, ...]:
    """A calm trailing run, repeated deterministically.

    Unusualness is measured against a security's own distribution (D14), so a quiet run is
    what makes the final session register as unusual at all.
    """
    return tuple(_STEPS[index % len(_STEPS)] for index in range(sessions))


SCENARIO: tuple[ScenarioCompany, ...] = (
    ScenarioCompany(
        symbol="RELIANCE",
        intent="High attention: an exchange filing, an unusual company-specific move, and "
        "independent established reporting, none of it explained by the sector.",
        closes=_drift(1300.0, (*_flat(), 6.4)),
        disclosures=(
            ScenarioDisclosure(
                category="Outcome of Board Meeting",
                title="Board approves acquisition of a refining joint venture stake",
                minutes_ago=180,
            ),
        ),
        articles=(
            # Deliberately near-identical wording. Event identity is lexical for
            # rule-extracted articles (D12), so three reports of one occurrence have to
            # read like three reports of one occurrence or they become three events.
            ScenarioArticle(
                publisher="Reuters",
                title="Reliance Industries approves refining joint venture acquisition",
                minutes_ago=150,
            ),
            ScenarioArticle(
                publisher="The Economic Times",
                title="Reliance Industries approves refining joint venture acquisition",
                minutes_ago=140,
            ),
            ScenarioArticle(
                publisher="Business Standard",
                title="Reliance Industries approves refining joint venture acquisition deal",
                minutes_ago=120,
            ),
        ),
        interests=("commodities", "regulation"),
    ),
    ScenarioCompany(
        symbol="TCS",
        intent="Medium attention: real corroborated reporting with no unusual price move — "
        "the case that proves attention is not a price alert.",
        closes=_drift(2300.0, (*_flat(), 0.2)),
        articles=(
            ScenarioArticle(
                publisher="The Economic Times",
                title="TCS wins multi-year banking contract in Europe",
                minutes_ago=210,
            ),
            ScenarioArticle(
                publisher="Moneycontrol.com",
                title="TCS wins multi-year banking contract in Europe",
                minutes_ago=190,
            ),
        ),
        interests=("contracts",),
    ),
    ScenarioCompany(
        symbol="HDFCBANK",
        intent="Watch point: a level the reader set is crossed by the final stored close, "
        "and settles through the ordinary evaluator.",
        closes=_drift(700.0, (*_flat(), 3.1)),
        watch_margin_pct=1.5,
        watch_note="Tell me if it breaks out — I want to add on strength.",
        articles=(
            ScenarioArticle(
                publisher="Business Standard",
                title="HDFC Bank raises deposit rates across tenures",
                minutes_ago=200,
            ),
        ),
        interests=("regulation",),
    ),
    ScenarioCompany(
        symbol="ITC",
        intent="Coverage incomplete: nothing new, and one source family degraded — so the "
        "review says it could not evaluate rather than calling the company quiet. "
        "Coverage is a per-source-family verdict in this model, so within one review a "
        "company with nothing new is either quiet or unable, never one of each.",
        closes=_drift(260.0, (*_flat(), 0.1)),
    ),
    ScenarioCompany(
        symbol="INFY",
        intent="The source of the gap: the market feed holds nothing for this company, so "
        "its price is unavailable, its assessment records the missing observation, and the "
        "market family reports itself degraded for the whole run.",
        closes=(),
        articles=(
            ScenarioArticle(
                publisher="Business Standard",
                title="Infosys announces a partnership with a cloud provider",
                minutes_ago=160,
            ),
        ),
    ),
    ScenarioCompany(
        symbol="TMPV",
        intent="Sector-explained: the shares moved, and the sector moved with them. Context "
        "the system reports without inventing a company-specific cause.",
        closes=_drift(310.0, (*_flat(), 4.6)),
    ),
)

INDEX_MOVES: dict[str, float] = {"^CNXAUTO": 4.4}
"""How far each index moves on the final session, defaulting to ``QUIET_INDEX_MOVE``.

Only the auto index moves, and TMPV is the company judged against it — so TMPV's rise is
largely explained by its sector while RELIANCE's, judged against a broad index that barely
moved, is not. Two outcomes from one number, which is the comparison the scenario exists
to show. Moving every index instead made the engine attribute RELIANCE's move to the
sector as well, which was the fixture being wrong rather than the engine.
"""

QUIET_INDEX_MOVE = 0.0
"""Every other index is flat on the final session.

A 0.4% drift here made TCS's 0.3% move read as sector-explained — correctly, by the rule
in `is_sector_explained`. The fixture was asserting a comparison it had not set up, so the
index that is not part of the comparison now does not move.
"""

REVIEW_WINDOW = timedelta(hours=19)
"""How long ago the reader last completed a review. Long enough that the scenario's whole
day falls inside the window, so "since your last review" has something in it."""

WATCH_POINT_AGE = timedelta(days=2, hours=6)
"""How long before seeding the watch point was set.

Two days, and the arithmetic matters. The final stored session is *yesterday* — today's
has not settled — and `evaluate` ignores sessions on or before the creation date. So a
point has to predate the crossing session by a whole day to fire. That is the rule doing
its job (D37): a watch point is a question about what happens next, and the fixture
respects it rather than working around it.
"""
