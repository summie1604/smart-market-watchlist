"""The bounded explainer: "ask about this company", answered only from the record.

**Not a chat box.** VISION §17 refuses natural-language querying because the intelligence
must live in the evaluation, not in a conversation about it. This module is the narrow
thing that is still worth having: a reader looking at one company can ask why it is on
their screen, and get the *stored* answer back in a sentence instead of having to read a
reason-code ledger (D35).

Three properties make that safe, and all three are structural rather than promised:

*Nothing here generates prose from outside the record.* Every statement is composed from
persisted assessments, reason codes, coverage records and evidence refs that the API
already serves. There is no model in this path, so there is nothing that could invent a
counterparty, a price, a cause or a recommendation — the failure mode is a missing answer,
never a fabricated one.

*Every statement carries the events it came from.* A sentence that cannot name its
evidence is not emitted. That is the rule the engine applies to attention levels (D4),
applied to prose.

*Advice is refused before anything is looked up.* "Should I buy" is not a question with a
weak answer; it is a question this product does not answer at all (§6, §17). Resolving it
first means the refusal cannot be softened by whatever the records happen to say.

Pure and I/O-free, like the rest of ``core``. The caller supplies the window, the records
and the coverage; nothing here reads a clock, a database or a network — which is what
makes "a question never triggers ingestion or external browsing" a property of the
architecture rather than a rule someone has to remember.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from .corroboration import assess_corroboration
from .models import Attention, ContradictionState

if TYPE_CHECKING:
    from datetime import datetime

    from .models import Assessment, Coverage

__all__ = [
    "COMPANY_INTENTS",
    "DISCLAIMER",
    "GENERATED_BY",
    "SUGGESTIONS",
    "WATCHLIST_INTENTS",
    "WATCHLIST_SUGGESTIONS",
    "Answer",
    "Intent",
    "Statement",
    "WatchlistFacts",
    "Window",
    "explain",
    "explain_watchlist",
    "resolve_intent",
]

GENERATED_BY = "deterministic/explainer/v1"
"""Provenance for the answer path itself.

