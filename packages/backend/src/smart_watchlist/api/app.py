"""HTTP interface — a thin shell over ``core``.

Holds no engine logic. It serves persisted assessments and the reason codes that
produced them; it never computes an attention level (DESIGN.md D2).

Every ownership check would live at this boundary or deeper. Step 0 has no user state
yet, so everything served here is shared intelligence — the same for every reader.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..adapters.claude_extractor import ClaudeExtractor
from ..adapters.google_news import GoogleNewsSource
from ..adapters.nse_disclosures import SOURCE_NAME, NseDisclosureSource
from ..adapters.rule_extractor import RuleExtractor
from ..adapters.sqlite_store import SqliteAssessmentStore
from ..adapters.yfinance_market import YFinanceMarketSource
from ..core.corroboration import assess_corroboration
from ..core.engine import coverage_status_note
from ..core.models import Attention
from ..core.pipeline import (
    run_disclosure_pipeline,
    run_market_pipeline,
    run_news_pipeline,
)

if TYPE_CHECKING:
    from ..core.models import Assessment, IngestRun

__all__ = ["app"]

DB_PATH = os.environ.get("WATCHLIST_DB", "watchlist.db")

app = FastAPI(title="Smart Market Watchlist", version="0.1.0")

# The web package runs on its own dev-server origin. Narrow deliberately: this is a
# development convenience, not a public API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4321", "http://127.0.0.1:4321"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# Built once. Constructing per request re-ran the migration check on every call.
_STORE = SqliteAssessmentStore(DB_PATH)


def _store() -> SqliteAssessmentStore:
    return _STORE


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check. Says nothing about source coverage — that is a domain verdict."""
    return {"status": "ok"}


@app.post("/ingest")
def ingest() -> dict[str, Any]:
    """Run the disclosure pipeline once and persist what it assessed.

    Manual for now. Step 3 puts this on a schedule, because observing only when someone
    asks cannot answer "what changed while I was gone" (DESIGN.md D3).
    """
    store = _store()
    market = YFinanceMarketSource()
    market_run, market_assessed = run_market_pipeline(market, store)
    news_run, news_assessed = run_news_pipeline(
        GoogleNewsSource(), ClaudeExtractor(), store, market=market, fallback=RuleExtractor()
    )
    disclosure_run, disclosure_assessed = run_disclosure_pipeline(
        NseDisclosureSource(), store, market=market
    )
    return {
        "assessed": len(market_assessed) + len(disclosure_assessed) + len(news_assessed),
        "source_health": _serialise_run(disclosure_run),
        "runs": [
            _serialise_run(market_run),
            _serialise_run(news_run),
            _serialise_run(disclosure_run),
        ],
    }


@app.get("/assessments")
def assessments(limit: int = 50) -> dict[str, Any]:
    """Persisted verdicts in canonical ranked order, plus current source health.

    ``source_health`` is a top-level field rather than something derived from the
    assessments, because the case that matters most is the one where there are no
    assessments at all. A failed ingest must be visible even when the list is empty and
    even when older verdicts are still being shown.
    """
    store = _store()
    items = _rank(store.recent(limit))
    latest = store.latest_run(SOURCE_NAME)
    return {
        "count": len(items),
        "source_health": None if latest is None else _serialise_run(latest),
        "assessments": [_serialise(a) for a in items],
    }


_RANK: dict[Attention, int] = {
    Attention.HIGH: 0,
    Attention.MEDIUM: 1,
    Attention.LOW: 2,
    Attention.NONE: 3,
    Attention.UNABLE: 4,
}


def _rank(items: list[Assessment]) -> list[Assessment]:
    """Canonical product ordering — what each item asks of the reader, then how strongly.

    The engine owns this. Clients render the order they are given; a client that
    re-derived it would be a second, divergent answer to a product question
    (DESIGN.md D2).
    """
    return sorted(items, key=lambda a: (_RANK[a.attention], -a.score, a.event.security_symbol))


def _serialise_run(run: IngestRun) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "source": run.source,
        "started_at": run.started_at.isoformat(),
        "assessed_count": run.assessed_count,
        "healthy": run.is_healthy,
        "records": [
            {"source": c.source, "status": c.status.value, "detail": c.detail}
            for c in run.coverage.records
        ],
    }


def _serialise(assessment: Assessment) -> dict[str, Any]:
    """View model.

    Coverage travels with the verdict rather than being summarised away: the reader
    must be able to tell a conclusion from an admission.
    """
    event = assessment.event
    corroboration = assess_corroboration(event.evidence)
    return {
        "event_id": event.event_id,
        "symbol": event.security_symbol,
        "company": event.company_name,
        "event_type": event.event_type,
        "description": event.description,
        "occurred_at": event.occurred_at.isoformat(),
        "attention": assessment.attention.value,
        "confidence": assessment.confidence.value,
        "score": assessment.score,
        "scoring_version": assessment.scoring_version,
        "reasons": [
            {
                "code": r.code,
                "direction": r.direction,
                "contribution": r.contribution,
                "detail": r.detail,
            }
            for r in assessment.reasons
        ],
        "coverage": {
            "complete": assessment.coverage.is_complete,
            "note": coverage_status_note(assessment.coverage),
            "records": [
                {"source": c.source, "status": c.status.value, "detail": c.detail}
                for c in assessment.coverage.records
            ],
        },
        "corroboration": {
            "article_count": corroboration.article_count,
            "independent_source_count": corroboration.independent_source_count,
            "summary": corroboration.summary,
            "has_authoritative": corroboration.has_authoritative,
        },
        "evidence": [
            {
                "source": e.source,
                "ref": e.source_ref,
                "tier": e.tier.name,
                "publisher": e.publisher,
                "subject_company": e.subject_company,
                "published_at": e.published_at.isoformat(),
                "url": e.url,
            }
            for e in event.evidence
        ],
    }
