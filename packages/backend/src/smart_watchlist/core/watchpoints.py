"""Watch points — a level the reader asked to be told about, and the note saying why.

A user marks *"watch out for this"* on a company: a price level, and a sentence in their
own words. When a stored end-of-day close crosses that level, the point is triggered and
appears the next time they look (D37).

Three boundaries hold this together, and they are the reason it is a watch point rather
than an alert:

*It is the reader's claim, not ours.* A level someone chose is not a forecast, a target or
advice — it is a bookmark. Nothing here predicts a price, recommends an action, or lets a
watch point change an attention level. Shared verdicts stay identical for every reader
(D27); this is private state that produces a private observation beside them.

*It is settled on stored end-of-day closes.* Never intraday, never a live quote. So the
trigger says *"closed at ₹1,405 on 2026-09-04"* — a session and a number we hold — and not
*"hit ₹1,400"*, which would claim a tick we never saw.

*It announces once.* A triggered point stays triggered until the reader acknowledges it.
Re-running a cycle re-reads the same bars and must not re-announce anything, which is what
makes an unattended schedule safe to run as often as it likes.

Pure and I/O-free: the caller supplies the sessions, the clock and the storage.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date, datetime

    from .market import Bar

__all__ = [
    "MAX_NOTE",
    "Trigger",
    "WatchDirection",
    "WatchPoint",
    "direction_for",
    "evaluate",
    "percent_rejection_for",
    "rejection_for",
]

MAX_NOTE = 200
"""A sentence, not an essay. The note is a reminder to its author, not a document."""


class WatchDirection(Enum):
    """What has to happen for the point to be satisfied.

    The first two compare a close against a **price**. The second two compare a *move*
    against the price the point was set at, which is why ``created_close`` is frozen when
    the point is created and never recomputed (D39).
    """

    ABOVE = "ABOVE"
    BELOW = "BELOW"
    PERCENT_UP = "PERCENT_UP"
    """Risen by at least ``level`` percent from the price when the point was set."""
    PERCENT_DOWN = "PERCENT_DOWN"
    """Fallen by at least ``level`` percent from the price when the point was set."""

    @property
    def is_percent(self) -> bool:
        return self in (WatchDirection.PERCENT_UP, WatchDirection.PERCENT_DOWN)


@dataclass(frozen=True)
class Trigger:
    """The session that satisfied a watch point."""

    on: date
    close: float


@dataclass(frozen=True)
class WatchPoint:
    """One level on one company, for one reader."""

    point_id: str
    user_id: str
    symbol: str
    level: float
    """A price for ``ABOVE``/``BELOW``, a positive percentage magnitude otherwise."""
    direction: WatchDirection
    """Frozen at creation. Deriving it later from the current price would flip the meaning
    of the point as the price moved — a level set as "tell me if it falls to 1,300" would
    silently become "tell me if it rises to 1,300" the moment it fell."""
    note: str
    created_at: datetime
    created_close: float | None
    """What the company last closed at when the point was set.

    For a price point this is context — what the reader was reacting to. For a percentage
    point it is **the baseline the move is measured from**, frozen here so every later
    evaluation gives the same answer. A baseline that followed the price would make "down
    5%" unreachable in a slow decline, because the bar would move down with it (D39)."""
    triggered_on: date | None = None
    triggered_close: float | None = None
    acknowledged_at: datetime | None = None

    @property
    def is_triggered(self) -> bool:
        return self.triggered_on is not None

    @property
    def needs_attention(self) -> bool:
        """Triggered and not yet seen. The only state that asks anything of the reader."""
        return self.is_triggered and self.acknowledged_at is None


def direction_for(level: float, latest_close: float) -> WatchDirection:
    """Which way the reader must be watching, given where the price is now.

    Inferred rather than asked: someone setting a level above today's close is waiting for
    a rise, and making them say so is a question with only one correct answer. It is
    inferred *once* and then stored (see ``WatchPoint.direction``).
    """
    return WatchDirection.ABOVE if level > latest_close else WatchDirection.BELOW


def percent_rejection_for(percent: float, latest_close: float | None) -> str | None:
    """Why this percentage move cannot be watched for. ``None`` when it can."""
    if percent == 0:
        return "A percentage watch point needs a move to wait for, not zero."
    if abs(percent) > 100:
        return "A move of more than 100% is not something we can measure against a close."
    if latest_close is None or latest_close <= 0:
        return (
            "We hold no end-of-day close for this company yet, so there is no baseline to "
            "measure a move against."
        )
    return None


def rejection_for(level: float, latest_close: float | None) -> str | None:
    """Why this level cannot be set, in the reader's words. ``None`` when it can.

    A level already satisfied is refused rather than created-and-immediately-fired. An
    alert that goes off the instant you set it teaches you to ignore it, and the reader
    almost certainly meant a different number.
    """
    if level <= 0:
        return "A watch level has to be a positive price."
    if latest_close is None:
        return (
            "We hold no end-of-day close for this company yet, so there is nothing to "
            "measure a level against."
        )
    if level > latest_close:
        return None
    if level < latest_close:
        return None
    return (
        f"It last closed at exactly {latest_close:,.2f}. Choose a level above or below "
        "that, so there is a crossing to wait for."
    )


def evaluate(point: WatchPoint, bars: list[Bar]) -> Trigger | None:
    """The first session after creation whose close satisfies the point.

    Returns ``None`` for a point that is already triggered, so re-running a cycle over the
    same bars changes nothing — the idempotence that keeps an unattended schedule from
    announcing the same thing every fifteen minutes.

    Sessions on or before the creation date are ignored. A point is a question about what
    happens *next*; answering it from a session that had already closed when it was set
    would report history as news.
    """
    if point.is_triggered:
        return None

    created_on = point.created_at.date()
    for bar in sorted(bars, key=lambda b: b.on):
        if bar.on <= created_on or bar.close <= 0:
            continue
        if _satisfied(point, bar.close):
            return Trigger(on=bar.on, close=bar.close)
    return None


def _satisfied(point: WatchPoint, close: float) -> bool:
    """At or beyond what the reader asked for.

    ``>=`` rather than ``>``: a close exactly on the number they named is the thing they
    asked about.
    """
    if point.direction is WatchDirection.ABOVE:
        return close >= point.level
    if point.direction is WatchDirection.BELOW:
        return close <= point.level

    # Percentage: measured against the frozen baseline, never against the previous
    # session. "Down 5%" means down from where it was when you said so (D39).
    baseline = point.created_close
    if baseline is None or baseline <= 0:
        return False
    move = (close / baseline - 1) * 100
    if point.direction is WatchDirection.PERCENT_UP:
        return move >= point.level
    return move <= -point.level
