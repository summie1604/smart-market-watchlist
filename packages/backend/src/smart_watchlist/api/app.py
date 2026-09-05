"""HTTP interface — a thin shell over ``core``.

Holds no engine logic. It serves persisted assessments and the reason codes that
produced them; it never computes an attention level (DESIGN.md D2).

Every ownership check would live at this boundary or deeper. Step 0 has no user state
yet, so everything served here is shared intelligence — the same for every reader.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

from ..adapters.claude_extractor import ClaudeExtractor
from ..adapters.google_news import SOURCE_NAME as NEWS_SOURCE
from ..adapters.google_news import GoogleNewsSource
from ..adapters.nse_disclosures import SOURCE_NAME as DISCLOSURE_SOURCE
from ..adapters.nse_disclosures import NseDisclosureSource
from ..adapters.rule_extractor import RuleExtractor
from ..adapters.sqlite_store import SqliteAssessmentStore
from ..adapters.user_store import SESSION_LIFETIME, SqliteUserStore
from ..adapters.yfinance_market import SOURCE_NAME as MARKET_SOURCE
from ..adapters.yfinance_market import YFinanceMarketSource
from ..core.context import context_for, curated_symbols
from ..core.corroboration import assess_corroboration
from ..core.engine import coverage_status_note
from ..core.models import Attention, Coverage
from ..core.pipeline import (
    run_disclosure_pipeline,
    run_market_pipeline,
    run_news_pipeline,
)
from ..core.review import CompanyLine, assemble

# Imported at runtime, not under TYPE_CHECKING: FastAPI resolves dependency
# annotations at import time, and a string-only annotation becomes a query parameter.
from ..core.userstate import User, advance_checkpoint
from .auth import COOKIE_NAME, clear_session_cookie, current_user, set_session_cookie

if TYPE_CHECKING:
    from ..core.models import Assessment, IngestRun

__all__ = ["app"]

DB_PATH = os.environ.get("WATCHLIST_DB", "watchlist.db")

app = FastAPI(title="Smart Market Watchlist", version="0.1.0")

# The web package runs on its own dev-server origin. Narrow deliberately: this is a
# development convenience, not a public API.
# The dev server runs on its own origin, so the session cookie is cross-origin and needs
# allow_credentials. Origins stay explicit rather than "*": a wildcard is incompatible
# with credentialed requests, and would be wrong here even if it were not.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4321", "http://127.0.0.1:4321"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


# Built once. Constructing per request re-ran the migration check on every call.
_STORE = SqliteAssessmentStore(DB_PATH)
_USER_STORE = SqliteUserStore(DB_PATH)
app.state.user_store = _USER_STORE


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

    # Health is reported for every source family, not just disclosures. Reading one
    # source and calling it "the" health let the page claim nothing had been looked at
    # while it was displaying results from a source that had run.
    runs = [store.latest_run(name) for name in SOURCE_FAMILIES]
    present = [_serialise_run(r) for r in runs if r is not None]
    return {
        "count": len(items),
        "source_health": _overall_health(present),
        "runs": present,
        "assessments": [_serialise(a) for a in items],
    }


SOURCE_FAMILIES = (DISCLOSURE_SOURCE, MARKET_SOURCE, NEWS_SOURCE)


def _overall_health(runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """One summary across the families that have actually run.

    ``None`` means nothing has ever run — genuinely nothing looked at. A family that has
    never run is absent from ``runs`` rather than counted as healthy, because absence of
    a failure record is not evidence of success.
    """
    if not runs:
        return None
    unhealthy = [r for r in runs if not r["healthy"]]
    records = [record for run in runs for record in run["records"]]
    return {
        "run_id": ",".join(str(r["run_id"]) for r in runs),
        "source": ", ".join(str(r["source"]) for r in runs),
        "started_at": max(str(r["started_at"]) for r in runs),
        "assessed_count": sum(int(r["assessed_count"]) for r in runs),
        "healthy": not unhealthy,
        "records": records,
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


# --- accounts -----------------------------------------------------------------


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class SymbolRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)


class CompleteRequest(BaseModel):
    review_id: str = Field(min_length=1, max_length=128)
    """The review's identity, not its cutoff. A client returning a timestamp is returning
    a claim; a client returning an id is returning a reference the server can resolve."""


_GENERIC_AUTH_FAILURE = "Registration failed or the email is unavailable."
"""Deliberately uninformative: distinguishing "taken" from other failures confirms that
an account exists."""


@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(credentials: Credentials, response: Response) -> dict[str, Any]:
    user = _USER_STORE.create_user(str(credentials.email), credentials.password)
    if user is None:
        raise HTTPException(status.HTTP_409_CONFLICT, _GENERIC_AUTH_FAILURE)
    session = _USER_STORE.create_session(user.user_id)
    set_session_cookie(response, session.session_id, int(SESSION_LIFETIME.total_seconds()))
    return {"user_id": user.user_id, "email": user.email}


@app.post("/auth/login")
def login(credentials: Credentials, response: Response) -> dict[str, Any]:
    user = _USER_STORE.verify_credentials(str(credentials.email), credentials.password)
    if user is None:
        # One message for a wrong password and an unknown account alike.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password.")
    session = _USER_STORE.create_session(user.user_id)
    set_session_cookie(response, session.session_id, int(SESSION_LIFETIME.total_seconds()))
    return {"user_id": user.user_id, "email": user.email}


@app.post("/auth/logout")
def logout(request: Request, response: Response) -> dict[str, str]:
    session_id = request.cookies.get(COOKIE_NAME)
    if session_id:
        _USER_STORE.end_session(session_id)
    clear_session_cookie(response)
    return {"status": "signed out"}


@app.get("/auth/me")
def me(user: Annotated[User, Depends(current_user)]) -> dict[str, Any]:
    return {"user_id": user.user_id, "email": user.email}


# --- watchlist ----------------------------------------------------------------


@app.get("/watchlist")
def watchlist(user: Annotated[User, Depends(current_user)]) -> dict[str, Any]:
    """This user's companies. Scoped by the session, never by a supplied id."""
    return {
        "companies": [
            _membership_view(m.symbol, m.added_at) for m in _USER_STORE.memberships(user.user_id)
        ]
    }