Recorded on every response so a reader — and a later reviewer — can tell how an answer was
produced. If a model-phrased variant is ever added behind this contract it names itself
here, and the two are never confused (D35).
"""

DISCLAIMER = (
    "This explains what we have recorded about this company. "
    "It is not investment advice, and it makes no claim about what the price will do."
)


class Intent(Enum):
    """The bounded set of questions this explainer answers.

    Bounded on purpose. An intent that cannot be answered from stored records has no
    business being recognised, because recognising it promises an answer the record
    cannot support.
    """

    WHAT_CHANGED = "what_changed"
    WHY_ATTENTION = "why_attention"
    COVERAGE = "coverage"
    CORROBORATION = "corroboration"
    PRICE_CONTEXT = "price_context"
    CONTRADICTION = "contradiction"
    DISCLOSURES = "disclosures"
    """Filings specifically, as opposed to ``COVERAGE`` which is about what we could not
    consult. "Any important disclosures?" and "what could you not see?" are different
    questions and returning one for the other would be quietly wrong."""
    EXPLAIN_SIMPLE = "explain_simple"
    WATCHLIST_ATTENTION = "watchlist_attention"
    BIGGEST_MOVERS = "biggest_movers"
    ALERTS = "alerts"
    OUT_OF_SCOPE_ADVICE = "out_of_scope_advice"
    """Recognised so it can be refused explicitly, never so it can be answered."""
    UNSUPPORTED = "unsupported"


SUGGESTIONS: tuple[str, ...] = (
    "What changed recently?",
    "Why does this need my attention?",
    "What could you not see?",
    "How many independent sources reported this?",
    "What did the market do?",
    "Has anything been disputed?",
)
"""Offered whenever a company question falls outside the set, so a refusal is useful."""

WATCHLIST_SUGGESTIONS: tuple[str, ...] = (
    "What needs my attention?",
    "What are my biggest movers?",
    "Any important new disclosures?",
    "What alerts have triggered?",
)
"""The same, for a question asked with no company in view."""

# Advice and prediction are matched first and refused outright. A question about what to
# do with a holding is not a weak question — it is one this product does not answer (§6).
_ADVICE = re.compile(
    r"\b(should i|shall i|do i|would you|can you recommend|recommend|advice|advise|"
    r"buy|sell|hold|short|invest|entry|exit|target price|price target|fair value|"
    r"undervalued|overvalued|worth buying|worth holding|"
    r"will (?:it|the price|this) (?:go|rise|fall|drop|climb|reach)|"
    r"forecast|predict|prediction|good stock|bad stock)\b",
    re.IGNORECASE,
)

_PATTERNS: tuple[tuple[Intent, re.Pattern[str]], ...] = (
    (
        Intent.EXPLAIN_SIMPLE,
        re.compile(
            r"\b(simpl\w*|plain english|plainly|layman|beginner|eli5|in short|briefly)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Intent.ALERTS,
        re.compile(
            r"\b(alert|alerts|watch ?point\w*|triggered|my level\w*|threshold\w*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Intent.BIGGEST_MOVERS,
        re.compile(
            r"\b(biggest|largest|top) (mover|movers|gainer|gainers|loser|losers|rise|fall)\w*"
            r"|\bmovers\b|\bwho (?:moved|gained|fell) most\b",
            re.IGNORECASE,
        ),
    ),
    (
        Intent.WATCHLIST_ATTENTION,
        re.compile(
            # Anchored on "what/which/who", so "why does *this* need my attention" stays a
            # question about the company in view rather than about the whole list.
            r"\b(?:what|which|who|anything)\b[^?]{0,40}?"
            r"\b(?:needs?|deserves?|wants?)\b[^?]{0,20}?\battention\b"
            r"|\bwhat should i look at\b|\bmy watchlist\b|\bacross my watchlist\b",
            re.IGNORECASE,
        ),
    ),
    (
        Intent.DISCLOSURES,
        re.compile(
            r"\b(disclosure\w*|filing\w*|filed|exchange announcement\w*|"
            r"regulatory (?:filing|announcement)\w*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Intent.CONTRADICTION,
        re.compile(
            r"\b(disput|contradict|denied|denial|retract|withdraw|conflict|is it true|"
            r"reliable)\w*",
            re.IGNORECASE,
        ),
    ),
    (
        Intent.COVERAGE,
        re.compile(
            r"\b(?:coverage|missing|gap|blind|unavailable|not checked|limitation)\w*"
            r"|\b(?:could|couldn'?t)\s+(?:you\s+)?(?:not\s+)?see\b"
            r"|\bwhat\s+don'?t\s+you\s+know\b",
            re.IGNORECASE,
        ),
    ),
    (
        Intent.CORROBORATION,
        re.compile(
            r"\b(corroborat|independent|how many source|who reported|which publisher|"
            r"publisher|outlet|confirmed by|sourc)\w*",
            re.IGNORECASE,
        ),
    ),
    (
        Intent.PRICE_CONTEXT,
        re.compile(
            r"\b(price|share|stock move|moved|movement|market|sector|index|volume|"
            r"trading|close|split|dividend)\w*",
            re.IGNORECASE,
        ),
    ),
    (
        Intent.WHY_ATTENTION,
        re.compile(
            r"\b(why|reason|matter|important|significan|attention|flagged|surfaced|"
            r"high|explain)\w*",
            re.IGNORECASE,
        ),
    ),
    (
        Intent.WHAT_CHANGED,
        re.compile(
            r"\b(what|chang|happen|new|recent|latest|update|news|since|going on|"
            r"summar)\w*",
            re.IGNORECASE,
        ),
    ),
)


def resolve_intent(question: str) -> Intent:
    """Which bounded question this is, if any.

    Advice is tested first so it cannot be reclassified by a later pattern: *"should I buy
    given the results?"* mentions results, and answering it would be answering the wrong
    half of the sentence.

    Order among the rest runs from most specific to most general. A question about a
    disputed report also contains the word "reported"; the narrower reading is the one the
    reader meant.
    """
    text = question.strip()
    if not text:
        return Intent.UNSUPPORTED
    if _ADVICE.search(text):
        return Intent.OUT_OF_SCOPE_ADVICE
    for intent, pattern in _PATTERNS:
        if pattern.search(text):
            return intent
    return Intent.UNSUPPORTED


@dataclass(frozen=True)
class Window:
    """The evidence window an answer speaks for. Stated on every response."""

    start: datetime | None
    """The reader's last completed review, or ``None`` when they have completed none."""
    end: datetime
    basis: str
    """In the reader's words: what the window means, not how it was computed."""
    considered: int


