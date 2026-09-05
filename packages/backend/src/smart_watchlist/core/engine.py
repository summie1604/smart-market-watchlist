"""The Meaningful Change Engine.

Deterministic, and explainable by construction: the reason codes it emits are the same
information that produced the verdict, never a narration added afterwards. An attention
level that cannot produce its reason codes cannot be ranked (DESIGN.md D4, VISION.md §15).

Step 0 assesses disclosures only. Relevance, corroboration and market-relative
significance arrive in step 3; their absence is not hidden — it is scored as a negative
reason code and reported as missing coverage.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from .context import CoverageTier, context_for
from .models import Assessment, Attention, Confidence, ReasonCode, SourceTier
from .normalize import MATERIAL_EVENT_TYPES, ROUTINE_EVENT_TYPES
from .scoring import SCORING_VERSION, attention_for, weight_of

if TYPE_CHECKING:
    from .models import Coverage, Event

__all__ = ["assess", "coverage_status_note"]

_REQUIRED_FOR_A_CLEAN_NEGATIVE = ("market", "news")
"""Source families that must be present before "nothing meaningful changed" is sayable."""


def _reason(code: str, detail: str) -> ReasonCode:
    return ReasonCode(code=code, contribution=weight_of(code), detail=detail)


def assess(event: Event, coverage: Coverage) -> Assessment:
    """Decide what this event asks of a user, and record why.

    Coverage is an input, not a footnote: a verdict produced while a source family was
    missing is a weaker verdict, and where the verdict *is* the absence of a finding,
    missing coverage removes our standing to state it at all.
    """
    reasons: list[ReasonCode] = []

    tiers = {e.tier for e in event.evidence}
    if SourceTier.OFFICIAL_DISCLOSURE in tiers:
        reasons.append(
            _reason(
                "AUTHORITATIVE_DISCLOSURE",
                "Filed with the exchange by the company — not reported, disclosed.",
            )
        )

    if event.event_type in MATERIAL_EVENT_TYPES:
        reasons.append(
            _reason("MATERIAL_EVENT_TYPE", f"{event.event_type} is a material disclosure category.")
        )
    elif event.event_type in ROUTINE_EVENT_TYPES:
        reasons.append(
            _reason("ROUTINE_EVENT_TYPE", f"{event.event_type} is routine for a listed company.")
        )

    context = context_for(event.security_symbol, event.company_name)
    if context.tier is CoverageTier.LIMITED:
        reasons.append(
            _reason(
                "LIMITED_COMPANY_COVERAGE",
                "Outside the curated universe — no sector, competitor or exposure context.",
            )
        )

    missing = {r.source for r in coverage.missing}
    if "market" in missing:
        reasons.append(
            _reason(
                "NO_MARKET_OBSERVATION",
                "No price or volume observation available to corroborate or discount this.",
            )
        )
    if "news" in missing:
        reasons.append(
            _reason(
                "NO_NEWS_CORROBORATION",
                "No independent reporting available to corroborate this disclosure.",
            )
        )

    score = sum(r.contribution for r in reasons)
    attention = attention_for(score)

    # A negative finding is only sayable when we could actually look. Where the verdict
    # would be "nothing meaningful here" but a required source family was missing, the
    # honest verdict is that we could not evaluate it — VISION.md §14.
    blind_to = [s for s in _REQUIRED_FOR_A_CLEAN_NEGATIVE if s in missing]
    if attention is Attention.NONE and blind_to:
        attention = Attention.UNABLE

    return Assessment(
        event=event,
        attention=attention,
        confidence=_confidence(tiers),
        reasons=tuple(reasons),
        coverage=coverage,
        scoring_version=SCORING_VERSION,
        assessed_at=datetime.now(UTC),
        score=score,
    )


def _confidence(tiers: set[SourceTier]) -> Confidence:
    """Confidence tracks the evidence, never the score.

    Separate from attention deliberately: "possibly significant, uncertain" and
    "modest, certain" are different answers, and one number would destroy the difference.
    """
    if not tiers:
        return Confidence.LOW
    best = max(tiers, key=lambda t: t.value)
    if best in (SourceTier.COMPUTED, SourceTier.OFFICIAL_DISCLOSURE):
        return Confidence.HIGH
    if best is SourceTier.CREDIBLE_REPORTING:
        return Confidence.MEDIUM
    return Confidence.LOW


def coverage_status_note(coverage: Coverage) -> str:
    """One line describing what could not be consulted. Empty when coverage is complete."""
    if coverage.is_complete:
        return ""
    parts = [f"{r.source} ({r.status.value.lower()})" for r in coverage.missing]
    return "Not consulted: " + ", ".join(parts)
