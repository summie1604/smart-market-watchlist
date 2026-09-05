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
    """Implements ``Extractor``. Never raises, never invents."""

    name = EXTRACTOR_NAME

    def extract(self, evidence: Evidence) -> ExtractedEvent | None:
        text = f"{evidence.title} {evidence.body}"
        lowered = text.lower()

        event_type = _classify(lowered)
        if event_type is None:
            return None  # nothing recognisable; better than a guess

        # A story about the index or the sector is not a company event, even when the
        # company's name appears in it.
        concerns_subject = not bool(_SECTOR_WIDE.search(evidence.title))

        money = _MONEY.search(text)
        return ExtractedEvent(
            subject_company=evidence.subject_company,
            event_type=event_type,
            description=evidence.title,
            occurred_at=evidence.published_at,
            contract_value=money.group(0).strip() if money else None,
            is_speculative=bool(_SPECULATIVE.search(text)),
            concerns_subject=concerns_subject,
            missing=("counterparties", "geographies", "products", "regulator"),
        )


def _classify(lowered: str) -> str | None:
    for event_type, keywords in _EVENT_VOCABULARY:
        if any(keyword in lowered for keyword in keywords):
            return event_type
    return None
