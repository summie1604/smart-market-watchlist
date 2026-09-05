"""The D14 chain, tested where it is pure — no network, no database.

Scenario G is the one that justifies the ordering: a mechanical price move must be
adjusted before anomaly detection, not explained away afterwards.
"""

from __future__ import annotations

from datetime import date, timedelta

from smart_watchlist.core.market import MIN_BASELINE_SESSIONS, Bar, observe

START = date(2026, 6, 1)


def steady_bars(n: int = 40, price: float = 100.0, step: float = 0.2) -> list[Bar]:
    """A calm series: small alternating moves, so sigma is small but non-zero."""
    bars: list[Bar] = []
    for i in range(n):
        close = price + (step if i % 2 else -step)
        bars.append(
            Bar(on=START + timedelta(days=i), close=close, adjusted_close=close, volume=1_000_000)
        )
    return bars


def test_a_calm_series_is_not_unusual() -> None:
    observation = observe("CALM", steady_bars())

    assert observation is not None
    assert observation.has_baseline
    assert not observation.is_unusual


def test_a_move_is_judged_against_the_securitys_own_baseline() -> None:
    """Not against a fixed percentage — the same move means different things."""
    bars = steady_bars()
    bars.append(
        Bar(on=START + timedelta(days=99), close=103.0, adjusted_close=103.0, volume=1_000_000)
    )

    observation = observe("JUMPY", bars)

    assert observation is not None
    assert observation.is_unusual
    assert abs(observation.sigma_multiple) >= 2.0


def test_scenario_g_a_split_is_adjusted_before_anomaly_detection() -> None:
    """A two-for-one split halves the printed price.

    Unadjusted that reads as a 50% collapse. The chain must remove it first, so the
    system reports a corporate action rather than a catastrophe.
    """
    bars = steady_bars()
    bars.append(
        Bar(
            on=START + timedelta(days=99),
            close=50.0,  # printed price halves
            adjusted_close=100.0,  # economically unchanged
            volume=1_000_000,
            split_ratio=2.0,
        )
    )

    observation = observe("SPLIT", bars)

    assert observation is not None
    assert observation.raw_return_pct < -45.0, "the printed move really is a halving"
    assert abs(observation.return_pct) < 1.0, "the adjusted move is nothing"
    assert observation.is_mechanical
    assert not observation.is_unusual, "a split must never register as unusual movement"
    assert observation.corporate_action is not None


def test_scenario_a_an_unusual_move_carries_no_explanation_of_its_own() -> None:
    """The observation reports what happened and offers no cause.

    Scenario A depends on this: with no company event, there must be nothing in the
    observation for the system to mistake for a reason.
    """
    bars = steady_bars()
    bars.append(
        Bar(on=START + timedelta(days=99), close=104.0, adjusted_close=104.0, volume=5_000_000)
    )

    observation = observe("UNEXPLAINED", bars)

    assert observation is not None
    assert observation.is_unusual
    assert observation.corporate_action is None
    assert observation.sector_return_pct is None
    assert observation.residual_pct is None, "no sector data means no comparison, not a zero one"


def test_a_move_matching_its_sector_is_marked_as_sector_explained() -> None:
    bars = steady_bars()
    bars.append(
        Bar(on=START + timedelta(days=99), close=104.0, adjusted_close=104.0, volume=1_000_000)
    )
    sector = [
        Bar(on=START, close=100.0, adjusted_close=100.0, volume=0),
        Bar(on=START + timedelta(days=99), close=103.8, adjusted_close=103.8, volume=0),
    ]

    observation = observe("WITHSECTOR", bars, sector_index="^NSEI", sector_bars=sector)

    assert observation is not None
    assert observation.residual_pct is not None
    assert observation.is_sector_explained


def test_a_thin_baseline_withholds_the_unusualness_claim() -> None:
    """Too few sessions is not a distribution, and must not be treated as one."""
    bars = steady_bars(n=MIN_BASELINE_SESSIONS - 5)
    bars.append(
        Bar(on=START + timedelta(days=99), close=140.0, adjusted_close=140.0, volume=1_000_000)
    )

    observation = observe("NEW", bars)

    assert observation is not None
    assert not observation.has_baseline
    assert not observation.is_unusual, "a large move on a thin baseline is not yet a claim"


def test_too_few_bars_is_absence_not_a_quiet_verdict() -> None:
    assert observe("EMPTY", []) is None
    assert observe("ONE", steady_bars(n=1)) is None


def test_the_sector_residual_aligns_to_the_securitys_own_session() -> None:
    """A halted security and a trading index do not end on the same date.

    Taking the index's last two bars regardless would compare different sessions and
    produce a residual that looks precise and means nothing.
    """
    bars = steady_bars()
    bars.append(Bar(on=date(2026, 9, 2), close=104.0, adjusted_close=104.0, volume=1_000_000))
    index_traded_a_day_later = [
        Bar(on=date(2026, 9, 2), close=100.0, adjusted_close=100.0, volume=0),
        Bar(on=date(2026, 9, 3), close=97.0, adjusted_close=97.0, volume=0),
    ]

    observation = observe(
        "HALTED", bars, sector_index="^NSEI", sector_bars=index_traded_a_day_later
    )

    assert observation is not None
    assert observation.as_of == date(2026, 9, 2)
    assert observation.residual_pct is None, (
        "with no aligned index session, absence beats a fabricated comparison"
    )


def test_the_sector_residual_uses_the_matching_session_when_one_exists() -> None:
    bars = steady_bars()
    bars.append(Bar(on=date(2026, 9, 2), close=104.0, adjusted_close=104.0, volume=1_000_000))
    index = [
        Bar(on=date(2026, 9, 1), close=100.0, adjusted_close=100.0, volume=0),
        Bar(on=date(2026, 9, 2), close=103.8, adjusted_close=103.8, volume=0),
        Bar(on=date(2026, 9, 3), close=90.0, adjusted_close=90.0, volume=0),  # must be ignored
    ]

    observation = observe("ALIGNED", bars, sector_index="^NSEI", sector_bars=index)

    assert observation is not None
    assert observation.sector_return_pct is not None
    assert observation.sector_return_pct > 0, "the 09-03 crash is not this security's session"


def test_bars_out_of_order_do_not_silently_pick_the_wrong_session() -> None:
    """Adjacency is load-bearing; the function must not trust its caller's ordering."""
    ascending = steady_bars()
    descending = list(reversed(ascending))

    assert observe("A", ascending) == observe("A", descending)
