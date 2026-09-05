"""Orchestration: evidence in, persisted assessments out.

The spine of Step 0. It depends only on the protocols in :mod:`.ports`, so the same
function runs against the live NSE adapter or a fixture — which is what makes seeded
demo data a genuine test of the pipeline rather than a parallel fake (DESIGN.md D18).
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from .context import BROAD_INDEX, context_for, curated_symbols
from .corroboration import assess_corroboration
from .engine import assess
from .extraction import ExtractedEvent, Extraction, validate
from .linking import LINK_WINDOW, LinkOutcome, decide_link
from .market import observe
from .models import Coverage, CoverageRecord, CoverageStatus, Event, IngestRun
from .normalize import from_observation, to_candidate

if TYPE_CHECKING:
    from .market import MarketObservation
    from .models import Assessment, Evidence
    from .ports import AssessmentStore, DisclosureSource, Extractor, MarketSource, NewsSource

__all__ = [
    "NOT_BUILT_SOURCES",
    "run_disclosure_pipeline",
    "run_market_pipeline",
    "run_news_pipeline",
]

NOT_BUILT_SOURCES: tuple[str, ...] = ()
"""Source families the design calls for that this step has not built.

Declared rather than omitted: an expected source that is absent is missing coverage,
and every verdict produced now must carry that. Silence about a gap would be the one
failure the product cannot afford.

The market adapter left this list in step 1, the news adapter in step 2, so it is now
empty. The mechanism stays: the next source family the design calls for and the build
lacks is declared here rather than omitted.
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


def run_news_pipeline(
    source: NewsSource,
    extractor: Extractor,
    store: AssessmentStore,
    market: MarketSource | None = None,
    fallback: Extractor | None = None,
) -> tuple[IngestRun, list[Assessment]]:
    """News to assessed events: extract, validate, link, corroborate, score.

    The order matters and mirrors the product goal. Extraction proposes; validation
    grounds it against the source; linking decides whether this is a new occurrence or
    another report of one we hold; corroboration counts independent publishers rather
    than articles; only then does the engine score it.

    ``fallback`` runs when the primary extractor returns nothing — normally the rule
    extractor behind the model, so a model outage degrades the reading rather than
    stopping the flow of news into the domain (D5).
    """
    now = datetime.now(UTC)
    companies = [(symbol, context_for(symbol, symbol).name) for symbol in curated_symbols()]
    evidence_list, news_coverage = source.fetch(companies)

    observations, market_coverage = _observe_disclosed(market, evidence_list, now)
    disclosure_gap = CoverageRecord(
        source="nse-disclosures",
        status=CoverageStatus.UNAVAILABLE,
        observed_at=now,
        detail="Disclosures were not consulted by this news run.",
    )
    coverage = Coverage(records=(news_coverage, market_coverage, disclosure_gap))

    assessments: list[Assessment] = []
    for evidence in evidence_list:
        assessment = _assess_article(
            evidence, extractor, fallback, coverage, observations, store, now
        )
        if assessment is not None:
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


def _assess_article(
    evidence: Evidence,
    extractor: Extractor,
    fallback: Extractor | None,
    coverage: Coverage,
    observations: dict[str, MarketObservation],
    store: AssessmentStore,
    now: datetime,
) -> Assessment | None:
    """One article, all the way through. Returns ``None`` when nothing survives."""
    degraded = False
    proposal = extractor.extract(evidence)
    if proposal is None and fallback is not None:
        proposal = fallback.extract(evidence)
        degraded = proposal is not None
    if proposal is None:
        return None  # the article stays stored as evidence; it yields no event

    used = fallback.name if degraded and fallback is not None else extractor.name
    extraction, refusal = validate(proposal, evidence, used)
    if extraction is None or refusal is not None:
        return None  # not about this company, or too thin to be anything

    decision = decide_link(
        extraction.event,
        _link_candidates(store, evidence, extraction.event, now),
    )

    if decision.outcome is LinkOutcome.LINK and decision.event_id is not None:
        event = _merge_into(store, decision.event_id, evidence, extraction.event)
    else:
        event = Event(
            event_id=_event_id(evidence),
            security_symbol=evidence.security_symbol,
            company_name=extraction.event.subject_company,
            event_type=extraction.event.event_type,
            description=extraction.event.description,
            occurred_at=extraction.event.occurred_at or evidence.published_at,
            evidence=(evidence,),
        )

    assessment = assess(
        event,
        coverage,
        observations.get(evidence.security_symbol),
        corroboration=assess_corroboration(event.evidence),
        extraction=extraction,
        link=decision,
    )
    store.save(
        assessment, extraction=_extraction_row(extraction), link_state=decision.outcome.value
    )
    return assessment


def _link_candidates(
    store: AssessmentStore, evidence: Evidence, proposal: ExtractedEvent, now: datetime
) -> list[tuple[Event, ExtractedEvent | None]]:
    since = now - LINK_WINDOW
    rows = store.candidates(evidence.security_symbol, proposal.event_type, since)
    return [(a.event, _extraction_from_row(raw)) for a, raw in rows]


def _merge_into(
    store: AssessmentStore, event_id: str, evidence: Evidence, proposal: ExtractedEvent
) -> Event:
    """Attach this article to the event it continues.

    One event, several evidence records — which is what makes article count and event
    count different numbers, and why five reports of one story are not five alerts.
    """
    existing = store.get(event_id)
    if existing is None:
        # The link target could not be read back. Reusing its id would overwrite it with
        # a single evidence record and destroy the provenance it had accumulated, so this
        # becomes a new event instead — a duplicate, which is the survivable error (D12).
        return Event(
            event_id=_event_id(evidence),
            security_symbol=evidence.security_symbol,
            company_name=proposal.subject_company,
            event_type=proposal.event_type,
            description=proposal.description,
            occurred_at=evidence.published_at,
            evidence=(evidence,),
        )
    already = {e.source_ref for e in existing.event.evidence}
    merged = (
        existing.event.evidence
        if evidence.source_ref in already
        else (*existing.event.evidence, evidence)
    )
    return replace(existing.event, evidence=merged)


def _extraction_row(extraction: Extraction) -> dict[str, object]:
    event = extraction.event
    return {
        "subject_company": event.subject_company,
        "event_type": event.event_type,
        "description": event.description,
        "counterparties": list(event.counterparties),
        "geographies": list(event.geographies),
        "products": list(event.products),
        "industries": list(event.industries),
        "regulator": event.regulator,
        "contract_value": event.contract_value,
        "is_speculative": event.is_speculative,
        "extractor": extraction.extractor,
        "dropped": list(extraction.dropped),
    }


def _extraction_from_row(raw: dict[str, object] | None) -> ExtractedEvent | None:
    if raw is None:
        return None
    return ExtractedEvent(
        subject_company=_text(raw.get("subject_company")),
        event_type=_text(raw.get("event_type")),
        description=_text(raw.get("description")),
        counterparties=_string_tuple(raw.get("counterparties")),
        geographies=_string_tuple(raw.get("geographies")),
        products=_string_tuple(raw.get("products")),
        industries=_string_tuple(raw.get("industries")),
        regulator=_optional_text(raw.get("regulator")),
        contract_value=_optional_text(raw.get("contract_value")),
        is_speculative=bool(raw.get("is_speculative", False)),
    )


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(v for v in value if isinstance(v, str))
