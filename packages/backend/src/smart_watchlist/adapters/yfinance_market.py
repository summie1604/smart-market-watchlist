"""Market data via yfinance.

Provides the primary data the deterministic half of the engine runs on. Like every
adapter here it returns evidence and a coverage record together — including on failure,
where the bars are empty and the record says why. A market source that failed silently
would let a missing price read as a calm one.

Two properties of the feed are handled here rather than downstream, because they are
facts about this source and not about markets:

*The most recent bar is often incomplete* — it carries volume but a NaN close while the
session settles. Computing a return against it yields NaN and poisons the baseline, so
incomplete sessions are dropped and the newest complete bar becomes the reference.

*Adjusted and unadjusted closes are both kept.* The adjustment is what makes a split
visible as mechanical rather than silently invisible (D14, scenario G).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, SupportsFloat

from ..core.market import Bar
from ..core.models import CoverageRecord, CoverageStatus

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["SOURCE_NAME", "YFinanceMarketSource"]

SOURCE_NAME = "market"

_NSE_SUFFIX = ".NS"
_LOOKBACK = "6mo"
"""Long enough for a trailing baseline with room for holidays and suspensions."""


class YFinanceMarketSource:
    """Fetches daily bars for NSE securities and indices.

    Implements :class:`smart_watchlist.core.ports.MarketSource`.
    """

    name = SOURCE_NAME

    def __init__(self, lookback: str = _LOOKBACK) -> None:
        self._lookback = lookback

    def fetch(self, symbols: Sequence[str]) -> tuple[dict[str, list[Bar]], CoverageRecord]:
        """Bars per symbol, plus one coverage record for the run.

        A symbol that returns nothing is simply absent from the mapping — the caller
        treats absence as missing coverage for that security, never as a calm one.
        """
        observed_at = datetime.now(UTC)
        try:
            import yfinance
        except ImportError:
            return {}, CoverageRecord(
                source=SOURCE_NAME,
                status=CoverageStatus.UNAVAILABLE,
                observed_at=observed_at,
                detail="yfinance is not installed.",
            )

        bars: dict[str, list[Bar]] = {}
        failed: list[str] = []
        for symbol in symbols:
            try:
                frame = yfinance.Ticker(_to_yahoo(symbol)).history(
                    period=self._lookback, auto_adjust=False, raise_errors=False
                )
            except Exception:
                failed.append(symbol)
                continue
            series = _to_bars(frame)
            if series:
                bars[symbol] = series
            else:
                failed.append(symbol)

        return bars, _coverage(observed_at, requested=len(symbols), failed=failed)


def _coverage(observed_at: datetime, *, requested: int, failed: list[str]) -> CoverageRecord:
    if not failed:
        return CoverageRecord(
            source=SOURCE_NAME,
            status=CoverageStatus.OK,
            observed_at=observed_at,
            detail=f"{requested} securities retrieved.",
        )
    status = CoverageStatus.UNAVAILABLE if len(failed) == requested else CoverageStatus.DEGRADED
    return CoverageRecord(
        source=SOURCE_NAME,
        status=status,
        observed_at=observed_at,
        detail=f"No data for {len(failed)} of {requested}: {', '.join(sorted(failed)[:5])}.",
    )


def _to_yahoo(symbol: str) -> str:
    """Indices already carry their own namespace; equities need the NSE suffix."""
    return symbol if symbol.startswith("^") else f"{symbol}{_NSE_SUFFIX}"


def _to_bars(frame: Any) -> list[Bar]:
    """Convert a price frame to bars, discarding incomplete sessions."""
    if frame is None or getattr(frame, "empty", True):
        return []

    bars: list[Bar] = []
    for stamp, row in frame.iterrows():
        close = _number(row.get("Close"))
        if close is None:
            continue  # the session has not settled; it is not yet an observation
        adjusted = _number(row.get("Adj Close"))
        bars.append(
            Bar(
                on=stamp.date(),
                close=close,
                adjusted_close=close if adjusted is None else adjusted,
                volume=_number(row.get("Volume")) or 0.0,
                split_ratio=_number(row.get("Stock Splits")) or 0.0,
                dividend=_number(row.get("Dividends")) or 0.0,
            )
        )
    return bars


def _number(value: object) -> float | None:
    """A usable float, or ``None``. NaN is absence, not zero."""
    # Values arrive from pandas as object; narrow rather than suppress. SupportsFloat
    # covers numpy scalars, which are not int/float subclasses.
    if not isinstance(value, SupportsFloat | str):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number