@app.post("/watchlist")
def add_to_watchlist(
    body: SymbolRequest, user: Annotated[User, Depends(current_user)]
) -> dict[str, Any]:
    symbol = body.symbol.strip().upper()
    if symbol not in curated_symbols():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"{symbol} is not a supported security. Supported: {', '.join(curated_symbols())}.",
        )
    membership = _USER_STORE.add_membership(user.user_id, symbol)
    return _membership_view(membership.symbol, membership.added_at)


@app.delete("/watchlist/{symbol}")
def remove_from_watchlist(
    symbol: str, user: Annotated[User, Depends(current_user)]
) -> dict[str, Any]:
    removed = _USER_STORE.remove_membership(user.user_id, symbol.strip().upper())
    return {"symbol": symbol.strip().upper(), "removed": removed}


def _membership_view(symbol: str, added_at: datetime) -> dict[str, Any]:
    context = context_for(symbol, symbol)
    return {
        "symbol": symbol,
        "company": context.name,
        "coverage_tier": context.tier.value,
        "added_at": added_at.isoformat(),
        "watched_from": added_at.isoformat(),
    }


# --- review -------------------------------------------------------------------


@app.get("/review")
def review(user: Annotated[User, Depends(current_user)]) -> dict[str, Any]:
    """Assemble this user's review and issue a server-owned cutoff.

    The cutoff is server time, recorded before the assessments are read, so an event that
    arrives while the user is reading falls outside this window and stays new (D7).
    """
    store = _store()
    previous = _USER_STORE.checkpoint(user.user_id)
    cutoff = datetime.now(UTC)
    issued = _USER_STORE.issue_review(user.user_id, previous, cutoff)

    memberships = _USER_STORE.memberships(user.user_id)
    assembled = assemble(
        user_id=user.user_id,
        memberships=memberships,
        previous_checkpoint=previous,
        review_cutoff=cutoff,
        assessments=_rank(store.recent(500)),
        coverage=_current_coverage(store),
    )
    return {
        "review_id": issued.review_id,
        "previous_checkpoint": None if previous is None else previous.isoformat(),
        "review_cutoff": cutoff.isoformat(),
        "attention_count": assembled.attention_count,
        "changed": [_line_view(line) for line in assembled.changed],
        "newly_added": [_line_view(line) for line in assembled.newly_added],
        "unable": [_line_view(line) for line in assembled.unable],
        "quiet": [_line_view(line) for line in assembled.quiet],
    }


@app.post("/review/complete")
def complete_review(
    body: CompleteRequest, user: Annotated[User, Depends(current_user)]
) -> dict[str, Any]:
    """Advance the checkpoint to the cutoff this review was issued with.

    Never to the click time: an event that arrived after the cutoff was not part of what
    the user reviewed, and advancing past it would silently mark it seen.
    """
    issued = _USER_STORE.issued_review(body.review_id, user.user_id)
    if issued is None:
        # Also the answer when the review belongs to someone else — the lookup is scoped
        # by user, so another user's review is simply not found.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown review.")

    current = _USER_STORE.checkpoint(user.user_id)
    resolved, outcome = advance_checkpoint(current, issued.review_cutoff)
    _USER_STORE.set_checkpoint(user.user_id, resolved)

    # Read back rather than echoing what we wrote: the store enforces monotonicity in
    # SQL, so the persisted value is the authority even under concurrent completion.
    persisted = _USER_STORE.checkpoint(user.user_id) or resolved
    return {"checkpoint": persisted.isoformat(), "outcome": outcome}


def _line_view(line: CompanyLine) -> dict[str, Any]:
    return {
        "symbol": line.symbol,
        "company": line.company_name,
        "coverage_tier": line.coverage_tier,
        "state": line.state,
        "detail": line.detail,
        "assessments": [_serialise(a) for a in line.assessments],
    }


def _current_coverage(store: SqliteAssessmentStore) -> Coverage:
    """Current source health: each family judged by its own most recent run.

    A run's coverage record about a *different* source says "this run did not consult
    it", which is a fact about that run and not about that source's health. Pooling all
    records let a market run's "news not consulted" override the news run's own healthy
    record — so news read as missing while it was fine, and every company came back
    "unable to evaluate". That makes the honest quiet verdict unreachable, which inverts
    the guarantee: the system would claim ignorance it does not have.
    """
    records = []
    for name in SOURCE_FAMILIES:
        run = store.latest_run(name)
        if run is None:
            continue
        own = [record for record in run.coverage.records if record.source == name]
        records.extend(own)
    return Coverage(records=tuple(records))