@dataclass(frozen=True)
class Statement:
    """One factual sentence and the records behind it.

    ``event_ids`` is empty only for statements about this explainer's own limits — a
    refusal, or a pointer to the suggestions. A sentence about the *world* that cannot
    name the events it rests on is never emitted.
    """

    text: str
    event_ids: tuple[str, ...]


@dataclass(frozen=True)
class Answer:
    intent: Intent
    answered: bool
    statements: tuple[Statement, ...] = ()
    insufficient_reason: str | None = None
    """``no-evidence`` · ``no-record-of-that`` · ``out-of-scope`` · ``unsupported``."""
    cited_event_ids: tuple[str, ...] = field(default=())


def explain(
    *,
    intent: Intent,
    company: str,
    window: Window,
    in_window: list[Assessment],
    everything: list[Assessment],
    coverage: Coverage,
) -> Answer:
    """Compose an answer from stored records, or decline.

    ``in_window`` is what arrived since the reader's last completed review; ``everything``
    is the whole record we hold for this company. Both arrive already filtered and already
    ordered — this module never re-ranks, because canonical order is the backend's single
    answer to a product question (D26) and an explainer is not a second one.
    """
    if intent in WATCHLIST_INTENTS:
        # Asked with a company in view but answerable only across the watchlist. Rather
        # than guessing, the caller is told which scope the question belongs to.
        return Answer(
            intent=intent,
            answered=False,
            insufficient_reason="wrong-scope",
            statements=(
                Statement(
                    "That is a question about your whole watchlist. Ask it from the "
                    "watchlist and I can answer it there.",
                    (),
                ),
            ),
        )

    if intent is Intent.OUT_OF_SCOPE_ADVICE:
        return Answer(
            intent=intent,
            answered=False,
            insufficient_reason="out-of-scope",
            statements=(
                Statement(
                    "This product reports what changed and how confident we are. It does "
                    "not give buy, sell or hold advice, and it does not predict prices.",
                    (),
                ),
            ),
        )

    if intent is Intent.UNSUPPORTED:
        return Answer(
            intent=intent,
            answered=False,
            insufficient_reason="unsupported",
            statements=(
                Statement(
                    "I can only answer from what we have already assessed for this "
                    "company. Try one of the questions below.",
                    (),
                ),
            ),
        )

    if not everything:
        return Answer(
            intent=intent,
            answered=False,
            insufficient_reason="no-evidence",
            statements=(
                Statement(
                    f"I don't have enough evidence: nothing has been assessed for {company} yet.",
                    (),
                ),
            ),
        )

    builders = {
        Intent.WHAT_CHANGED: _what_changed,
        Intent.WHY_ATTENTION: _why_attention,
        Intent.COVERAGE: _coverage,
        Intent.CORROBORATION: _corroboration,
        Intent.PRICE_CONTEXT: _price_context,
        Intent.CONTRADICTION: _contradiction,
        Intent.DISCLOSURES: _disclosures,
        Intent.EXPLAIN_SIMPLE: _explain_simple,
    }
    statements = builders[intent](company, window, in_window, everything, coverage)

    if not statements:
        return Answer(
            intent=intent,
            answered=False,
            insufficient_reason="no-record-of-that",
            statements=(
                Statement(
                    f"I don't have enough evidence to answer that from what we hold for {company}.",
                    (),
                ),
            ),
        )

    return Answer(
        intent=intent,
        answered=True,
        statements=tuple(statements),
        cited_event_ids=tuple(dict.fromkeys(i for s in statements for i in s.event_ids)),
    )


