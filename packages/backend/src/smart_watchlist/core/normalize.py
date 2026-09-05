"""Evidence to event candidates.

Step 0 normalizes exchange disclosures, which arrive already structured — a category, a
symbol, a timestamp, an attachment. Extraction is therefore deterministic and is
recorded as such. When free-text news joins in step 2, an LLM produces candidates from
prose and the extraction provenance names the model, prompt and schema instead; nothing
downstream changes, because it consumes candidates either way (DESIGN.md D5).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from .models import EventCandidate, Evidence, SourceTier

if TYPE_CHECKING:
    from datetime import date

    from .market import MarketObservation

__all__ = [
    "CORPORATE_ACTION",
    "EXTRACTION_DETERMINISTIC",
    "MATERIAL_EVENT_TYPES",
    "ROUTINE_EVENT_TYPES",
    "UNUSUAL_MOVEMENT",
    "from_observation",
    "to_candidate",
]

EXTRACTION_DETERMINISTIC = "deterministic/disclosure-fields/v1"

UNUSUAL_MOVEMENT = "Unusual price movement"
"""Category for evidence the system computed itself, rather than read somewhere."""

CORPORATE_ACTION = "Corporate action"

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


def from_observation(observation: MarketObservation, company_name: str) -> list[Evidence]:
    """Turn a market observation into evidence, where it says something worth saying.

    An observation is evidence in its own right — computed by us from primary data, which
    is why :attr:`SourceTier.COMPUTED` exists. Two cases produce it, and they are
    deliberately different:

    *An unusual move* becomes evidence so the system can report that something happened
    without claiming to know why. That is scenario A: the honest output is the movement
    and its context, never a manufactured cause.

    *A corporate action* becomes evidence so a mechanical move is reported as mechanical.
    Adjustment already removed it from the return (D14), so it can no longer masquerade
    as deterioration — but staying silent would leave the reader wondering why the
    printed price moved. That is scenario G.

    A calm session produces nothing. Absence of evidence here is not a verdict; the
    per-company review in step 4 is what will say "nothing meaningful changed".
    """
    evidence: list[Evidence] = []
    if observation.corporate_action is not None:
        evidence.append(
            _computed(
                observation,
                company_name,
                category=CORPORATE_ACTION,
                title=(
                    f"{observation.symbol}: {observation.corporate_action}. "
                    f"Printed price moved {observation.raw_return_pct:+.1f}%; "
                    f"adjusted for the action the move is {observation.return_pct:+.1f}%."
                ),
            )
        )
    if observation.is_unusual and not observation.is_mechanical:
        evidence.append(
            _computed(
                observation,
                company_name,
                category=UNUSUAL_MOVEMENT,
                title=(
                    f"{observation.symbol} moved {observation.return_pct:+.1f}% "
                    f"({observation.sigma_multiple:+.1f} times its own typical session)."
                ),
            )
        )
    return evidence


def _computed(
    observation: MarketObservation, company_name: str, *, category: str, title: str
) -> Evidence:
    stamp = _at_midnight(observation.as_of)
    return Evidence(
        source="market",
        source_ref=f"market:{observation.symbol}:{observation.as_of.isoformat()}:{category}",
        tier=SourceTier.COMPUTED,
        publisher="computed",
        subject_company=company_name,
        retrieved_at=stamp,
        published_at=stamp,
        title=title,
        body="",
        url="",
        security_symbol=observation.symbol,
        category=category,
    )


def _at_midnight(on: date) -> datetime:
    """Sessions are dated, not timestamped. Anchor to the session date in UTC."""
    return datetime(on.year, on.month, on.day, tzinfo=UTC)
