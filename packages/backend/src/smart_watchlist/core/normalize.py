"""Evidence to event candidates.

Step 0 normalizes exchange disclosures, which arrive already structured — a category, a
symbol, a timestamp, an attachment. Extraction is therefore deterministic and is
recorded as such. When free-text news joins in step 2, an LLM produces candidates from
prose and the extraction provenance names the model, prompt and schema instead; nothing
downstream changes, because it consumes candidates either way (DESIGN.md D5).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .models import EventCandidate

if TYPE_CHECKING:
    from .models import Evidence

__all__ = [
    "EXTRACTION_DETERMINISTIC",
    "MATERIAL_EVENT_TYPES",
    "ROUTINE_EVENT_TYPES",
    "to_candidate",
]

EXTRACTION_DETERMINISTIC = "deterministic/disclosure-fields/v1"

MATERIAL_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "Outcome of Board Meeting",
        "Agreements",
        "Acquisition",
        "Diversification/Disinvestment",
        "Credit Rating- Revision",
        "Financial Result Updates",
        "Change in Directors/ Key Managerial Personnel",
        "Amalgamation/ Merger",
        "Raising of Funds",
    }
)
"""Disclosure categories a reasonable follower of the company would want to know about."""

ROUTINE_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "Shareholders meeting",
        "Analysts/Institutional Investor Meet/Con. Call Updates",
        "General Updates",
        "Record Date",
        "Updates",
        "Trading Window",
        "Investor Presentation",
        "Newspaper Publication",
    }
)
"""Categories that occur constantly and rarely change what anyone understands."""


def to_candidate(evidence: Evidence, event_type: str) -> EventCandidate:
    """Read one disclosure as a claim about one company.

    The claim is not asserted true here — it is asserted *made*, by a named source at a
    known time, with the evidence reference kept so every later statement can be traced
    back to it.

    Company identity comes from ``subject_company``, never from ``publisher``. Those
    coincide for exchange filings and diverge for everything else.
    """
    return EventCandidate(
        security_symbol=evidence.security_symbol,
        company_name=evidence.subject_company,
        event_type=event_type,
        description=evidence.title,
        occurred_at=evidence.published_at,
        evidence_refs=(evidence.source_ref,),
        extraction=EXTRACTION_DETERMINISTIC,
    )