# --- the answers ---------------------------------------------------------------
#
# Each builder returns statements or nothing. Returning nothing is a supported outcome and
# becomes "I don't have enough evidence" above; no builder invents a sentence to avoid an
# empty result.


def _what_changed(
    company: str,
    window: Window,
    in_window: list[Assessment],
    everything: list[Assessment],
    coverage: Coverage,
) -> list[Statement]:
    if in_window:
        lead = Statement(
            f"{len(in_window)} development{'s' if len(in_window) != 1 else ''} "
            f"{'were' if len(in_window) != 1 else 'was'} assessed for {company} "
            f"{window.basis}.",
            tuple(a.event.event_id for a in in_window),
        )
        return [lead, *(_development(a) for a in in_window[:5])]

    latest = everything[0]
    return [
        Statement(
            f"Nothing new was assessed for {company} {window.basis}. The most recent "
            "development we hold is below.",
            (latest.event.event_id,),
        ),
        _development(latest),
    ]


def _development(a: Assessment) -> Statement:
    """One development, in the engine's own terms. Nothing here re-judges it."""
    corroboration = assess_corroboration(a.event.evidence)
    return Statement(
        f"{a.attention.value.replace('_', ' ').lower()}, "
        f"{a.confidence.value.lower()} confidence — {a.event.description} "
        f"({a.event.event_type}, {corroboration.summary}).",
        (a.event.event_id,),
    )


def _why_attention(
    company: str,
    window: Window,
    in_window: list[Assessment],
    everything: list[Assessment],
    coverage: Coverage,
) -> list[Statement]:
    """The reason codes, verbatim. They *are* the decision, not a commentary on it."""
    ranked = in_window or everything
    subject = next(
        (a for a in ranked if a.attention in (Attention.HIGH, Attention.MEDIUM)),
        ranked[0],
    )
    if not subject.reasons:
        return []

    statements = [
        Statement(
            f"{subject.event.description} was assessed "
            f"{subject.attention.value.replace('_', ' ').lower()} with "
            f"{subject.confidence.value.lower()} confidence, by scoring version "
            f"{subject.scoring_version}.",
            (subject.event.event_id,),
        )
    ]
    for reason in subject.reasons:
        direction = "counted towards" if reason.direction == "+" else "counted against"
        statements.append(
            Statement(f"{reason.detail} ({direction} attention).", (subject.event.event_id,))
        )
    return statements


def _coverage(
    company: str,
    window: Window,
    in_window: list[Assessment],
    everything: list[Assessment],
    coverage: Coverage,
) -> list[Statement]:
    """What we could not consult. The one answer that must never be silent (D15)."""
    ids = tuple(a.event.event_id for a in everything[:5])
    if coverage.is_complete:
        consulted = ", ".join(sorted({r.source for r in coverage.records}))
        return [
            Statement(
                "Every source family was consulted successfully on its most recent run: "
                f"{consulted}.",
                ids,
            )
        ]
    return [
        Statement(
            "These sources could not be consulted, so anything they would have shown is "
            "missing from what you see:",
            ids,
        ),
        *(
            Statement(f"{r.source} — {r.status.value.lower()}. {r.detail}".strip(), ids)
            for r in coverage.missing
        ),
    ]


def _corroboration(
    company: str,
    window: Window,
    in_window: list[Assessment],
    everything: list[Assessment],
    coverage: Coverage,
) -> list[Statement]:
    """Independent publishers, never article count (D13)."""
    statements: list[Statement] = []
    for a in (in_window or everything)[:3]:
        corroboration = assess_corroboration(a.event.evidence)
        publishers = sorted({e.publisher for e in a.event.evidence if e.publisher})
        detail = f"{a.event.description} — {corroboration.summary}"
        if publishers:
            detail += f", from {', '.join(publishers)}"
        if corroboration.article_count > corroboration.independent_source_count:
            detail += ". Some of those reports share a newsroom, so they count once"
        statements.append(Statement(detail + ".", (a.event.event_id,)))
    return statements


