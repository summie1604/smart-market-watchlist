"""When a later report contradicts one we already hold.

D29. An event carries a contradiction state and, when disputed, a link to the record
disputing it. **Both stay visible and neither is deleted.** A reader who was told
something days ago is owed the correction next to the original, not a quietly edited page.

Four deterministic gates decide it, and all four must pass:

1. the two events are the same company and the same identity bucket (D12);
2. the disputing evidence is **at least as authoritative** as the disputed, by the tier
   ordering in VISION §12 — a forum post can never dispute a filing;
3. the disputing evidence is later by publication time; and
4. the contradiction is **grounded** in the disputing source's own words (D24).

What may *propose* a contradiction is bounded, not the gates. A model may return a
structured claim that B disputes A, and this module will judge it; the proposer built
here is a curated cue vocabulary — the language a denial or a retraction is actually
written in — because it is deterministic, inspectable and available with no model call.
Neither proposer decides anything. A proposal that fails any gate is recorded as a
possible relationship and shown as *"possibly related; relationship not confirmed"*, the
same treatment D12 gives an AMBIGUOUS link.

**A dispute lowers confidence, not attention.** A contested report may still be the most
significant thing about a company; what changed is how sure we are. Nothing in this
module touches an attention level or a score.

Recall here will be low. Most corrections are quiet, and many disputes never reuse the
original's terms. That is the intended direction: a false contradiction destroys trust in
every verdict beside it, while a missed one leaves the record merely incomplete.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .linking import LINK_WINDOW
from .models import ContradictionState

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

    from .models import Event, Evidence

__all__ = [
    "Contradiction",
    "DisputeProposal",
    "judge_dispute",
    "propose_dispute",
]


@dataclass(frozen=True)
class DisputeProposal:
    """A claim that one event contradicts another. A proposal, never a verdict."""

    state: ContradictionState
    detail: str
    grounded_in: str
    """The words in the disputing source that the proposal rests on. Verbatim, so the
    reader can check the claim against the text rather than trusting the label."""


@dataclass(frozen=True)
class Contradiction:
    """The judged relationship, as it is stored and shown."""

    state: ContradictionState
    disputed_by: str
    """Event id of the later record. The link is what keeps both readable."""
    detail: str
    confirmed: bool
    """False when a gate failed: shown as a possible relationship, never as a fact."""


_DENIAL = re.compile(
    r"\b(denies|denied|denial|refutes|refuted|rejects the report|dismisses the report|"
    r"calls the report|no such (?:proposal|plan|deal|talks|discussion)|"
    r"not in talks|has not (?:signed|agreed|received)|contrary to (?:media )?reports|"
    r"clarifies|clarification)\b",
    re.IGNORECASE,
)
"""A later report saying the earlier one is wrong."""

_WITHDRAWAL = re.compile(
    r"\b(retracts|retracted|retraction|withdraws|withdrawn|corrects an earlier|"
    r"correction to an earlier|an earlier version of this (?:story|report))\b",
    re.IGNORECASE,
)
"""The source unsaying it. Narrower than a denial, and it is a different state."""


def propose_dispute(evidence_list: Iterable[Evidence]) -> DisputeProposal | None:
    """Read a source's own words for language of denial or retraction.

    Grounding is the point: the phrase must appear in the disputing source's text, and
    the phrase we matched is carried on the proposal so the claim can be checked. Text
    that never says anything of the kind proposes nothing, which is the common case.

    Takes evidence rather than an event so the pipeline can ask *before* deciding
    identity. A denial is not another report of the story it denies, and letting it merge
    into that story would hide the disagreement inside the record of the claim.
    """
    for evidence in evidence_list:
        text = f"{evidence.title} {evidence.body}"
        withdrawal = _WITHDRAWAL.search(text)
        if withdrawal is not None:
            return DisputeProposal(
                state=ContradictionState.WITHDRAWN,
                detail=f"{evidence.publisher} retracted or corrected this report.",
                grounded_in=withdrawal.group(0),
            )
        denial = _DENIAL.search(text)
        if denial is not None:
            return DisputeProposal(
                state=ContradictionState.DISPUTED,
                detail=f"{evidence.publisher} reports this being denied or disputed.",
                grounded_in=denial.group(0),
            )
    return None


def judge_dispute(
    earlier: Event, later: Event, proposal: DisputeProposal | None
) -> Contradiction | None:
    """Run the gates. ``None`` when there is nothing to record at all.

    A returned contradiction with ``confirmed=False`` is a *possible* relationship: the
    proposal was made and a gate refused it. Recording it is deliberate — the reader sees
    that two records may be about the same disagreement without being told they are.
    """
    if proposal is None or earlier.event_id == later.event_id:
        return None

    failure = _gate_failure(earlier, later)
    if failure is None:
        return Contradiction(
            state=proposal.state,
            disputed_by=later.event_id,
            detail=f'{proposal.detail} Grounded in: "{proposal.grounded_in}".',
            confirmed=True,
        )
    return Contradiction(
        state=ContradictionState.STANDING,
        disputed_by=later.event_id,
        detail=f"Possibly related; relationship not confirmed ({failure}).",
        confirmed=False,
    )


def _gate_failure(earlier: Event, later: Event) -> str | None:
    """The first gate that refuses, in the reader's language. ``None`` when all pass."""
    if earlier.security_symbol != later.security_symbol:
        return "a different company"
    if earlier.event_type != later.event_type:
        return "a different kind of event"
    if not (
        earlier.occurred_at - LINK_WINDOW <= later.occurred_at <= earlier.occurred_at + LINK_WINDOW
    ):
        return "too far apart in time to be the same occurrence"
    if _published(later) <= _published(earlier):
        return "not published after the report it would dispute"
    if _authority(later) < _authority(earlier):
        return "a less authoritative source than the report it would dispute"
    return None


def _published(event: Event) -> datetime:
    """The latest publication time across an event's evidence."""
    return max(e.published_at for e in event.evidence)


def _authority(event: Event) -> int:
    """The strongest tier backing an event. Tier values are ordered by design."""
    return max(e.tier.value for e in event.evidence)
