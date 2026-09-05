"""Private user state — accounts, watchlists, and review checkpoints.

The boundary this module defends: **shared intelligence is computed once and belongs to
the world; user state belongs to one person.** A watchlist holds references to securities,
never copies of evidence or assessments, so ten thousand users watching Reliance produce
one Reliance analysis and ten thousand cheap diffs (DESIGN.md, *State*).

The review window is the correctness-critical part (D7). A review answers for the
half-open interval ``(previous_checkpoint, review_cutoff]``. The cutoff is issued by the
server when the review is assembled and stored, so completion resolves it by identity
rather than trusting a timestamp the client sends back. That is what makes forging a
cutoff impossible rather than merely discouraged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

__all__ = [
    "IssuedReview",
    "Membership",
    "Session",
    "User",
    "advance_checkpoint",
]


@dataclass(frozen=True)
class User:
    user_id: str
    email: str
    created_at: datetime


@dataclass(frozen=True)
class Session:
    session_id: str
    """Unpredictable and server-side. The cookie carries this and nothing else."""
    user_id: str
    created_at: datetime
    expires_at: datetime

    def is_active(self, now: datetime) -> bool:
        return now < self.expires_at


@dataclass(frozen=True)
class Membership:
    """One company on one user's watchlist."""

    user_id: str
    symbol: str
    added_at: datetime
    """Also the observation boundary: we did not watch this company for this user before
    they added it, and the first review must not pretend otherwise."""


@dataclass(frozen=True)
class IssuedReview:
    """A review the server assembled, and the cutoff it committed to.

    Stored because completion must resolve the cutoff from the server's own record. A
    client that returns a timestamp is returning a claim; a client that returns a review
    id is returning a reference.
    """

    review_id: str
    user_id: str
    previous_checkpoint: datetime | None
    review_cutoff: datetime
    issued_at: datetime


def advance_checkpoint(current: datetime | None, issued_cutoff: datetime) -> tuple[datetime, str]:
    """Decide the new checkpoint, and say why.

    Monotonic by construction: an older cutoff is a no-op rather than a regression, which
    is what keeps a stale tab from undoing a review completed on another device. Returns
    the resulting checkpoint and a reason, so the API can answer honestly instead of
    silently doing nothing.
    """
    if current is None:
        return issued_cutoff, "advanced"
    if issued_cutoff > current:
        return issued_cutoff, "advanced"
    if issued_cutoff == current:
        return current, "already-at-this-cutoff"
    return current, "stale-cutoff-ignored"
