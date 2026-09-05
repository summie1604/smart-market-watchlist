"""Scoring configuration — weights and thresholds, versioned.

Mechanism and calibration are separate concerns, and only the mechanism is claimed to
be right (DESIGN.md D4). These numbers are judgement. They live here, versioned, so a
change to them is one edit and a historical decision can be read against the rules in
force when it was made — not so that anyone can claim the values are correct.

Production calibration would need historical evaluation and user-outcome data we do
not have. What holds these honest instead is the fixture set in ``tests``.
"""

from __future__ import annotations

from .models import Attention

__all__ = ["SCORING_VERSION", "THRESHOLDS", "WEIGHTS", "attention_for", "weight_of"]

SCORING_VERSION = "2026-09-05.a"

WEIGHTS: dict[str, int] = {
    # Provenance
    "AUTHORITATIVE_DISCLOSURE": 3,
    # Event semantics — which disclosures a reasonable follower would want to know about
    "MATERIAL_EVENT_TYPE": 3,
    "ROUTINE_EVENT_TYPE": -3,
    # Coverage — an absent source lowers what may be claimed, it never leaves it unchanged
    "NO_MARKET_OBSERVATION": -1,
    "NO_NEWS_CORROBORATION": -1,
    "LIMITED_COMPANY_COVERAGE": -1,
}

THRESHOLDS: dict[Attention, int] = {
    Attention.HIGH: 5,
    Attention.MEDIUM: 3,
    Attention.LOW: 1,
}


def weight_of(code: str) -> int:
    """The signed contribution a reason code carries under this scoring version."""
    return WEIGHTS[code]


def attention_for(score: int) -> Attention:
    """Map a total score onto an attention level.

    Below the LOW threshold is :attr:`Attention.NONE` — a positive conclusion that
    nothing here meets the bar, not a failure to decide. Whether that conclusion is
    *sayable* depends on coverage, which the engine settles separately.
    """
    if score >= THRESHOLDS[Attention.HIGH]:
        return Attention.HIGH
    if score >= THRESHOLDS[Attention.MEDIUM]:
        return Attention.MEDIUM
    if score >= THRESHOLDS[Attention.LOW]:
        return Attention.LOW
    return Attention.NONE
