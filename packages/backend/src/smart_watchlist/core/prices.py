"""Price context: a company against its benchmarks, over sessions they actually share.

Illustrative, and deliberately so. A chart is context; an assessment is a claim. Nothing
here feeds the engine, nothing here becomes evidence, and no verdict changes because of
what a line does (D28).

Three rules carry the whole module:

*End of day, corporate-action adjusted.* The same bars the engine already observes. The
adjusted close is what makes a split visible as mechanical rather than as a crash.

*Aligned on the sessions every included series has.* A session missing from one series is
dropped from all of them. Nothing is interpolated or forward-filled, because comparing a
company's Tuesday against an index's Monday is not a subtle error — it is a wrong number
that looks precise. Step 1 shipped exactly that bug in the sector residual, and this is
the same rule stated once and generalised.

*Rebased to 100 at the first common session.* The question is relative movement, not
price level; a rupee price beside an index level compares nothing.

A benchmark that has stopped updating is **excluded and named**, not silently intersected
away. Intersection is the right answer for a holiday or a suspension — a handful of
missing sessions. It is the wrong answer for a series that ends months early: it would
truncate the company's own chart to the benchmark's last day and present that as the
range the user asked for. Excluding it keeps the company's real span and says which
comparison could not be made.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date

    from .market import Bar

__all__ = [
    "MAX_TRAILING_GAP",
    "PriceComparison",
    "PriceSession",
    "PriceStatus",
    "Series",
    "SeriesPoint",
    "build_comparison",
    "build_status",
]

MAX_TRAILING_GAP = 2
"""How many of the security's most recent sessions a benchmark may be missing.

Measured at the *end* of the series rather than across it, because that is what
distinguishes the two cases. A benchmark that skipped a day in March has gaps, and the
intersection handles it. A benchmark whose last session is months behind the security's
has stopped, and intersecting it would cut the company's chart back to that day.

