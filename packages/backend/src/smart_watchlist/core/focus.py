"""What a user said they were watching for, and whether an event matches it.

Interests **filter and annotate. They never score** (D27). Nothing in this module reads
or returns an attention level, a confidence, a corroboration count or a position in the
canonical order. Two users with opposite interests see the same severities for the same
company, which is what lets one analysis serve everyone.

The mapping is curated and inspectable, like the company aliases in ``context``. It is
never inferred per user and never decided by a model: an annotation that says *why* an
item matched has to be something we can show, and a learned match is a match we cannot
explain.

Matching is token-bounded rather than substring — "cci" must not match "accident" — and
runs over the event type, the description and the evidence categories, all of which are
either the engine's own classification or text already grounded in the source (D24).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Assessment

__all__ = [
    "FOCUS_TAGS",
    "FocusMatch",
    "FocusTag",
    "known_tags",
    "matches_focus",
    "normalise_tags",
]


@dataclass(frozen=True)
class FocusTag:
    """One thing a user can say they are watching for."""

    tag: str
    label: str
    terms: tuple[str, ...]
    """Curated terms. A match on any of them is a match on the tag."""
    because: str
    """How the match is explained to the reader, in the reader's language."""


FOCUS_TAGS: tuple[FocusTag, ...] = (
    FocusTag(
        tag="earnings",
        label="Earnings and results",
        terms=(
            "result",
            "results",
            "earnings",
            "profit",
            "loss",
            "revenue",
            "quarterly",
            "guidance",
            "margin",
        ),
        because="reports on results or earnings",
    ),
    FocusTag(
        tag="management",
        label="Management changes",
        terms=(
            "director",
            "directors",
            "managerial",
            "ceo",
            "cfo",
            "chairman",
            "board",
            "resigns",
            "resignation",
            "appoints",
            "appointment",
            "steps",
        ),
        because="concerns the board or senior management",
    ),
    FocusTag(
        tag="regulation",
        label="Regulatory and legal",
        terms=(
            "regulatory",
            "regulator",
            "sebi",
            "rbi",
            "cci",
            "trai",
            "probe",
            "investigation",
            "penalty",
            "legal",
            "court",
            "tribunal",
            "nclt",
            "lawsuit",
            "verdict",
            "compliance",
        ),
        because="involves a regulator or a legal process",
    ),
    FocusTag(
        tag="competitors",
        label="Competitive moves",
        terms=(
            "merger",
            "amalgamation",
            "demerger",
            "acquisition",
            "acquire",
            "acquires",
            "takeover",
            "stake",
            "divestment",
            "joint",
            "venture",
        ),
        because="changes who the company competes with or owns",
    ),
    FocusTag(
        tag="contracts",
        label="Contracts and orders",
        terms=(
            "contract",
            "contracts",
            "order",
            "orders",
            "agreement",
            "agreements",
            "deal",
            "partnership",
            "mou",
            "awarded",
            "tender",
        ),
        because="reports a contract, order or agreement",
    ),
    FocusTag(
        tag="commodities",
        label="Commodity and input costs",
        terms=(
            "crude",
            "oil",
            "gas",
            "aluminium",
            "aluminum",
            "copper",
            "steel",
            "coal",
            "commodity",
            "commodities",
            "refining",
            "refinery",
            "tariff",
            "tariffs",
        ),
        because="turns on commodity or input costs",
    ),
    FocusTag(
        tag="dividends",
        label="Dividends and buybacks",
        terms=(
            "dividend",
            "dividends",
            "buyback",
            "bonus",
            "split",
            "payout",
            "record",
        ),
        because="affects a payout to shareholders",
    ),
    FocusTag(
        tag="price",
        label="Unusual price movement",
        terms=(
            "unusual",
            "movement",
            "volume",
            "price",
            "corporate",
            "action",
        ),
        because="is a movement observed in the market itself",
    ),
)
"""The vocabulary, fixed. Free text would match how people actually describe what they
watch, but nothing deterministic could then explain the match — so the free-text answers
a user gives are kept for their own reference and to inform later curation of this list,
not parsed into behaviour."""

_TERM_PATTERNS: dict[str, re.Pattern[str]] = {
    tag.tag: re.compile(r"\b(?:" + "|".join(re.escape(t) for t in tag.terms) + r")\b", re.I)
    for tag in FOCUS_TAGS
}


@dataclass(frozen=True)
class FocusMatch:
    """One reason an event is relevant to something the user said they watch for."""

    tag: str
    label: str
    why: str


def known_tags() -> tuple[str, ...]:
    return tuple(tag.tag for tag in FOCUS_TAGS)


def normalise_tags(raw: object) -> tuple[str, ...]:
    """Accept what a client sent and keep only tags we actually have a mapping for.

    An unknown tag is dropped rather than stored: storing it would let the interface
    offer a filter that can never match, which reads as the system missing things.
    """
    if not isinstance(raw, (list, tuple)):
        return ()
    allowed = set(known_tags())
    seen: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        tag = item.strip().lower()
        if tag in allowed and tag not in seen:
            seen.append(tag)
    return tuple(seen)


def matches_focus(assessment: Assessment, tags: tuple[str, ...]) -> tuple[FocusMatch, ...]:
    """Which of this user's tags this event matches, and why.

    Empty when the user set no tags, and empty when nothing matched — an unmatched item
    is left unannotated rather than annotated with a guess.
    """
    if not tags:
        return ()
    event = assessment.event
    haystack = " ".join(
        (
            event.event_type,
            event.description,
            *(e.category for e in event.evidence),
        )
    )
    out: list[FocusMatch] = []
    for tag in FOCUS_TAGS:
        if tag.tag not in tags:
            continue
        if _TERM_PATTERNS[tag.tag].search(haystack):
            out.append(FocusMatch(tag=tag.tag, label=tag.label, why=f"{tag.label}: {tag.because}"))
    return tuple(out)
