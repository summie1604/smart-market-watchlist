"""Grouping attention items for presentation: several records, one development.

Attention is scarce, which is the product's whole argument. Three cards saying nearly the
same thing spend it badly even when all three records are individually correct — so this
groups them *for display* while leaving every record exactly as the engine produced it
(D43).

**This is not event identity.** D12 decides whether two reports are the same occurrence
and merges their evidence, and it is deliberately strict: a false merge corrupts
corroboration and provenance invisibly, so it refuses to link across event types. This is
a weaker, reversible claim — *"a reader looking at these would say it was one story"* —
and because nothing is merged, deleted or rescored, being wrong here costs a collapsed
card that expands, not a corrupted record.

The relation is D12's own, reused rather than reinvented:

    same company
    + within D12's link window
    + title similarity at or above D12's calibrated link threshold

What it drops is the event-type bucket, and that is the entire point. The three RELIANCE
records that prompted this were classified `Agreements`, `Acquisition` and `Outcome of
Board Meeting` — three buckets, so D12 could never consider them, while a reader sees one
announcement reported three ways. The lexical evidence D12 already trusts to establish
identity *within* a bucket is enough to justify sitting them on one card *across* buckets.

Candidates are compared against a group's primary rather than any member, so similarity
cannot chain: A grouping with B and B with C does not drag in a C that is unlike A.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .linking import LINK_WINDOW, TITLE_SIMILARITY_LINK, title_similarity

if TYPE_CHECKING:
    from .models import Assessment

__all__ = ["development_ids"]


def development_ids(ordered: list[Assessment]) -> dict[str, str]:
    """Map each assessment's event id to the id of the development it belongs to.

    ``ordered`` must already be in canonical order (D26). The first member of a group is
    therefore its primary, which means presentation reuses the backend's single ranking
    answer rather than inventing a second one.

    An assessment that groups with nothing maps to itself, so every item has a development
    id and the caller never has to special-case the ungrouped case.
    """
    primaries: list[Assessment] = []
    assigned: dict[str, str] = {}

    for assessment in ordered:
        primary = next((p for p in primaries if _same_development(p, assessment)), None)
        if primary is None:
            primaries.append(assessment)
            assigned[assessment.event.event_id] = assessment.event.event_id
        else:
            assigned[assessment.event.event_id] = primary.event.event_id
    return assigned


def _same_development(primary: Assessment, candidate: Assessment) -> bool:
    """Whether a reader would call these one development.

    Company first because it is the cheapest and the most important: grouping across
    companies would be the one error that makes the board actively misleading.
    """
    left, right = primary.event, candidate.event
    if left.security_symbol != right.security_symbol:
        return False
    if abs(left.occurred_at - right.occurred_at) > LINK_WINDOW:
        return False
    return title_similarity(left.description, right.description) >= TITLE_SIMILARITY_LINK