def _price_context(
    company: str,
    window: Window,
    in_window: list[Assessment],
    everything: list[Assessment],
    coverage: Coverage,
) -> list[Statement]:
    """Market observations already stored — never a fresh quote.

    A question must not reach a market feed, so this reads persisted observations and
    nothing else. When none are stored, the honest answer is that we hold none, which the
    caller turns into "I don't have enough evidence" rather than into a number.
    """
    observed = [a for a in everything if any(e.source == "market" for e in a.event.evidence)]
    if not observed:
        return []
    return [
        Statement(
            "From market observations we have already recorded — stored end-of-day data, "
            "not a live quote:",
            tuple(a.event.event_id for a in observed[:3]),
        ),
        *(_development(a) for a in observed[:3]),
    ]


def _contradiction(
    company: str,
    window: Window,
    in_window: list[Assessment],
    everything: list[Assessment],
    coverage: Coverage,
) -> list[Statement]:
    """Disputes the gates confirmed, and links they only proposed (D29)."""
    statements: list[Statement] = []
    for a in everything:
        event = a.event
        if event.disputed_by is None:
            continue
        if event.contradiction is ContradictionState.STANDING:
            statements.append(
                Statement(
                    f"{event.description} — {event.dispute_detail} It is shown as a "
                    "possible relationship, not as a contradiction.",
                    (event.event_id, event.disputed_by),
                )
            )
        else:
            statements.append(
                Statement(
                    f"{event.description} is marked {event.contradiction.value.lower()}. "
                    f"{event.dispute_detail} This lowers how sure we are, not how much it "
                    "matters.",
                    (event.event_id, event.disputed_by),
                )
            )
    return statements


def _disclosures(
    company: str,
    window: Window,
    in_window: list[Assessment],
    everything: list[Assessment],
    coverage: Coverage,
) -> list[Statement]:
    """Filings, specifically — not news that mentions one.

    Selected by the evidence behind an event rather than by its wording, the same way the
    detail view groups a record by kind. An exchange filing is the company on the record;
    a report about a filing is not.
    """
    filed = [a for a in everything if any(e.source == "nse-disclosures" for e in a.event.evidence)]
    if not filed:
        return []
    return [
        Statement(
            f"{len(filed)} exchange disclosure{'s' if len(filed) != 1 else ''} on record for "
            f"{company}, newest first:",
            tuple(a.event.event_id for a in filed[:5]),
        ),
        *(_development(a) for a in filed[:5]),
    ]


def _explain_simple(
    company: str,
    window: Window,
    in_window: list[Assessment],
    everything: list[Assessment],
    coverage: Coverage,
) -> list[Statement]:
    """The shortest honest version: what it asks of you, and the single strongest reason.

    Not a rephrasing of the full answer — there is no model here to rephrase with. It is a
    deliberately narrower selection from the same ledger: the level, the one reason that
    contributed most, and a plain statement of what the level does not mean.
    """
    subject = (in_window or everything)[0]
    level = subject.attention.value.replace("_", " ").lower()
    strongest = max(subject.reasons, key=lambda r: r.contribution, default=None)

    statements = [
        Statement(
            f"In short: {company} is at {level}, and we are {subject.confidence.value.lower()} "
            "confidence about it.",
            (subject.event.event_id,),
        ),
        Statement(subject.event.description, (subject.event.event_id,)),
    ]
    if strongest is not None:
        statements.append(
            Statement(f"Mostly because: {strongest.detail}", (subject.event.event_id,))
        )
    statements.append(
        Statement(
            "Attention means it is worth your time to look, not that anything should be "
            "bought or sold.",
            (),
        )
    )
    return statements


# --- the whole watchlist ---------------------------------------------------------


