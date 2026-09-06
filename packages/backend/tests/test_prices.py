"""Price context: aligned on shared sessions, rebased, never interpolated (D28).

The failure this pins is the one Step 1 actually shipped: comparing a security's session
against an index's session of a different date. It is not a subtle error — it is a wrong
number that looks precise.
"""

from __future__ import annotations

from datetime import date

import pytest

from smart_watchlist.core.market import Bar
from smart_watchlist.core.prices import build_comparison, build_status


def bars(*rows: tuple[str, float]) -> list[Bar]:
    return [
        Bar(
            on=date.fromisoformat(day),
            close=close,
            adjusted_close=close,
            volume=1000.0,
            split_ratio=0.0,
            dividend=0.0,
        )
        for day, close in rows
    ]


def comparison(book: dict[str, list[Bar]], sector: str | None = "^CNXIT"):
    return build_comparison(
        "INFY",
        "Infosys Limited",
        book,
        sector_index=sector,
        sector_label="NIFTY IT",
        broad_index="^NSEI",
        broad_label="NIFTY 50",
    )


FULL = {
    "INFY": bars(("2026-09-01", 100.0), ("2026-09-02", 110.0), ("2026-09-03", 121.0)),
    "^CNXIT": bars(("2026-09-01", 200.0), ("2026-09-02", 210.0), ("2026-09-03", 220.0)),
    "^NSEI": bars(("2026-09-01", 400.0), ("2026-09-02", 404.0), ("2026-09-03", 408.0)),
}


def test_series_are_rebased_so_the_comparison_is_relative() -> None:
    """A rupee price beside an index level compares nothing."""
    result = comparison(FULL)

    security = next(s for s in result.series if s.role == "security")
    assert [round(p.value, 2) for p in security.points] == [100.0, 110.0, 121.0]
    assert round(security.change_pct, 2) == 21.0

    broad = next(s for s in result.series if s.role == "broad")
    assert round(broad.change_pct, 2) == 2.0


def test_a_session_missing_from_one_series_is_dropped_from_all_of_them() -> None:
    """No interpolation, no forward-fill: a comparison across dates is a wrong number."""
    book = dict(FULL)
    book["^CNXIT"] = bars(("2026-09-01", 200.0), ("2026-09-03", 220.0))

    result = comparison(book)

    assert result.sessions == 2
    for series in result.series:
        assert [p.on.isoformat() for p in series.points] == ["2026-09-01", "2026-09-03"]
    assert any("shares" in note for note in result.notes)


def test_a_benchmark_that_has_stopped_is_excluded_and_named() -> None:
    """Intersecting it away would silently truncate the company's own range."""
    book = dict(FULL)
    book["INFY"] = bars(
        ("2026-09-01", 100.0),
        ("2026-09-02", 110.0),
        ("2026-09-03", 121.0),
        ("2026-09-04", 130.0),
        ("2026-09-07", 140.0),
    )
    book["^CNXIT"] = bars(("2026-09-01", 200.0), ("2026-09-02", 210.0))
    book["^NSEI"] = bars(
        ("2026-09-01", 400.0),
        ("2026-09-02", 404.0),
        ("2026-09-03", 408.0),
        ("2026-09-04", 412.0),
        ("2026-09-07", 416.0),
    )

    result = comparison(book)

    assert [s.symbol for s in result.series] == ["INFY", "^NSEI"]
    assert result.sessions == 5, "the company's own range survives a stale benchmark"
    assert any("no data after 2026-09-02" in note for note in result.notes)


def test_no_curated_sector_index_is_said_rather_than_substituted() -> None:
    """Falling back to the broad index would imply a comparison we did not choose."""
    result = comparison({k: v for k, v in FULL.items() if k != "^CNXIT"}, sector=None)

    assert [s.role for s in result.series] == ["security", "broad"]
    assert any("No sector index is curated" in note for note in result.notes)


def test_a_security_with_no_bars_reports_that_rather_than_drawing_nothing() -> None:
    result = comparison({k: v for k, v in FULL.items() if k != "INFY"})

    assert result.is_empty
    assert result.series == ()
    assert "No end-of-day price data" in result.notes[0]


def test_a_single_shared_session_cannot_be_a_comparison() -> None:
    book = dict(FULL)
    book["^NSEI"] = bars(("2026-09-03", 408.0), ("2026-09-04", 412.0))
    book["^CNXIT"] = bars(("2026-09-03", 220.0), ("2026-09-04", 221.0))

    result = comparison(book)

    assert result.is_empty
    assert any("fewer than two trading sessions" in note for note in result.notes)


def test_the_broad_index_is_not_drawn_twice_as_its_own_sector() -> None:
    """Some companies name the broad index as their reference; one line, one comparison."""
    result = build_comparison(
        "RELIANCE",
        "Reliance Industries Limited",
        {
            "RELIANCE": FULL["INFY"],
            "^NSEI": FULL["^NSEI"],
        },
        sector_index="^NSEI",
        sector_label="NIFTY 50",
        broad_index="^NSEI",
        broad_label="NIFTY 50",
    )

    assert [s.role for s in result.series] == ["security", "broad"]
    assert any("narrower than NIFTY 50" in note for note in result.notes)


def test_status_uses_only_stored_end_of_day_bars() -> None:
    result = build_status("INFY", FULL["INFY"], point_limit=2)

    assert result.as_of == date(2026, 9, 3)
    assert result.close == 121.0
    assert result.daily_change_pct == pytest.approx(10.0)
    assert result.points == (110.0, 121.0)


def test_status_says_when_no_stored_price_exists() -> None:
    result = build_status("INFY", None)

    assert result.close is None
    assert result.daily_change_pct is None
    assert result.points == ()


def test_a_cards_trace_carries_the_session_behind_every_point() -> None:
    """A line with no dates invites the reader to guess one, and a guessed date on a
    price is a wrong fact wearing a chart's authority."""
    from smart_watchlist.core.prices import build_status

    status = build_status("INFY", FULL["INFY"])

    assert [s.on.isoformat() for s in status.sessions] == [
        "2026-09-01",
        "2026-09-02",
        "2026-09-03",
    ]
    assert [s.close for s in status.sessions] == list(status.points), (
        "the trace and its dates describe the same sessions"
    )


def test_a_security_with_no_bars_has_no_sessions_to_point_at() -> None:
    from smart_watchlist.core.prices import build_status

    status = build_status("INFY", [])

    assert status.sessions == ()
    assert status.points == ()
    assert status.close is None
