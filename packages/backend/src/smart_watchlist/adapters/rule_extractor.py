"""Deterministic extraction — the floor the system never falls below.

Not a mock. This runs in production whenever the language model is unavailable, rate
limited, or returning output that fails validation, which is what makes D5's "degrade
gracefully" real rather than aspirational: news keeps flowing into the domain, with a
plainly weaker reading of it.

It classifies from the headline vocabulary and extracts nothing it cannot see. Its
ceiling is low and its floor is solid — it never invents a counterparty, because it
never proposes one it did not read.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..core.extraction import ExtractedEvent

if TYPE_CHECKING:
    from ..core.models import Evidence

__all__ = ["EXTRACTOR_NAME", "RuleExtractor"]

EXTRACTOR_NAME = "rules/headline-vocabulary/v1"

_EVENT_VOCABULARY: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Agreements", ("partnership", "agreement", "deal", "pact", "mou", "tie-up", "signs")),
    ("Acquisition", ("acquire", "acquisition", "takeover", "buyout", "stake buy")),
    ("Amalgamation/ Merger", ("merger", "merge", "demerger", "demerge")),
    ("Contract Win", ("contract", "order win", "bags order", "wins order", "awarded")),
    ("Financial Result Updates", ("results", "profit", "revenue", "earnings", "quarterly")),
    ("Regulatory Action", ("sebi", "rbi", "cci", "regulator", "probe", "investigation", "penalty")),
    ("Legal", ("lawsuit", "court", "tribunal", "nclt", "verdict", "appeal")),
    (
        "Change in Directors/ Key Managerial Personnel",
        ("ceo", "cfo", "resigns", "appoints", "steps down"),
    ),
    ("Raising of Funds", ("ipo", "fundraise", "qip", "bond issue", "rights issue", "listing")),
    ("Credit Rating- Revision", ("rating", "downgrade", "upgrade")),
    ("Expansion", ("expansion", "plant", "capacity", "refinery", "facility", "invest")),
    ("Product Launch", ("launch", "launches", "unveils", "forays", "enters india", "rollout")),
    ("Divestment", ("stake sale", "reduce stake", "reduces stake", "divest", "sells stake")),
)

_SPECULATIVE = re.compile(
    r"\b(may|might|could|reportedly|rumou?r|in talks|considering|weighing|plans to|likely to|"
    r"sources said|said to be)\b",
    re.IGNORECASE,
)

_SECTOR_WIDE = re.compile(
    r"\b(sector|nifty|sensex|index|markets? (?:close|open|end)|top gainers|top losers|"
    r"stocks to watch|share price target|prediction)\b",
    re.IGNORECASE,
)

_MONEY = re.compile(
    r"(?:rs\.?|inr|usd|\$|₹)\s?[\d,.]+\s?(?:crore|cr|lakh|billion|bn|million|mn|trillion)?",
    re.IGNORECASE,
)


class RuleExtractor:
    """Implements ``Extractor``. Never raises, never invents, never guesses the subject."""

    name = EXTRACTOR_NAME

    def __init__(self) -> None:
        self.last_rejection: str | None = None
        """Why the most recent article produced nothing. Observable and provenanced."""

    def extract(self, evidence: Evidence) -> ExtractedEvent | None:
        self.last_rejection = None
        text = f"{evidence.title} {evidence.body}"

        rejection = subject_rejection(evidence)
        if rejection is not None:
            self.last_rejection = rejection
            return None

        event_type = _classify(text.lower())
        if event_type is None:
            self.last_rejection = "no-recognisable-event-type"
            return None

        money = _MONEY.search(text)
        return ExtractedEvent(
            subject_company=evidence.subject_company,
            event_type=event_type,
            description=evidence.title,
            occurred_at=evidence.published_at,
            contract_value=money.group(0).strip() if money else None,
            is_speculative=bool(_SPECULATIVE.search(text)),
            concerns_subject=True,
            missing=("counterparties", "geographies", "products", "regulator"),
        )


def _classify(lowered: str) -> str | None:
    for event_type, keywords in _EVENT_VOCABULARY:
        if any(keyword in lowered for keyword in keywords):
            return event_type
    return None


# --- deterministic subject grounding -------------------------------------------

# En and em dashes are matched by codepoint: real headlines use both, and the
# literal characters trip the ambiguous-unicode lint.
_CLAUSE_SEPARATORS = re.compile("\\s*[:;|]\\s*|\\s+[-\u2013\u2014]\\s+")
"""Where a headline stops naming its subject and starts commenting.