COMPANY_INTENTS: frozenset[Intent] = frozenset(
    {
        Intent.WHAT_CHANGED,
        Intent.WHY_ATTENTION,
        Intent.COVERAGE,
        Intent.CORROBORATION,
        Intent.PRICE_CONTEXT,
        Intent.CONTRADICTION,
        Intent.DISCLOSURES,
        Intent.EXPLAIN_SIMPLE,
    }
)

WATCHLIST_INTENTS: frozenset[Intent] = frozenset(
    {Intent.WATCHLIST_ATTENTION, Intent.BIGGEST_MOVERS, Intent.ALERTS}
)
"""Questions about the set rather than about one company.

``DISCLOSURES`` is deliberately in neither set: "any important disclosures?" is a sensible
question at both scopes, and the answer differs only in how wide it looks.
"""


@dataclass(frozen=True)
class Mover:
    """One company's stored end-of-day move. Supplied by the caller, never computed here."""

    symbol: str
    company: str
    change_pct: float | None
    """``None`` where no close is stored. Absence, never a flat move."""
    as_of: str | None


@dataclass(frozen=True)
class AlertLine:
    """One watch point, flattened for the answer. The caller reads the domain object."""

    symbol: str
    condition: str
    note: str
    triggered_on: str | None
    triggered_close: float | None
    acknowledged: bool


@dataclass(frozen=True)
class WatchlistFacts:
    """Everything a watchlist-scope answer may draw on.

    Assembled by the caller from what the dashboard already loads, so asking a question
    costs the same queries as opening the page — no second path to the data, and nothing
    fetched from outside (D40).
    """

    company_count: int
    surfaced: tuple[tuple[str, Assessment], ...]
    """Symbol and assessment for everything new since the last completed review, in the
    backend's canonical order (D26). Never re-sorted here."""
    movers: tuple[Mover, ...]
    alerts: tuple[AlertLine, ...]


def explain_watchlist(
    *,
    intent: Intent,
    window: Window,
    facts: WatchlistFacts,
    coverage: Coverage,
) -> Answer:
    """Answer a question about the watchlist as a whole, from records already assembled."""
    if intent is Intent.OUT_OF_SCOPE_ADVICE:
        return Answer(
            intent=intent,
            answered=False,
            insufficient_reason="out-of-scope",
            statements=(
                Statement(
                    "This product reports what changed and how confident we are. It does "
                    "not give buy, sell or hold advice, and it does not predict prices.",
                    (),
                ),
            ),
        )

    if intent in COMPANY_INTENTS and intent is not Intent.DISCLOSURES:
        return Answer(
            intent=intent,
            answered=False,
            insufficient_reason="needs-a-company",
            statements=(
                Statement(
                    "That question is about one company. Open a company and ask again, or "
                    "name one of the questions below.",
                    (),
                ),
            ),
        )

    if intent is Intent.UNSUPPORTED:
        return Answer(
            intent=intent,
            answered=False,
            insufficient_reason="unsupported",
            statements=(
                Statement(
                    "I can only answer from what the system has already assessed. Try one "
                    "of the questions below.",
                    (),
                ),
            ),
        )

    builders = {
        Intent.WATCHLIST_ATTENTION: _watchlist_attention,
        Intent.BIGGEST_MOVERS: _biggest_movers,
        Intent.ALERTS: _alerts,
        Intent.DISCLOSURES: _watchlist_disclosures,
    }
    statements = builders[intent](window, facts)

    if not statements:
        return Answer(
            intent=intent,
            answered=False,
            insufficient_reason="no-record-of-that",
            statements=(
                Statement(
                    "I don't have enough evidence to answer that from what we hold for "
                    "your watchlist.",
                    (),
                ),
            ),
        )
    return Answer(
        intent=intent,
        answered=True,
        statements=tuple(statements),
        cited_event_ids=tuple(dict.fromkeys(i for s in statements for i in s.event_ids)),
    )


