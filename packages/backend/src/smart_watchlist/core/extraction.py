"""Structured extraction, and the deterministic gate every extractor passes through.

An extractor — a language model, a rule set, anything — proposes structure. It does not
get to assert it. This module holds the shape of that proposal and the validation that
decides which parts of it may enter the domain.

**Grounding is the anti-fabrication mechanism, and it is deterministic.** A material
field naming something concrete — a counterparty, a regulator, a product, a monetary
figure — must appear in the source text. A model that invents a counterparty produces a
field that fails this check and is dropped, with the drop recorded. That is a stronger
guarantee than prompting, because it does not depend on the model cooperating.

Unknown stays unknown. An extractor that omits a field leaves it absent; nothing here
fills a gap with a plausible value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from .models import Evidence

__all__ = [
    "ExtractedEvent",
    "Extraction",
    "ValidationOutcome",
    "validate",
]

_GROUNDED_FIELDS = ("counterparties", "geographies", "products", "regulator", "contract_value")
"""Fields naming something concrete enough that the source must contain it.

``event_type`` and ``description`` are deliberately excluded: a type is a classification
and a description is a paraphrase, and requiring either to appear verbatim would reject
correct work. They are constrained by the allowed vocabulary and by length instead.
"""

_WORD = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class ExtractedEvent:
    """What an extractor proposes about one article. Not yet a claim about the world."""

    subject_company: str
    event_type: str
    description: str
    occurred_at: datetime | None = None
    counterparties: tuple[str, ...] = ()
    geographies: tuple[str, ...] = ()
    products: tuple[str, ...] = ()
    industries: tuple[str, ...] = ()
    regulator: str | None = None
    contract_value: str | None = None
    is_speculative: bool = False
    """The article reports a rumour, a report of talks, or an unconfirmed plan."""
    concerns_subject: bool = True
    """False when the company is mentioned only incidentally, or the story is sector-wide."""
    missing: tuple[str, ...] = ()
    """Fields the extractor could not determine. Absence, stated."""


@dataclass(frozen=True)
class Extraction:
    """A validated proposal, plus the record of what validation removed."""

    event: ExtractedEvent
    evidence_ref: str
    extractor: str
    """Provider and prompt or ruleset version, so a result can be reproduced and debugged."""
    dropped: tuple[str, ...] = field(default=())
    """Fields removed because the source did not support them."""

    @property
    def is_grounded(self) -> bool:
        return not self.dropped


class ValidationOutcome:
    """Why an extraction was refused entry, when it was."""

    REJECTED_EMPTY = "empty"
    REJECTED_NOT_ABOUT_SUBJECT = "not-about-subject"


def validate(
    proposal: ExtractedEvent, evidence: Evidence, extractor: str
) -> tuple[Extraction | None, str | None]:
    """Gate one proposal against its source.

    Returns the validated extraction, or ``None`` with a reason. Partial support is not
    failure: unsupported fields are stripped and recorded, and what the source does
    support is kept — a semantically incomplete but honest extraction is more useful
    than a rejected one, provided the reader can see what was removed.
    """
    if not proposal.subject_company.strip() or not proposal.description.strip():
        return None, ValidationOutcome.REJECTED_EMPTY

    if not proposal.concerns_subject:
        return None, ValidationOutcome.REJECTED_NOT_ABOUT_SUBJECT

    haystack = _tokens(f"{evidence.title} {evidence.body}")
    dropped: list[str] = []
    cleaned = proposal

    for name in _GROUNDED_FIELDS:
        value = getattr(proposal, name)
        if not value:
            continue
        if isinstance(value, str):
            if not _supported(value, haystack):
                dropped.append(name)
                cleaned = replace(cleaned, **{name: None})
            continue
        kept = tuple(v for v in value if _supported(v, haystack))
        if len(kept) != len(value):
            dropped.append(name)
        cleaned = replace(cleaned, **{name: kept})

    return Extraction(
        event=cleaned,
        evidence_ref=evidence.source_ref,
        extractor=extractor,
        dropped=tuple(dropped),
    ), None


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def _supported(value: str, haystack: set[str]) -> bool:
    """Every meaningful token of the value must appear in the source.

    Token-level rather than substring, so "Aramco" matches inside a longer phrase while
    an invented "Saudi Aramco Refining Ltd" whose distinctive words are absent does not.
    Short tokens are ignored — they carry no evidence either way.
    """
    words = [w for w in _WORD.findall(value.lower()) if len(w) > 2]
    return bool(words) and all(w in haystack for w in words)
