"""Event identity — D12, implemented conservatively.

The bucket generates candidates. It is not identity.

    (company, event_type, temporal window)  →  candidates
      → structured attribute comparison
      → bounded lexical similarity
      → LINK | CREATE_NEW | AMBIGUOUS

**False merges are more damaging than temporary duplicates.** A duplicate makes the
review slightly noisier and can be reconciled later. A false merge corrupts lifecycle
state, corroboration counts and provenance *invisibly* — the merged event looks
perfectly coherent afterwards. So when the structured evidence is insufficient, this
prefers CREATE_NEW or AMBIGUOUS.

AMBIGUOUS holds the *merge*, not the event: both events stay visible and a possible
relationship is recorded between them. Uncertainty reduces what the system claims; it
never suppresses evidence.

No embeddings. A merge the system cannot explain is as bad as a ranking it cannot
explain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .extraction import ExtractedEvent
    from .models import Event

__all__ = ["LINK_WINDOW", "LinkDecision", "LinkOutcome", "decide_link"]

LINK_WINDOW = timedelta(days=4)
"""How far back a candidate may reach. A developing story spans days; beyond this the
same company and type is more likely a second occurrence than the same one."""

_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "its",
        "has",
        "have",
        "will",
        "after",
        "over",
        "into",
        "amid",
        "says",
        "said",
        "new",
        "plans",
        "may",
        "arm",
        "unit",
        "ltd",
        "limited",
    }
)
_WORD = re.compile(r"[a-z0-9]+")

_TITLE_SIMILARITY_LINK = 0.5
"""Above this, and with no attribute conflict, two reports describe one occurrence.

Calibrated against real multi-publisher coverage rather than chosen: two outlets
reporting the same Consob approval scored 0.57, while two genuinely different same-day
Tata Motors events scored 0.13. The threshold sits in that gap, nearer the lower end
because the conflict check above already removes the dangerous merges."""

_TITLE_SIMILARITY_AMBIGUOUS = 0.3
"""Between the two, the relationship is possible but unproven — recorded, not asserted."""


class LinkOutcome(Enum):
    LINK = "LINK"
    CREATE_NEW = "CREATE_NEW"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class LinkDecision:
    """The outcome, the event it concerns, and why — explainable by construction."""

    outcome: LinkOutcome
    event_id: str | None
    reason: str
    similarity: float = 0.0

    @property
    def possible_relationship(self) -> str | None:
        """User-facing wording for an unproven relationship."""
        if self.outcome is not LinkOutcome.AMBIGUOUS:
            return None
        return "Possibly related to an earlier event; relationship not yet confirmed."


def decide_link(
    proposal: ExtractedEvent,
    candidates: list[tuple[Event, ExtractedEvent | None]],
) -> LinkDecision:
    """Decide whether this proposal continues an existing event.

    ``candidates`` are events already bucketed by company, type and window. Each is
    paired with its own extraction where one exists, so structured attributes can be
    compared rather than only headlines.
    """
    if not candidates:
        return LinkDecision(LinkOutcome.CREATE_NEW, None, "No existing event in the window.")

    best: tuple[float, Event, str] | None = None
    for event, extracted in candidates:
        conflict = _attribute_conflict(proposal, extracted)
        if conflict is not None:
            continue  # a contradicted attribute rules this candidate out entirely
        similarity = _similarity(proposal.description, event.description)
        if best is None or similarity > best[0]:
            best = (similarity, event, _attribute_support(proposal, extracted))

    if best is None:
        return LinkDecision(
            LinkOutcome.CREATE_NEW,
            None,
            "Every candidate conflicts on a structured attribute — a different occurrence.",
        )

    similarity, event, support = best
    if similarity >= _TITLE_SIMILARITY_LINK:
        return LinkDecision(
            LinkOutcome.LINK,
            event.event_id,
            f"Same company, type and window; {support}descriptions overlap strongly.",
            similarity,
        )
    if similarity >= _TITLE_SIMILARITY_AMBIGUOUS:
        return LinkDecision(
            LinkOutcome.AMBIGUOUS,
            event.event_id,
            f"Same company, type and window, but {support}the evidence does not "
            "establish these are one occurrence.",
            similarity,
        )
    return LinkDecision(
        LinkOutcome.CREATE_NEW,
        None,
        "Descriptions share too little to treat as one occurrence.",
        similarity,
    )


def _attribute_conflict(proposal: ExtractedEvent, other: ExtractedEvent | None) -> str | None:
    """A structured attribute that contradicts, which is decisive evidence of difference.

    Two contracts on the same day with different counterparties are two events, however
    similar their headlines read. This is the check that stops the same-day merge.
    """
    if other is None:
        return None
    for name in ("counterparties", "products", "geographies"):
        mine = {v.lower() for v in getattr(proposal, name)}
        theirs = {v.lower() for v in getattr(other, name)}
        if mine and theirs and not (mine & theirs):
            return name
    if proposal.regulator and other.regulator and proposal.regulator != other.regulator:
        return "regulator"
    if (
        proposal.contract_value
        and other.contract_value
        and _digits(proposal.contract_value) != _digits(other.contract_value)
    ):
        return "contract_value"
    return None


def _attribute_support(proposal: ExtractedEvent, other: ExtractedEvent | None) -> str:
    if other is None:
        return ""
    for name in ("counterparties", "products", "geographies"):
        mine = {v.lower() for v in getattr(proposal, name)}
        theirs = {v.lower() for v in getattr(other, name)}
        if mine & theirs:
            return f"shared {name.rstrip('s')}, and "
    return ""


def _similarity(left: str, right: str) -> float:
    """Bounded lexical overlap — Jaccard over meaningful words.

    Deliberately simple and inspectable. It is a tiebreaker between candidates that
    already share company, type and window, not a semantic model.
    """
    a, b = _significant(left), _significant(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _significant(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if len(w) > 2 and w not in _STOPWORDS}


def _digits(value: str) -> str:
    return "".join(c for c in value if c.isdigit())