Two sessions is judgement, held stable by tests: enough to absorb a holiday or a late
publication, too few to hide a feed that has gone quiet.
"""


@dataclass(frozen=True)
class SeriesPoint:
    on: date
    value: float
    """Rebased to 100 at the first common session — a relative level, never a price."""


@dataclass(frozen=True)
class Series:
    symbol: str
    label: str
    role: str
    """``security`` · ``sector`` · ``broad`` — what this line is for."""
    points: tuple[SeriesPoint, ...]

    @property
    def change_pct(self) -> float:
        """Movement across the covered span, in percent. Zero for an empty series."""
        if len(self.points) < 2:
            return 0.0
        return self.points[-1].value - 100.0


@dataclass(frozen=True)
class PriceComparison:
    """What could honestly be drawn for one company over one requested range."""

    symbol: str
    series: tuple[Series, ...]
    covered_from: date | None
    covered_to: date | None
    sessions: int
    notes: tuple[str, ...]
    """Everything the reader needs in order to trust or discount the picture: a benchmark
    that was excluded, a span shorter than the one requested, or no data at all."""

    @property
    def is_empty(self) -> bool:
        return not self.series or self.sessions < 2


@dataclass(frozen=True)
class PriceSession:
    """One stored end-of-day session: the date, and the close on it."""

    on: date
    close: float


@dataclass(frozen=True)
class PriceStatus:
    """The small, honest price context a watchlist card may show (D34)."""

    symbol: str
    as_of: date | None
    close: float | None
    daily_change: float | None
    """The move in rupees, derived from the two stored closes rather than persisted. A
    stored copy of a subtraction is a second place for it to disagree with itself."""
    daily_change_pct: float | None
    day_high: float | None
    """The latest session's range, as the provider reported it. ``None`` where it did not
    — never the close standing in for a high it did not give."""
    day_low: float | None
    day_volume: float | None
    points: tuple[float, ...]
    """Closes alone, for drawing a trace."""
    sessions: tuple[PriceSession, ...] = ()
    """The same closes with the session each belongs to.

    Carried so a reader can point at the trace and be told *which day* — a line with no
    dates invites the reader to guess at one, and a guessed date on a price is a wrong
    fact wearing a chart's authority.
    """


def build_status(symbol: str, bars: list[Bar] | None, *, point_limit: int = 14) -> PriceStatus:
    """Return a stored end-of-day status; never fetch or interpolate for a card."""
    ordered = sorted(bars or [], key=lambda bar: bar.on)
    if not ordered:
        return PriceStatus(
            symbol=symbol,
            as_of=None,
            close=None,
            daily_change=None,
            daily_change_pct=None,
            day_high=None,
            day_low=None,
            day_volume=None,
            points=(),
            sessions=(),
        )

    latest = ordered[-1]
    previous = ordered[-2] if len(ordered) > 1 else None
    comparable = previous is not None and previous.adjusted_close > 0
    daily_change_pct = (
        None
        if not comparable or previous is None
        else (latest.adjusted_close / previous.adjusted_close - 1) * 100
    )
    daily_change = (
        None
        if not comparable or previous is None
        else latest.adjusted_close - previous.adjusted_close
    )
    # One pass, so the trace and its dates can never disagree about which sessions the
    # card is showing.
    recent = [bar for bar in ordered[-point_limit:] if bar.close > 0]
    return PriceStatus(
        symbol=symbol,
        as_of=latest.on,
        close=latest.close,
        daily_change=daily_change,
        daily_change_pct=daily_change_pct,
        day_high=latest.high,
        day_low=latest.low,
        day_volume=latest.volume or None,
        points=tuple(bar.close for bar in recent),
        sessions=tuple(PriceSession(on=bar.on, close=bar.close) for bar in recent),
    )


def build_comparison(
    symbol: str,
    label: str,
    bars: dict[str, list[Bar]],
    *,
    sector_index: str | None,
    sector_label: str,
    broad_index: str,
    broad_label: str,
    since: date | None = None,
) -> PriceComparison:
    """Align a company and its benchmarks, and say what could not be included.

    ``bars`` is what the market adapter returned. A symbol absent from it has no data —
    which is reported, never approximated.
    """
    notes: list[str] = []

    own = _in_range(bars.get(symbol), since)
    if len(own) < 2:
        return PriceComparison(
            symbol=symbol,
            series=(),
            covered_from=None,
            covered_to=None,
            sessions=0,
            notes=("No end-of-day price data is available for this security in this range.",),
        )

    candidates: list[tuple[str, str, str, dict[date, float]]] = [(symbol, label, "security", own)]
    # Some curated companies name the broad index as their sector reference, because no
    # narrower index fits them. Drawing it twice would suggest two comparisons where
    # there is one.
    sector = None if sector_index == broad_index else sector_index
    if sector is None and sector_index is not None:
        notes.append(
            f"No sector index narrower than {broad_label} is curated for this company, so "
            "the comparison is against the broad market alone."
        )

    for index_symbol, index_label, role in (
        (sector, sector_label, "sector"),
        (broad_index, broad_label, "broad"),
    ):
        if index_symbol is None and sector_index is not None and role == "sector":
            continue
        if index_symbol is None:
            notes.append(
                "No sector index is curated for this company, so no sector comparison is "
                "shown. We would rather show nothing than compare it to an index we did "
                "not choose for it."
            )
            continue
        series = _in_range(bars.get(index_symbol), since)
        if len(series) < 2:
            notes.append(f"{index_label} returned no data for this range and is not shown.")
            continue
        if _stale_against(series, own):
            last = max(series)
            notes.append(
                f"{index_label} has no data after {last.isoformat()} and is excluded, so the "
                "company's own range is not cut short by it."
            )
            continue
        candidates.append((index_symbol, index_label, role, series))

    common = sorted(set.intersection(*(set(s[3]) for s in candidates)))
    if len(common) < 2:
        return PriceComparison(
            symbol=symbol,
            series=(),
            covered_from=None,
            covered_to=None,
            sessions=0,
            notes=(
                *notes,
                "These series share fewer than two trading sessions in this range, so no "
                "comparison can be drawn.",
            ),
        )

    # Any session the security has but the comparison could not use is worth saying,
    # whether it was trimmed from the ends or dropped from the middle.
    if len(common) < len(own):
        notes.append(
            f"Compared over the {len(common)} sessions every series shares, "
            f"{common[0].isoformat()} to {common[-1].isoformat()}. Sessions missing from any "
            "series are dropped from all of them rather than filled in."
        )

    return PriceComparison(
        symbol=symbol,
        series=tuple(
            Series(
                symbol=series_symbol,
                label=series_label,
                role=role,
                points=_rebase(values, common),
            )
            for series_symbol, series_label, role, values in candidates
        ),
        covered_from=common[0],
        covered_to=common[-1],
        sessions=len(common),
        notes=tuple(notes),
    )


def _in_range(series: list[Bar] | None, since: date | None) -> dict[date, float]:
    """Adjusted closes by session, filtered to the requested range."""
    if not series:
        return {}
    return {
        bar.on: bar.adjusted_close
        for bar in series
        if since is None or bar.on >= since
        if bar.adjusted_close > 0
    }


def _stale_against(benchmark: dict[date, float], own: dict[date, float]) -> bool:
    """Whether a benchmark has stopped rather than merely missed sessions."""
    last = max(benchmark)
    trailing = sum(1 for on in own if on > last)
    return trailing > MAX_TRAILING_GAP


def _rebase(values: dict[date, float], common: list[date]) -> tuple[SeriesPoint, ...]:
    """Restrict to the shared sessions and rebase to 100 at the first of them."""
    base = values[common[0]]
    if base <= 0:
        return ()
    return tuple(SeriesPoint(on=on, value=values[on] / base * 100.0) for on in common)
