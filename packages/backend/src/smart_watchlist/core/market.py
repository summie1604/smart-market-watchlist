"""Market observation — the deterministic half of the engine.

This module owns the ordering D14 fixes, and it owns it *structurally*: each stage
takes the previous stage's output, so the sequence cannot be reordered by accident.

    raw market data
      → corporate-action adjustment
      → normalized observation
      → own-security trailing baseline
      → sector/index residual
      → unusualness
      → reason-code contribution

Anomaly detection never runs before adjustment. A two-for-one split halves the printed
price; judged against an unadjusted series that is a 50% collapse, and no downstream
cleverness recovers from a corrupted input (VISION.md §5, scenario G).

No I/O, no model, no framework. Given bars, the answers here are reproducible.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date

__all__ = [
    "MIN_BASELINE_SESSIONS",
    "Bar",
    "MarketObservation",
    "observe",
]

MIN_BASELINE_SESSIONS = 20
"""Below this, a security's own trailing distribution is not a distribution.

Movement claims are still made — the price did what it did — but they are marked as
resting on a thin baseline rather than presented with the same confidence.
"""


@dataclass(frozen=True)
class Bar:
    """One session, as the source reported it.

    ``close`` is the printed price. ``adjusted_close`` is the same session corrected for
    corporate actions. Keeping both is what makes the adjustment visible instead of
    implicit — and lets the system say *"this move is mechanical"* rather than silently
    not reporting it.
    """

    on: date
    close: float
    adjusted_close: float
    volume: float
    split_ratio: float = 0.0
    """Non-zero when a split or bonus took effect this session. 2.0 is two-for-one."""
    dividend: float = 0.0


@dataclass(frozen=True)
class MarketObservation:
    """What the market did, and how unusual that is for this security.

    Every field is computed from primary data. Nothing here is inferred, and nothing
    here is a claim about *why* — causation is not this module's to assert (VISION.md §13).
    """

    symbol: str
    as_of: date
    close: float
    return_pct: float
    """Adjusted session return. Corporate actions are already removed."""
    raw_return_pct: float
    """Unadjusted return — what a naive reading of the printed price would have shown."""
    volume: float
    volume_ratio: float
    """Volume against its own trailing median. 1.0 is a typical session."""
    baseline_sessions: int
    baseline_sigma: float
    sigma_multiple: float
    """How many of this security's own standard deviations the move represents."""
    sector_index: str | None
    sector_return_pct: float | None
    residual_pct: float | None
    """Return minus sector return. ``None`` when no sector reference was available —
    absence, not zero, because zero would assert a comparison we could not make."""
    corporate_action: str | None
    """A description when this session carried a split, bonus or dividend."""

    @property
    def has_baseline(self) -> bool:
        return self.baseline_sessions >= MIN_BASELINE_SESSIONS and self.baseline_sigma > 0

    @property
    def is_unusual(self) -> bool:
        """Unusual relative to this security, never to a fixed percentage.

        A 3% move is routine for one security and extraordinary for another; a fixed
        threshold would encode exactly the magnitude-equals-meaning error the product
        rejects (VISION.md §5).
        """
        return self.has_baseline and abs(self.sigma_multiple) >= 2.0

    @property
    def is_mechanical(self) -> bool:
        """The printed move is explained by a corporate action, not by trading.

        True when an action landed this session and the adjusted move is materially
        smaller than the raw one — the scenario G case.
        """
        return (
            self.corporate_action is not None
            and abs(self.raw_return_pct) > abs(self.return_pct) + 1.0
        )

    @property
    def is_sector_explained(self) -> bool:
        """The move is broadly consistent with the sector's.

        Context, not cause. It licenses *"this looks like the market moving"* and never
        *"the sector caused this"* (VISION.md §13).
        """
        if self.residual_pct is None or not self.has_baseline:
            return False
        return abs(self.residual_pct) < abs(self.return_pct) / 2 and abs(self.return_pct) > 0


def observe(
    symbol: str,
    bars: list[Bar],
    sector_index: str | None = None,
    sector_bars: list[Bar] | None = None,
) -> MarketObservation | None:
    """Run the D14 chain over one security's bars.

    Returns ``None`` when there are too few complete sessions to compute a return at
    all. That is missing coverage, not a quiet verdict, and the caller must treat it so.
    """
    if len(bars) < 2:
        return None

    # Sessions are compared by adjacency, so their order is load-bearing. Sorting here
    # makes the function total rather than trusting every caller and every provider to
    # hand them over ascending.
    bars = sorted(bars, key=lambda b: b.on)
    latest, previous = bars[-1], bars[-2]

    # 1. Corporate-action adjustment — before anything is compared to anything.
    return_pct = _pct_change(previous.adjusted_close, latest.adjusted_close)
    raw_return_pct = _pct_change(previous.close, latest.close)
    corporate_action = _describe_action(latest)

    # 2. The security's own trailing baseline, computed on adjusted returns.
    history = _adjusted_returns(bars)
    baseline = history[:-1]
    sigma = statistics.pstdev(baseline) if len(baseline) >= 2 else 0.0
    volume_ratio = _volume_ratio(bars)

    # 3. Sector / index residual, aligned to the security's own session.
    sector_return = _sector_return(sector_bars, latest.on)
    residual = None if sector_return is None else return_pct - sector_return

    # 4. Unusualness, expressed in the security's own units.
    sigma_multiple = return_pct / sigma if sigma > 0 else 0.0

    return MarketObservation(
        symbol=symbol,
        as_of=latest.on,
        close=latest.close,
        return_pct=return_pct,
        raw_return_pct=raw_return_pct,
        volume=latest.volume,
        volume_ratio=volume_ratio,
        baseline_sessions=len(baseline),
        baseline_sigma=sigma,
        sigma_multiple=sigma_multiple,
        sector_index=sector_index,
        sector_return_pct=sector_return,
        residual_pct=residual,
        corporate_action=corporate_action,
    )


def _pct_change(before: float, after: float) -> float:
    return 0.0 if before == 0 else (after - before) / before * 100.0


def _adjusted_returns(bars: list[Bar]) -> list[float]:
    return [
        _pct_change(previous.adjusted_close, current.adjusted_close)
        for previous, current in pairwise(bars)
    ]


def _volume_ratio(bars: list[Bar]) -> float:
    volumes = [b.volume for b in bars[:-1] if b.volume > 0]
    if not volumes:
        return 0.0
    median = statistics.median(volumes)
    return 0.0 if median == 0 else bars[-1].volume / median


def _sector_return(sector_bars: list[Bar] | None, as_of: date) -> float | None:
    """The sector's move over the *same* session the security's move covers.

    A security can be halted, suspended or simply untraded on a day the index trades, so
    the two series do not always end on the same date. Taking the index's last two bars
    regardless would compare different sessions and produce a residual that looks
    precise and means nothing.

    Returns ``None`` when the index has no session at or before ``as_of`` to align to —
    absence rather than a fabricated comparison.
    """
    if sector_bars is None:
        return None
    aligned = sorted((b for b in sector_bars if b.on <= as_of), key=lambda b: b.on)
    if len(aligned) < 2:
        return None
    return _pct_change(aligned[-2].adjusted_close, aligned[-1].adjusted_close)


def _describe_action(bar: Bar) -> str | None:
    parts: list[str] = []
    if bar.split_ratio:
        parts.append(f"split or bonus, ratio {bar.split_ratio:g}")
    if bar.dividend:
        parts.append(f"dividend {bar.dividend:g}")
    return ", ".join(parts) if parts else None
