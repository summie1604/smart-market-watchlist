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
from .models import Assessment, Attention, Confidence, CoverageStatus, ReasonCode, SourceTier
from .normalize import (
    CORPORATE_ACTION,
    MATERIAL_EVENT_TYPES,
    ROUTINE_EVENT_TYPES,
    UNUSUAL_MOVEMENT,
)
from .scoring import SCORING_VERSION, attention_for, weight_of

if TYPE_CHECKING:
    from .market import MarketObservation
    from .models import Coverage, Event

__all__ = ["assess", "coverage_status_note"]

_REQUIRED_FOR_A_CLEAN_NEGATIVE = ("market", "news")
"""Source families that must be present before "nothing meaningful changed" is sayable."""


def _reason(code: str, detail: str) -> ReasonCode:
    return ReasonCode(code=code, contribution=weight_of(code), detail=detail)


def assess(
    event: Event, coverage: Coverage, observation: MarketObservation | None = None
) -> Assessment:
    """Decide what this event asks of a user, and record why.

    Coverage is an input, not a footnote: a verdict produced while a source family was
    missing is a weaker verdict, and where the verdict *is* the absence of a finding,
    missing coverage removes our standing to state it at all.

    ``observation`` is the market's account of the same security over the same window.
    It sharpens a disclosure — trading corroborating a filing means more than either
    alone — and for a computed event it *is* the finding.
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

    reasons.extend(_market_reasons(event, observation, coverage))

    missing = {r.source for r in coverage.missing}
    if "market" in missing and observation is None:
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
    #
    # The exception is a finding that explains itself. This promotion exists because an
    # *absence* of findings might be blindness; it does not apply when the system holds a
    # complete, high-confidence account of what it observed. A split is fully explained
    # by the corporate action that caused it, and reporting that as "unable to evaluate"
    # would misrepresent a thing we understand exactly (scenario G).
    blind_to = [s for s in _REQUIRED_FOR_A_CLEAN_NEGATIVE if s in missing]
    if attention is Attention.NONE and blind_to and not _explains_itself(event, reasons):
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


def _explains_itself(event: Event, reasons: list[ReasonCode]) -> bool:
    """True when the verdict rests on a positive account rather than on absence.

    Narrow by intent: only a corporate action qualifies today, because only a corporate
    action both causes the movement and fully accounts for it. Widening this is how the
    coverage guarantee gets quietly eroded, so it should be widened only against a
    named case.
    """
    return event.event_type == CORPORATE_ACTION and any(
        r.code == "CORPORATE_ACTION_EXPLAINS_MOVE" for r in reasons
    )


def _market_reasons(
    event: Event, observation: MarketObservation | None, coverage: Coverage
) -> list[ReasonCode]:
    """What trading says about this event — including when it says nothing.

    Order matters here only in that it mirrors D14: the observation handed in has
    already been adjusted for corporate actions and compared to the security's own
    baseline. Nothing in this function re-derives any of that.
    """
    if observation is None:
        return []

    reasons: list[ReasonCode] = []
    is_computed = event.event_type in (UNUSUAL_MOVEMENT, CORPORATE_ACTION)

    if observation.is_mechanical:
        # Scenario G. The adjustment already removed this from the return; saying so
        # is what stops a reader mistaking a split for deterioration.
        reasons.append(
            _reason(
                "CORPORATE_ACTION_EXPLAINS_MOVE",
                f"The printed move is mechanical: {observation.corporate_action}.",
            )
        )
    elif observation.is_unusual:
        reasons.append(
            _reason(
                "UNUSUAL_PRICE_MOVE" if is_computed else "MARKET_CORROBORATES",
                f"Moved {observation.return_pct:+.1f}%, "
                f"{observation.sigma_multiple:+.1f} times its own typical session.",
            )
        )
        if observation.volume_ratio >= 2.0:
            reasons.append(
                _reason(
                    "ELEVATED_VOLUME",
                    f"Volume {observation.volume_ratio:.1f} times its trailing median.",
                )
            )

    if observation.is_sector_explained:
        reasons.append(
            _reason(
                "MOVE_EXPLAINED_BY_SECTOR",
                f"{observation.sector_index} moved similarly; "
                f"the company-specific residual is {observation.residual_pct:+.1f}%. "
                "Context, not cause.",
            )
        )

    if not observation.has_baseline:
        reasons.append(
            _reason(
                "THIN_BASELINE",
                f"Only {observation.baseline_sessions} prior sessions — "
                "too few to call a move unusual.",
            )
        )

    # Scenario A. An unusual move with nothing company-specific behind it is reported as
    # exactly that — but "we found no disclosure" is a claim about disclosures, and it
    # requires having looked. Where the disclosure source was not consulted, the honest
    # statement is the coverage gap, not the finding.
    if is_computed and event.event_type == UNUSUAL_MOVEMENT:
        checked = any(
            r.source == "nse-disclosures" and r.status is CoverageStatus.OK
            for r in coverage.records
        )
        reasons.append(
            _reason(
                "NO_COMPANY_EVENT_DETECTED" if checked else "NO_DISCLOSURE_CONSULTED",
                "No company-specific disclosure found for this move. "
                "Reported as unexplained rather than attributed."
                if checked
                else "Disclosures were not consulted for this move, so no claim is made "
                "about whether one exists.",
            )
        )

    return reasons


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
