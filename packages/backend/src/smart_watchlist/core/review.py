"""Review assembly — one user's answer to "what changed since I last checked?"

This layer **filters shared intelligence; it never rescores it**. The engine decided what
each event asks of a reader and in what order; a review selects the subset inside this
user's window and leaves that order alone. Rescoring here would be a second, divergent
answer to a product question (D22).

The window is half-open: ``(previous_checkpoint, review_cutoff]``. Events at exactly the
previous checkpoint were covered by the last review; events at the cutoff are covered by
this one.

Two honesty rules carry over from earlier steps and matter more here, because this is the
surface a person actually reads:

*A company is only quiet if we could look.* Missing coverage produces "could not evaluate",
never silence (D15).

*A newly added company has no history with this user.* Its window starts when they added
it, and the review says so rather than presenting old events as things they missed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .context import CoverageTier, context_for

if TYPE_CHECKING:
    from datetime import datetime

    from .models import Assessment, Attention, Coverage
    from .userstate import Membership

__all__ = ["CompanyLine", "Review", "assemble"]


@dataclass(frozen=True)
class CompanyLine:
    """One watched company's standing in this review."""

    symbol: str
    company_name: str
    coverage_tier: str
    state: str
    """``changed`` · ``quiet`` · ``unable`` · ``new`` — what we can honestly say."""
    detail: str
    assessments: tuple[Assessment, ...] = ()

    @property
    def is_quiet(self) -> bool:
        return self.state == "quiet"


@dataclass(frozen=True)
class Review:
    """What one user missed, for one window."""

    user_id: str
    previous_checkpoint: datetime | None
    review_cutoff: datetime
    lines: tuple[CompanyLine, ...] = field(default=())

    @property
    def changed(self) -> tuple[CompanyLine, ...]:
        return tuple(line for line in self.lines if line.state == "changed")

    @property
    def quiet(self) -> tuple[CompanyLine, ...]:
        return tuple(line for line in self.lines if line.state == "quiet")

    @property
    def unable(self) -> tuple[CompanyLine, ...]:
        return tuple(line for line in self.lines if line.state == "unable")

    @property
    def newly_added(self) -> tuple[CompanyLine, ...]:
        return tuple(line for line in self.lines if line.state == "new")

    @property
    def attention_count(self) -> int:
        return sum(len(line.assessments) for line in self.changed)


def assemble(
    user_id: str,
    memberships: list[Membership],
    previous_checkpoint: datetime | None,
    review_cutoff: datetime,
    assessments: list[Assessment],
    coverage: Coverage,
) -> Review:
    """Build a review from shared assessments and this user's own state.

    ``assessments`` arrive in the engine's canonical order and leave in it. Nothing here
    sorts, scores, or re-ranks.

    ``coverage`` is *current* source health, from the latest ingest runs. It must be
    passed in rather than derived from the assessments in the window: a company with no
    assessments has nothing to read coverage from, and inferring "quiet" from that would
    turn blindness into a conclusion — the one failure this product cannot afford (D15).
    """
    by_symbol: dict[str, list[Assessment]] = {}
    for assessment in assessments:
        by_symbol.setdefault(assessment.event.security_symbol, []).append(assessment)

    lines: list[CompanyLine] = []
    for membership in memberships:
        context = context_for(membership.symbol, membership.symbol)
        # A company added mid-window was not watched for this user before that moment.
        window_start = _later(previous_checkpoint, membership.added_at)
        in_window = [
            a
            for a in by_symbol.get(membership.symbol, [])
            if window_start is None or window_start < a.event.occurred_at <= review_cutoff
        ]
        lines.append(_line(membership, context, in_window, previous_checkpoint, coverage))

    return Review(
        user_id=user_id,
        previous_checkpoint=previous_checkpoint,
        review_cutoff=review_cutoff,
        lines=tuple(lines),
    )


def _line(
    membership: Membership,
    context: object,
    in_window: list[Assessment],
    previous_checkpoint: datetime | None,
    coverage: Coverage,
) -> CompanyLine:
    tier = getattr(context, "tier", CoverageTier.LIMITED)
    name = getattr(context, "name", membership.symbol)
    tier_name = tier.value if isinstance(tier, CoverageTier) else str(tier)

    if previous_checkpoint is not None and membership.added_at > previous_checkpoint:
        return CompanyLine(
            symbol=membership.symbol,
            company_name=name,
            coverage_tier=tier_name,
            state="new",
            detail=(
                "Added during this window. We did not watch this company for you before "
                f"{membership.added_at.isoformat()}, so nothing earlier is reported as missed."
            ),
            assessments=tuple(in_window),
        )

    if in_window:
        return CompanyLine(
            symbol=membership.symbol,
            company_name=name,
            coverage_tier=tier_name,
            state="changed",
            detail=f"{len(in_window)} assessed change{'s' if len(in_window) != 1 else ''}.",
            assessments=tuple(in_window),
        )

    # Nothing in the window. Whether that is a conclusion or an admission depends on
    # whether we could look — which is current coverage, not anything the empty window
    # can tell us.
    blind = {record.source for record in coverage.missing}
    if blind:
        return CompanyLine(
            symbol=membership.symbol,
            company_name=name,
            coverage_tier=tier_name,
            state="unable",
            detail=f"Could not evaluate reliably: {', '.join(sorted(blind))} unavailable.",
        )

    detail = "No meaningful change detected since your last review."
    if tier is CoverageTier.LIMITED:
        detail = (
            "No meaningful change detected in the sources currently available to us. "
            "Coverage for this company is limited."
        )
    return CompanyLine(
        symbol=membership.symbol,
        company_name=name,
        coverage_tier=tier_name,
        state="quiet",
        detail=detail,
    )


def _later(a: datetime | None, b: datetime | None) -> datetime | None:
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


def attention_order(review: Review) -> list[Attention]:
    """The attention levels present, in the order the engine ranked them."""
    return [a.attention for line in review.changed for a in line.assessments]
