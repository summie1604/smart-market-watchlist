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

from ..core.attribution import subject_rejection
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
