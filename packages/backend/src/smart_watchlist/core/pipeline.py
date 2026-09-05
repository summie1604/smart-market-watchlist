"""Orchestration: evidence in, persisted assessments out.

The spine of Step 0. It depends only on the protocols in :mod:`.ports`, so the same
function runs against the live NSE adapter or a fixture — which is what makes seeded
demo data a genuine test of the pipeline rather than a parallel fake (DESIGN.md D18).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from .engine import assess
from .models import Coverage, CoverageRecord, CoverageStatus, Event, IngestRun
from .normalize import to_candidate

if TYPE_CHECKING:
    from .models import Assessment, Evidence
    from .ports import AssessmentStore, DisclosureSource

__all__ = ["NOT_BUILT_SOURCES", "run_disclosure_pipeline"]

NOT_BUILT_SOURCES = ("market", "news")
"""Source families the design calls for that this step has not built.

Declared rather than omitted: an expected source that is absent is missing coverage,
and every verdict produced now must carry that. Silence about a gap would be the one
failure the product cannot afford.
"""


def _event_id(evidence: Evidence) -> str:
    """Stable identity for one disclosure.

    Derived from the source and its native reference, so re-ingestion is idempotent.
    This is *not* the event-identity model from D12 — linking, and the AMBIGUOUS
    outcome, arrive in step 2. Step 0 creates one event per disclosure and says so.
    """
    raw = f"{evidence.source}:{evidence.source_ref}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _declared_gaps(now: datetime) -> list[CoverageRecord]:
    return [
        CoverageRecord(
            source=name,
            status=CoverageStatus.NOT_BUILT,
            observed_at=now,
            detail=f"The {name} adapter is not built yet (Step 0).",
        )
        for name in NOT_BUILT_SOURCES
    ]


def run_disclosure_pipeline(
    source: DisclosureSource, store: AssessmentStore
) -> tuple[IngestRun, list[Assessment]]:
    """Fetch, normalize, assess and persist.

    Returns the run alongside what it assessed. The run is persisted unconditionally,
    including when the fetch failed and produced nothing: a run that saw nothing still
    happened, and without that record a failed ingest leaves the previous run's healthy
    coverage standing as though it were current — blindness reading as quiet, which is
    the failure this system exists to avoid (VISION.md §14, DESIGN.md D15).
    """
    now = datetime.now(UTC)
    evidence_list, source_coverage = source.fetch()
    coverage = Coverage(records=(source_coverage, *_declared_gaps(now)))

    assessments: list[Assessment] = []
    for evidence in evidence_list:
        candidate = to_candidate(evidence, event_type=evidence.category)
        event = Event(
            event_id=_event_id(evidence),
            security_symbol=candidate.security_symbol,
            company_name=candidate.company_name,
            event_type=candidate.event_type,
            description=candidate.description,
            occurred_at=candidate.occurred_at,
            evidence=(evidence,),
        )
        assessment = assess(event, coverage)
        store.save(assessment)
        assessments.append(assessment)

    run = IngestRun(
        run_id=f"{source.name}:{now.isoformat()}",
        source=source.name,
        started_at=now,
        coverage=coverage,
        assessed_count=len(assessments),
    )
    store.save_run(run)
    return run, assessments
