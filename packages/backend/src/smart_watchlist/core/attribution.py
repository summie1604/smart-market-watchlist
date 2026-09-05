"""Company attribution — does this evidence support naming this company as the subject?

Domain logic, not an adapter concern. Retrieval context is a hint about where we looked;
it is never proof of who an article is about (D21), and deciding that question is the
same kind of judgement the engine makes everywhere else.

The rule, stated once: **a company must be named in the headline, inside the leading
clause, in a subject position.** Everything here fails closed, because a false attribution
is worse than a missed article: a missed article is absence, a false one is a claim about
a company that never made it.

Bounded and explainable on purpose. This is the floor the system keeps when no model is
available — a model can read a body and judge what a paragraph is about; these rules
cannot, and decline rather than guess.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .context import context_for

if TYPE_CHECKING:
    from .models import Evidence

__all__ = ["subject_rejection"]


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
