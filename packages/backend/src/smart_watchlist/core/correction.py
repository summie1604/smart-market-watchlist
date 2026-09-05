"""Correcting derived intelligence that a later rule proves unsupported.

Narrow by intent. This re-checks stored assessments against the current subject-grounding
rule and removes only those whose evidence never supported attribution to the company
they were filed under — preserving the raw evidence and its provenance in the rejection
record, so nothing is lost except the claim that should not have been made.

It does not touch coverage, ingest runs, user state, or any assessment that still passes.
Correcting derived intelligence is not the same as deleting history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from ..adapters.rule_extractor import EXTRACTOR_NAME as RULE_NAME
from ..adapters.rule_extractor import subject_rejection

if TYPE_CHECKING:
    from .ports import AssessmentStore

__all__ = ["CorrectionReport", "correct_unsupported_attribution"]


@dataclass
class CorrectionReport:
    checked: int = 0
    removed: list[tuple[str, str, str]] = field(default_factory=list)
    """``(event_id, symbol, reason)`` for each claim withdrawn."""

    @property
    def removed_count(self) -> int:
        return len(self.removed)


def correct_unsupported_attribution(
    store: AssessmentStore, dry_run: bool = False
) -> CorrectionReport:
    """Withdraw assessments whose evidence never supported the company they name.

    Only rule-derived news assessments are re-checked. A model extraction read the article
    body and can support an attribution this bounded rule cannot see, so re-judging one by
    the other's standard would discard sound work.
    """
    report = CorrectionReport()
    now = datetime.now(UTC)

    for assessment in store.recent(1000):
        event = assessment.event
        news_evidence = [e for e in event.evidence if e.source == "news"]
        if not news_evidence:
            continue  # market observations and filings are not attributed by headline

        report.checked += 1
        # Supported if *any* piece of its evidence would still pass grounding today.
        reasons = [subject_rejection(e) for e in news_evidence]
        if any(reason is None for reason in reasons):
            continue

        reason = next(r for r in reasons if r is not None)
        report.removed.append((event.event_id, event.security_symbol, reason))
        if dry_run:
            continue

        for evidence in news_evidence:
            store.record_rejection(evidence, reason, RULE_NAME, now)
        store.delete_assessment(event.event_id)

    return report
