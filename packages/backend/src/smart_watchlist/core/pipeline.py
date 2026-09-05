"""Orchestration: evidence in, persisted assessments out.

The spine of Step 0. It depends only on the protocols in :mod:`.ports`, so the same
function runs against the live NSE adapter or a fixture — which is what makes seeded
demo data a genuine test of the pipeline rather than a parallel fake (DESIGN.md D18).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from .context import BROAD_INDEX, context_for, curated_symbols
from .engine import assess
from .market import observe
from .models import Coverage, CoverageRecord, CoverageStatus, Event, IngestRun
from .normalize import from_observation, to_candidate

if TYPE_CHECKING:
    from .market import MarketObservation
    from .models import Assessment, Evidence
    from .ports import AssessmentStore, DisclosureSource, MarketSource

__all__ = ["NOT_BUILT_SOURCES", "run_disclosure_pipeline", "run_market_pipeline"]

NOT_BUILT_SOURCES = ("news",)
"""Source families the design calls for that this step has not built.

Declared rather than omitted: an expected source that is absent is missing coverage,
and every verdict produced now must carry that. Silence about a gap would be the one
failure the product cannot afford.

The market adapter left this list in step 1. News remains.
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
    source: DisclosureSource, store: AssessmentStore, market: MarketSource | None = None
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

    observations, market_coverage = _observe_disclosed(market, evidence_list, now)
    coverage = Coverage(records=(source_coverage, market_coverage, *_declared_gaps(now)))

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
        assessment = assess(event, coverage, observations.get(evidence.security_symbol))
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


def run_market_pipeline(
    source: MarketSource, store: AssessmentStore
) -> tuple[IngestRun, list[Assessment]]:
    """Observe the curated universe and assess what the market did.

    The chain runs in the order D14 fixes — adjustment, then baseline, then residual,
    then unusualness — inside :func:`smart_watchlist.core.market.observe`. This function
    only decides which securities to observe and what to persist.

    A calm security produces no assessment. That is not the same as a verdict of "no
    meaningful change", which is a per-company statement the review page owes the user
    in step 4; here it is simply the absence of anything worth recording.
    """
    now = datetime.now(UTC)
    symbols = curated_symbols()
    indices = tuple({c for c in (context_for(s, s).sector_index for s in symbols) if c})
    bars, market_coverage = source.fetch([*symbols, *indices, BROAD_INDEX])

    news_gap = CoverageRecord(
        source="news",
        status=CoverageStatus.NOT_BUILT,
        observed_at=now,
        detail="The news adapter is not built yet.",
    )
    # This run observes the market only. Saying "no company event was found" would be a
    # claim about disclosures, and this run did not look at them — so the gap is stated
    # and the engine withholds the claim.
    disclosure_gap = CoverageRecord(
        source="nse-disclosures",
        status=CoverageStatus.UNAVAILABLE,
        observed_at=now,
        detail="Disclosures were not consulted by this market run.",
    )

    assessments: list[Assessment] = []
    for symbol in symbols:
        series = bars.get(symbol)
        if series is None:
            continue  # no data for this security; the run coverage already says so
        context = context_for(symbol, symbol)
        observation = observe(
            symbol,
            series,
            sector_index=context.sector_index,
            sector_bars=bars.get(context.sector_index) if context.sector_index else None,
        )
        if observation is None:
            continue
        assessments.extend(
            _assess_observation(
                observation, context.name, market_coverage, news_gap, disclosure_gap, store
            )
        )

    run = IngestRun(
        run_id=f"{source.name}:{now.isoformat()}",
        source=source.name,
        started_at=now,
        coverage=Coverage(records=(market_coverage, news_gap, disclosure_gap)),
        assessed_count=len(assessments),
    )
    store.save_run(run)
    return run, assessments


def _assess_observation(
    observation: MarketObservation,
    company_name: str,
    market_coverage: CoverageRecord,
    news_gap: CoverageRecord,
    disclosure_gap: CoverageRecord,
    store: AssessmentStore,
) -> list[Assessment]:
    coverage = Coverage(records=(market_coverage, news_gap, disclosure_gap))
    out: list[Assessment] = []
    for evidence in from_observation(observation, company_name):
        event = Event(
            event_id=_event_id(evidence),
            security_symbol=evidence.security_symbol,
            company_name=evidence.subject_company,
            event_type=evidence.category,
            description=evidence.title,
            occurred_at=evidence.published_at,
            evidence=(evidence,),
        )
        assessment = assess(event, coverage, observation)
        store.save(assessment)
        out.append(assessment)
    return out


def _observe_disclosed(
    market: MarketSource | None, evidence_list: list[Evidence], now: datetime
) -> tuple[dict[str, MarketObservation], CoverageRecord]:
    """Market context for the securities that disclosed something.

    Market data is not built into this pipeline's silence. When no market source is
    supplied the gap is *stated*, because "we did not look" and "we looked and it was
    calm" license different conclusions — and a capability existing elsewhere in the
    system never licenses a claim this verdict's evidence does not support.
    """
    if market is None:
        return {}, CoverageRecord(
            source="market",
            status=CoverageStatus.UNAVAILABLE,
            observed_at=now,
            detail="Market data was not consulted for this run.",
        )

    symbols = sorted({e.security_symbol for e in evidence_list})
    if not symbols:
        return {}, CoverageRecord(
            source="market",
            status=CoverageStatus.OK,
            observed_at=now,
            detail="No disclosed securities to observe.",
        )

    indices = tuple({c for c in (context_for(s, s).sector_index for s in symbols) if c})
    bars, coverage = market.fetch([*symbols, *indices])

    observations: dict[str, MarketObservation] = {}
    for symbol in symbols:
        series = bars.get(symbol)
        if series is None:
            continue
        context = context_for(symbol, symbol)
        found = observe(
            symbol,
            series,
            sector_index=context.sector_index,
            sector_bars=bars.get(context.sector_index) if context.sector_index else None,
        )
        if found is not None:
            observations[symbol] = found
    return observations, coverage