def _watchlist_attention(window: Window, facts: WatchlistFacts) -> list[Statement]:
    """What needs the reader, in the order the backend already ranked it (D26)."""
    if not facts.surfaced:
        return [
            Statement(
                f"Nothing on your {facts.company_count} watched "
                f"{'companies' if facts.company_count != 1 else 'company'} is asking for "
                f"you {window.basis}. That is a finding, not an empty page — we looked.",
                (),
            )
        ]
    return [
        Statement(
            f"{len(facts.surfaced)} development"
            f"{'s' if len(facts.surfaced) != 1 else ''} across "
            f"{len({s for s, _ in facts.surfaced})} of your {facts.company_count} companies "
            f"{window.basis}, most demanding first:",
            tuple(a.event.event_id for _, a in facts.surfaced),
        ),
        *(
            Statement(f"{symbol} — {_development(a).text}", (a.event.event_id,))
            for symbol, a in facts.surfaced[:5]
        ),
    ]


def _biggest_movers(window: Window, facts: WatchlistFacts) -> list[Statement]:
    """Stored end-of-day moves, largest first. A company with no close is named as such."""
    known = [m for m in facts.movers if m.change_pct is not None]
    if not known:
        return []
    ranked = sorted(known, key=lambda m: abs(m.change_pct or 0.0), reverse=True)[:5]
    missing = [m.symbol for m in facts.movers if m.change_pct is None]

    statements = [
        Statement(
            "Largest end-of-day moves on your watchlist. These are stored closing prices, "
            "not live quotes, and a move is not by itself a reason to act:",
            (),
        ),
        *(
            Statement(
                f"{m.symbol} ({m.company}) {_sign(m.change_pct)}"
                f"{abs(m.change_pct or 0):.2f}% on {m.as_of or 'an unrecorded session'}.",
                (),
            )
            for m in ranked
        ),
    ]
    if missing:
        statements.append(
            Statement(
                f"No stored close for {', '.join(sorted(missing))}, so they are absent from "
                "this list rather than counted as unchanged.",
                (),
            )
        )
    return statements


def _sign(change: float | None) -> str:
    """A typographic minus, so a move reads the same here as it does on the board."""
    return "+" if (change or 0.0) >= 0 else "\u2212"


def _alerts(window: Window, facts: WatchlistFacts) -> list[Statement]:
    """The reader's own levels, and where each stands (D37)."""
    if not facts.alerts:
        return []
    triggered = [a for a in facts.alerts if a.triggered_on is not None]
    waiting = [a for a in facts.alerts if a.triggered_on is None]

    statements: list[Statement] = []
    if triggered:
        statements.append(
            Statement(
                f"{len(triggered)} of your levels "
                f"{'have' if len(triggered) != 1 else 'has'} been reached:",
                (),
            )
        )
        statements.extend(
            Statement(
                f"{a.symbol} {a.condition} — closed "
                f"{a.triggered_close if a.triggered_close is not None else '—'} on "
                f"{a.triggered_on}"
                f"{f'. You said: {a.note}' if a.note else ''}"
                f"{'' if not a.acknowledged else ' (already seen)'}.",
                (),
            )
            for a in triggered
        )
    if waiting:
        statements.append(
            Statement(
                f"{len(waiting)} still waiting: "
                + ", ".join(f"{a.symbol} {a.condition}" for a in waiting)
                + ".",
                (),
            )
        )
    return statements


def _watchlist_disclosures(window: Window, facts: WatchlistFacts) -> list[Statement]:
    """Exchange filings among what was surfaced, chosen by evidence rather than wording."""
    filed = [
        (symbol, a)
        for symbol, a in facts.surfaced
        if any(e.source == "nse-disclosures" for e in a.event.evidence)
    ]
    if not filed:
        return []
    return [
        Statement(
            f"{len(filed)} exchange disclosure{'s' if len(filed) != 1 else ''} across your "
            f"watchlist {window.basis}:",
            tuple(a.event.event_id for _, a in filed),
        ),
        *(
            Statement(f"{symbol} — {_development(a).text}", (a.event.event_id,))
            for symbol, a in filed[:5]
        ),
    ]
