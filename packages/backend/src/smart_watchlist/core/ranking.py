"""Canonical product ordering.

One function, in ``core``, because the order a reader sees is a product decision and not
a presentation detail. Every surface — the board, a review, a client on another device —
renders what this returns (D26, D22).

**Severity, then recency.** Attention level first; within a level, when the development
*occurred*, newest first. Score is not a tiebreaker and is not ordering: two HIGH items
ordered by score look ranked against each other, and the product does not claim that
precision. The level is the claim; the score is the mechanism that produced it (D4).

Recency is measured by ``occurred_at`` rather than ``assessed_at`` deliberately. The
review *window* is measured by when we learned something, because a late-arriving event
is still new to the user; ordering is measured by when it happened, because that is what
"newer" means to someone reading a list of dates. Two clocks, two questions, both kept.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .models import Attention

if TYPE_CHECKING:
    from .models import Assessment

__all__ = ["ATTENTION_RANK", "canonical_order"]

ATTENTION_RANK: dict[Attention, int] = {
    Attention.HIGH: 0,
    Attention.MEDIUM: 1,
    Attention.LOW: 2,
    Attention.NONE: 3,
    Attention.UNABLE: 4,
}
"""What each level asks of the reader, most demanding first.

``UNABLE`` sits last rather than first: it is an admission about our coverage, not a
finding about the company, and putting an admission above a finding would invert the
page. It is never hidden — the review's own sections carry it — but it does not lead.
"""


def canonical_order(items: list[Assessment]) -> list[Assessment]:
    """Order assessments as every client must show them.

    Stable and total: symbol breaks an exact tie so the same input always produces the
    same page, and a client comparing two renderings never sees phantom movement.
    """
    return sorted(
        items,
        key=lambda a: (
            ATTENTION_RANK[a.attention],
            -a.event.occurred_at.timestamp(),
            a.event.security_symbol,
        ),
    )