Everything after the first of these is context: "Stocks to watch: Reliance, Wipro" is a
list, and "Kwality Wall's, Vadilal: why ice cream stocks fell after Reliance entry" is
about the companies named before the colon.
"""

_COUNTERPARTY_PREPOSITIONS = frozenset(
    {
        "from",
        "to",
        "with",
        "by",
        "for",
        "at",
        "after",
        "against",
        "than",
        "vs",
        "versus",
        "of",
        "over",
        "amid",
        "on",
    }
)
"""A name in this position is the other party, not the subject: "…order from Reliance"."""

_INCIDENTAL_QUALIFIERS = frozenset(
    {
        "supplier",
        "suppliers",
        "competitor",
        "competitors",
        "rival",
        "rivals",
        "peer",
        "peers",
        "backed",
        "owned",
        "led",
        "arm",
        "unit",
        "subsidiary",
        "partner",
    }
)
"""Words that make a nearby company name a relationship rather than a subject."""

_TRAILING_QUALIFIERS = re.compile(r"-(backed|owned|led|linked|controlled)\b", re.IGNORECASE)

_ROUNDUP = re.compile(
    r"\b(stocks? to watch|top gainers|top losers|market(s)? (close|open|end|live|roundup)|"
    r"sensex|nifty|share price target)\b",
    re.IGNORECASE,
)


def subject_rejection(evidence: Evidence) -> str | None:
    """Why this article cannot be attributed to the watched company — or ``None``.

    The rule, stated once: **the company must be named in the headline, in the leading
    clause, in a subject position.** Retrieval context is a hint about where we looked,
    never proof of who the article is about (D21).

    Body-only mentions are refused deliberately. A bounded rule cannot judge what a
    paragraph is about, and the honest response to that is to decline rather than to
    guess. Gemini handles those when it is available; this is the floor, not the ceiling.
    """
    from ..core.context import context_for

    context = context_for(evidence.security_symbol, evidence.subject_company)
    aliases = [a for a in context.aliases if a.strip()]
    headline = evidence.title

    if _ROUNDUP.search(headline):
        return "market-roundup-not-a-company-event"

    leading = _CLAUSE_SEPARATORS.split(headline, maxsplit=1)[0]

    found = _find_alias(leading, aliases)
    if found is None:
        # Named later in the headline, or only in the body — either way the leading clause
        # is about something else.
        return (
            "subject-named-outside-leading-clause"
            if _find_alias(headline, aliases) is not None
            else "subject-not-named-in-headline"
        )

    start, end = found
    if _TRAILING_QUALIFIERS.match(leading[end:]):
        return "subject-named-as-a-relationship"

    preceding = re.findall(r"[A-Za-z']+", leading[:start].lower())
    window = preceding[-2:]
    if any(word in _COUNTERPARTY_PREPOSITIONS for word in window):
        return "subject-named-as-counterparty"
    if any(word in _INCIDENTAL_QUALIFIERS for word in window):
        return "subject-named-as-a-relationship"

    return None


def _find_alias(text: str, aliases: list[str]) -> tuple[int, int] | None:
    """Locate the longest matching alias on token boundaries.

    Longest first so "Reliance Industries" is preferred over "Reliance", and bounded by
    ``\b`` so "Relianceable" is not a match.
    """
    for alias in sorted(aliases, key=len, reverse=True):
        match = re.search(rf"\b{re.escape(alias)}\b", text, re.IGNORECASE)
        if match is not None:
            return match.start(), match.end()
    return None
