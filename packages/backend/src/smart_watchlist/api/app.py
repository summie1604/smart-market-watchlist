"""HTTP interface — a thin shell over ``core``.

Holds no engine logic. It serves persisted assessments and the reason codes that
produced them; it never computes an attention level (DESIGN.md D2).

**One versioned API, many clients** (D30, D33). Every domain route lives under
``/v1``. The web app and a later mobile client call the same paths, receive the same
verdicts in the same canonical order, and share the TypeScript types generated from this
module's OpenAPI schema. A second client that needed a second backend would be a second
place for authorization and the review window to be wrong.

``/health`` stays unversioned on purpose: it is an infrastructure probe, not a domain
resource, and a load balancer should not have to know which API version it is talking to.

Every ownership check lives at this boundary or deeper, and every private query is scoped
to the resolved user rather than checked afterwards.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field

from ..adapters.gemini_extractor import GeminiExtractor
from ..adapters.google_news import SOURCE_NAME as NEWS_SOURCE
from ..adapters.google_news import GoogleNewsSource
from ..adapters.nse_disclosures import SOURCE_NAME as DISCLOSURE_SOURCE
from ..adapters.nse_disclosures import NseDisclosureSource
from ..adapters.rule_extractor import RuleExtractor
from ..adapters.sqlite_store import SqliteAssessmentStore
from ..adapters.user_store import SESSION_LIFETIME, SqliteUserStore
from ..adapters.yfinance_market import SOURCE_NAME as MARKET_SOURCE
from ..adapters.yfinance_market import YFinanceMarketSource
from ..core.context import BROAD_INDEX, context_for, curated_symbols, index_label
from ..core.corroboration import assess_corroboration
from ..core.engine import coverage_status_note
from ..core.explainer import (
    DISCLAIMER,
    GENERATED_BY,
    SUGGESTIONS,
    WATCHLIST_INTENTS,
    WATCHLIST_SUGGESTIONS,
    AlertLine,
    Answer,
    Intent,
    Mover,
    WatchlistFacts,
    Window,
    explain,
    explain_watchlist,
    resolve_intent,
)
from ..core.focus import FOCUS_TAGS, FocusMatch, matches_focus, normalise_tags
from ..core.grouping import development_ids
from ..core.ingestion import IngestionSources
from ..core.models import Attention, Confidence, ContradictionState, Coverage
from ..core.prices import PriceComparison, PriceStatus, build_comparison, build_status
from ..core.ranking import canonical_order
from ..core.review import CompanyLine, Review, assemble
from ..core.scoring import SCORING_VERSION
from ..core.standing import standing_label, standing_of, standing_of_publisher

# Imported at runtime, not under TYPE_CHECKING: FastAPI resolves dependency
# annotations at import time, and a string-only annotation becomes a query parameter.
from ..core.userstate import Membership, User, advance_checkpoint
from ..core.watchpoints import (
    MAX_NOTE,
    WatchDirection,
    WatchPoint,
    direction_for,
    percent_rejection_for,
    rejection_for,
)
from ..demo import judge_db_path, reset, seed
from .auth import (
    COOKIE_NAME,
    clear_session_cookie,
    current_user,
    demo_mode_enabled,
    optional_user,
    session_id_of,
    set_session_cookie,
)
from .scheduler import IngestionScheduler, SchedulerConfig
from .schemas import (
    AccountView,
    AssessmentsResponse,
    AssistantAnswerView,
    CompleteReviewResponse,
    ExplainerAnswerView,
    FocusTagsResponse,
    IngestResponse,
    MetaResponse,
    PriceComparisonView,
    PriceStatusesResponse,
    RemovedResponse,
    ReviewPageView,
    SchedulerResponse,
    SessionView,
    StatusResponse,
    UniverseResponse,
    WatchedCompanyView,
    WatchlistResponse,
    WatchPointsResponse,
    WatchPointView,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from datetime import date

    from ..core.models import Assessment, Evidence, IngestRun

log = logging.getLogger("smart_watchlist.api")

__all__ = ["API_VERSION", "app"]

API_VERSION = "v1"
"""The API's contract version, and the prefix every domain route is served under.

Bumped only for a breaking change. Additive fields do not bump it: a client that ignores
an unknown field keeps working, and forcing every client to move for a new field is how
versions multiply until nobody can retire one.
"""

MODE = os.environ.get("SMART_WATCHLIST_MODE", "live").strip().lower()
"""``live`` or ``judge``. Explicit, and validated below.

Judge mode is never inferred — not from a missing key, not from an empty database. An
accidental entry into it would put simulated market data in front of someone who believed
it was real, which is the one failure this whole feature exists to prevent (D42).
"""

if MODE not in ("live", "judge"):
    raise RuntimeError(
        f"SMART_WATCHLIST_MODE must be 'live' or 'judge', not {MODE!r}. "
        "A misconfigured mode fails here rather than silently serving the wrong data."
    )

JUDGE_MODE = MODE == "judge"

# Judge state never shares a file with live state, so a reset cannot reach real records.
DB_PATH = judge_db_path() if JUDGE_MODE else os.environ.get("WATCHLIST_DB", "watchlist.db")


def _scheduler_config() -> SchedulerConfig:
    """Configuration, deliberately four knobs and all optional.

    Defaults are development-safe: enabled, a quarter-hour interval, and one run shortly
    after startup so a fresh clone has data without anyone calling an endpoint.
    """
    return SchedulerConfig(
        enabled=os.environ.get("INGEST_SCHEDULER", "on").lower() not in ("off", "0", "false"),
        interval=timedelta(minutes=float(os.environ.get("INGEST_INTERVAL_MINUTES", "15"))),
        run_on_startup=os.environ.get("INGEST_ON_STARTUP", "on").lower()
        not in ("off", "0", "false"),
    )


def _live_sources() -> IngestionSources:
    """The real providers. Gemini leads; the rule extractor is the separate fallback."""
    return IngestionSources(
        market=YFinanceMarketSource(),
        disclosures=NseDisclosureSource(),
        news=GoogleNewsSource(),
        extractor=GeminiExtractor(),
        fallback=RuleExtractor(),
    )


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Own the scheduler's life alongside the application's.

    Ingestion belongs to the process, not to a request: nothing here is triggered by a
    page view, and no external or model call happens while rendering (D3).
    """
    if JUDGE_MODE:
        # Seeded once, then left alone. Judge mode reaches no provider: the scenario is
        # already stored, and a scheduler would replace it with whatever the market is
        # doing — which is precisely the dependency judge mode exists to remove.
        seed(DB_PATH)
        application.state.scheduler = None
        log.info("judge.ready path=%s scheduler=disabled", DB_PATH)
        yield
        return

    scheduler = IngestionScheduler(
        _live_sources(), _STORE, _scheduler_config(), watch_points=_USER_STORE
    )
    application.state.scheduler = scheduler
    await scheduler.start()
    try:
        yield
    finally:
        await scheduler.stop()


app = FastAPI(title="Smart Market Watchlist", version="0.1.0", lifespan=_lifespan)

# The web package runs on its own dev-server origin. Astro picks the next available
# port in development, so permit only its localhost port range rather than making the
# credentialed API available to arbitrary origins.
# The dev server runs on its own origin, so the session cookie is cross-origin and needs
# allow_credentials. Origins stay explicit rather than "*": a wildcard is incompatible
# with credentialed requests, and would be wrong here even if it were not.
# Deployment may serve the built frontend from this same process, in which case there is
# no cross-origin request to allow. ``WEB_ORIGINS`` covers the split-deployment case.
_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "WEB_ORIGINS", "http://localhost:4321,http://127.0.0.1:4321"
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ORIGINS,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):4\d{3}",
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


api = APIRouter()
"""Every domain route. Mounted under ``/v1`` below, so the version lives in one place
rather than being repeated on fifty decorators."""


# Built once. Constructing per request re-ran the migration check on every call.
_STORE = SqliteAssessmentStore(DB_PATH)
_USER_STORE = SqliteUserStore(DB_PATH)
app.state.user_store = _USER_STORE


def _store() -> SqliteAssessmentStore:
    return _STORE


@app.get("/health", response_model=StatusResponse)
def health() -> dict[str, str]:
    """Liveness check. Says nothing about source coverage — that is a domain verdict."""
    return {"status": "ok"}


@api.get("/meta", response_model=MetaResponse)
def meta() -> dict[str, Any]:
    """What this API is, so a client can refuse to guess.

    A mobile app ships and then keeps running against a server that moves on without it.
    Reporting the contract version, the scoring version behind every verdict and the
    supported focus vocabulary lets a client say *"this server is newer than I understand"*
    instead of silently rendering a field it will misinterpret.
    """
    return {
        "api_version": API_VERSION,
        "scoring_version": SCORING_VERSION,
        "demo_mode": demo_mode_enabled(),
        "mode": MODE,
        "attention_levels": [a.value for a in Attention],
        "confidence_levels": [c.value for c in Confidence],
        "contradiction_states": [c.value for c in ContradictionState],
        "focus_tags": [t.tag for t in FOCUS_TAGS],
        "price_ranges": list(_RANGES),
        "source_families": list(SOURCE_FAMILIES),
    }


@api.post("/ingest", response_model=IngestResponse)
async def ingest(request: Request) -> dict[str, Any]:
    """Run one cycle now, through the same path the scheduler uses.

    Kept as an operator and development affordance, not a second implementation: a bug
    cannot hide in the path nobody exercises. A cycle already in flight returns busy
    rather than queueing, since two concurrent cycles duplicate fetches for no benefit.
    """
    scheduler: IngestionScheduler | None = request.app.state.scheduler
    if scheduler is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Ingestion is disabled in judge mode: the scenario is fixed on purpose.",
        )
    result = await scheduler.trigger()
    if result is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An ingestion cycle is already running.")
    return {
        "outcome": result.outcome,
        "assessed": result.assessed,
        "healthy_families": result.healthy_families,
        "failed_families": result.failed_families,
        "runs": [_serialise_run(run) for run in result.runs],
    }


@api.get("/scheduler", response_model=SchedulerResponse)
def scheduler_status(request: Request) -> dict[str, Any]:
    """Operational visibility: is it running, when did the last cycle run, how did it go."""
    scheduler: IngestionScheduler | None = request.app.state.scheduler
    if scheduler is None:
        # Judge mode: the scenario is stored and nothing ingests. Reported honestly rather
        # than as a scheduler that is merely idle.
        return {
            "enabled": False,
            "started": False,
            "cycle_active": False,
            "interval_seconds": 0.0,
            "cycles_completed": 0,
            "next_run_at": None,
            "last_cycle": None,
        }
    return scheduler.status()


@api.get("/assessments", response_model=AssessmentsResponse)
def assessments(request: Request, limit: int = 50) -> dict[str, Any]:
    """Persisted verdicts in canonical ranked order, plus current source health.

    ``source_health`` is a top-level field rather than something derived from the
    assessments, because the case that matters most is the one where there are no
    assessments at all. A failed ingest must be visible even when the list is empty and
    even when older verdicts are still being shown.

    Shared intelligence: the verdicts and their order are the same for every caller.
    When we can tell who is asking, each item additionally carries which of *their*
    stated interests it matches — an annotation on an unchanged verdict (D27).
    """
    store = _store()
    items = _rank(store.recent(limit))
    tags = _tags_by_symbol(optional_user(request))

    # Health is reported for every source family, not just disclosures. Reading one
    # source and calling it "the" health let the page claim nothing had been looked at
    # while it was displaying results from a source that had run.
    runs = [store.latest_run(name) for name in SOURCE_FAMILIES]
    present = [_serialise_run(r) for r in runs if r is not None]
    return {
        "count": len(items),
        "source_health": _overall_health(present),
        "runs": present,
        "assessments": [_serialise(a, _focus_for(a, tags)) for a in items],
    }


def _tags_by_symbol(user: User | None) -> dict[str, tuple[str, ...]]:
    """This caller's focus tags, per company. Empty for a caller we cannot resolve."""
    if user is None:
        return {}
    return {m.symbol: m.tags for m in _USER_STORE.memberships(user.user_id)}


def _focus_for(assessment: Assessment, tags: dict[str, tuple[str, ...]]) -> tuple[FocusMatch, ...]:
    return matches_focus(assessment, tags.get(assessment.event.security_symbol, ()))


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


def _rank(items: list[Assessment]) -> list[Assessment]:
    """Canonical product ordering: severity, then recency (D26).

    Owned by ``core.ranking`` and applied at this boundary so every client — this web
    app, a later mobile client — receives one order. A client that re-derived it would be
    a second, divergent answer to a product question (D2, D30).
    """
    return canonical_order(items)


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


def _serialise(assessment: Assessment, focus: tuple[FocusMatch, ...] = ()) -> dict[str, Any]:
    """View model.

    Coverage travels with the verdict rather than being summarised away: the reader
    must be able to tell a conclusion from an admission.

    ``focus`` is an annotation derived from one user's stated interests. It rides
    alongside the verdict and never alters it: the attention level, confidence,
    corroboration and position in the order are identical for every reader (D27).
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
                "standing": standing_of_publisher(e.publisher, e.tier).value,
                "standing_label": standing_label(standing_of_publisher(e.publisher, e.tier)),
                "subject_company": e.subject_company,
                "published_at": e.published_at.isoformat(),
                "url": e.url,
            }
            for e in event.evidence
        ],
        # Both records stay readable and linked. A dispute is a statement about how sure
        # we are, never a reason to delete what was said (D29).
        "contradiction": {
            "state": event.contradiction.value,
            "disputed_by": event.disputed_by,
            "detail": event.dispute_detail,
            "confirmed": event.contradiction is not ContradictionState.STANDING,
        },
        "source_standing": standing_of(event.evidence).value,
        "source_standing_label": standing_label(standing_of(event.evidence)),
        "focus": [{"tag": m.tag, "label": m.label, "why": m.why} for m in focus],
    }


# --- accounts -----------------------------------------------------------------


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    transport: Literal["cookie", "bearer"] = "cookie"
    """How this client wants to hold the session (D30).

    ``cookie`` — the default — sets an HttpOnly cookie and returns no token, which is why
    a browser's own scripts cannot read it and an XSS cannot steal it. ``bearer`` returns
    the session identifier in the body for a native client that has no cookie jar, and
    sets no cookie.

    Opt-in rather than always returning the token: handing every browser a readable copy
    of its own session to serve a client that is not a browser would weaken the web path
    to make the mobile path convenient.
    """


class SymbolRequest(BaseModel):
    """Adding a company, and what the user says they are watching for.

    Every interest field is optional. The questions are worth asking on the way in — a
    watchlist entry with a stated purpose is worth more than one without — and never
    worth blocking on, so an empty body still adds the company (D27).
    """

    symbol: str = Field(min_length=1, max_length=32)
    reason: str = Field(default="", max_length=500)
    watch_for: str = Field(default="", max_length=500)
    tags: list[str] = Field(default_factory=list, max_length=20)


class WatchPointRequest(BaseModel):
    """What to watch for, and the reason in the reader's own words.

    Exactly one of ``level`` and ``percent`` is given. ``level`` is a price to cross;
    ``percent`` is a signed move — ``-5`` for a five percent fall — measured against the
    price when the point is created and frozen there (D39). Both paths are additive: a
    client that only sends ``level`` behaves exactly as before.
    """

    level: float | None = Field(default=None, gt=0, le=10_000_000)
    percent: float | None = Field(default=None, ge=-100, le=100)
    note: str = Field(default="", max_length=MAX_NOTE)


class AssistantRequest(BaseModel):
    """A question, and the company the reader is looking at if there is one.

    ``symbol`` is UI context, not part of the question: someone on a company page asking
    "why did this fall?" should not have to name it again. Absent, the question is
    answered across the watchlist.
    """

    question: str = Field(min_length=1, max_length=300)
    symbol: str | None = Field(default=None, max_length=32)


class ExplainRequest(BaseModel):
    """A question about one company.

    Bounded length because the explainer answers from a fixed set of stored questions —
    a longer field would invite the conversation the product does not have (VISION §17).
    """

    question: str = Field(min_length=1, max_length=300)


class CompleteRequest(BaseModel):
    review_id: str = Field(min_length=1, max_length=128)
    """The review's identity, not its cutoff. A client returning a timestamp is returning
    a claim; a client returning an id is returning a reference the server can resolve."""


_GENERIC_AUTH_FAILURE = "Registration failed or the email is unavailable."
"""Deliberately uninformative: distinguishing "taken" from other failures confirms that
an account exists."""


# ``exclude_none`` so a cookie login omits the token field entirely rather than sending
# ``"session": null``. The absence is the contract: a browser is never handed a readable
# copy of its own session, not even an empty one it might learn to look for.
@api.post(
    "/auth/register",
    status_code=status.HTTP_201_CREATED,
    response_model=SessionView,
    response_model_exclude_none=True,
)
def register(credentials: Credentials, response: Response) -> dict[str, Any]:
    user = _USER_STORE.create_user(str(credentials.email), credentials.password)
    if user is None:
        raise HTTPException(status.HTTP_409_CONFLICT, _GENERIC_AUTH_FAILURE)
    return _issue_session(user, credentials.transport, response)


@api.post("/auth/login", response_model=SessionView, response_model_exclude_none=True)
def login(credentials: Credentials, response: Response) -> dict[str, Any]:
    user = _USER_STORE.verify_credentials(str(credentials.email), credentials.password)
    if user is None:
        # One message for a wrong password and an unknown account alike.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password.")
    return _issue_session(user, credentials.transport, response)


def _issue_session(user: User, transport: str, response: Response) -> dict[str, Any]:
    """One session record, presented the way the client asked for it (D30)."""
    session = _USER_STORE.create_session(user.user_id)
    body: dict[str, Any] = {
        "user_id": user.user_id,
        "email": user.email,
        "transport": transport,
        "expires_at": session.expires_at.isoformat(),
    }
    if transport == "bearer":
        # No cookie is set: a client that holds the token must not also be handed an
        # ambient credential the browser would attach to every request on its own.
        body["session"] = session.session_id
        return body
    set_session_cookie(response, session.session_id, int(SESSION_LIFETIME.total_seconds()))
    return body


@api.post("/auth/logout", response_model=StatusResponse)
def logout(request: Request, response: Response) -> dict[str, str]:
    """End the session this request presented, by whichever transport carried it.

    Revocation is one path for both clients because there is one session table. A mobile
    client discarding its token locally would leave the row usable by anyone who copied
    it; deleting the row is what actually ends the session.
    """
    session_id = session_id_of(request)
    if session_id:
        _USER_STORE.end_session(session_id)
    clear_session_cookie(response)
    return {"status": "signed out"}


@api.get("/auth/me", response_model=AccountView)
def me(request: Request, user: Annotated[User, Depends(current_user)]) -> dict[str, Any]:
    """Who the caller is, and whether they got there by signing in.

    ``is_demo`` lets the interface skip a sign-in wall it would only be putting in the
    way; it is a statement about how this request resolved, not a capability grant.
    """
    # Resolved from a *valid* session, not from the presence of a cookie: a forged or
    # expired cookie falls through to the demo account, and reporting that as signed-in
    # would have the interface offer to sign out of an account nobody signed into.
    session_id = session_id_of(request)
    signed_in = bool(session_id) and _USER_STORE.user_for_session(session_id) is not None
    return {
        "user_id": user.user_id,
        "email": user.email,
        "demo_mode": demo_mode_enabled(),
        "is_demo": demo_mode_enabled() and not signed_in,
        "transport": ("bearer" if signed_in and COOKIE_NAME not in request.cookies else "cookie"),
    }


# --- watchlist ----------------------------------------------------------------


@api.get("/universe", response_model=UniverseResponse)
def universe() -> dict[str, Any]:
    """The securities a watchlist may contain.

    Exposed so the interface can offer them without keeping a second copy of the curated
    universe that would drift from this one. Data, not a decision — the universe itself is
    still curated in ``core.context``.
    """
    companies = []
    for symbol in curated_symbols():
        context = context_for(symbol, symbol)
        companies.append(
            {
                "symbol": symbol,
                "company": context.name,
                "coverage_tier": context.tier.value,
            }
        )
    return {"companies": companies}


@api.get("/watchlist", response_model=WatchlistResponse)
def watchlist(user: Annotated[User, Depends(current_user)]) -> dict[str, Any]:
    """This user's companies. Scoped by the session, never by a supplied id."""
    return {"companies": [_membership_view(m) for m in _USER_STORE.memberships(user.user_id)]}


@api.get("/focus-tags", response_model=FocusTagsResponse)
def focus_tags() -> dict[str, Any]:
    """The focus vocabulary, so the interface offers exactly what can be matched.

    Served rather than duplicated in the client: a tag a client could send but nothing
    could match would present as the system missing things (D27).
    """
    return {"tags": [{"tag": t.tag, "label": t.label, "because": t.because} for t in FOCUS_TAGS]}


@api.post("/watchlist", response_model=WatchedCompanyView)
def add_to_watchlist(
    body: SymbolRequest, user: Annotated[User, Depends(current_user)]
) -> dict[str, Any]:
    symbol = body.symbol.strip().upper()
    if symbol not in curated_symbols():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"{symbol} is not a supported security. Supported: {', '.join(curated_symbols())}.",
        )
    membership = _USER_STORE.add_membership(
        user.user_id,
        symbol,
        reason=body.reason,
        watch_for=body.watch_for,
        # Unknown tags are dropped rather than stored: the vocabulary is what the match
        # explanation is built from, so a tag with no mapping could never be explained.
        tags=normalise_tags(body.tags),
    )
    return _membership_view(membership)


@api.delete("/watchlist/{symbol}", response_model=RemovedResponse)
def remove_from_watchlist(
    symbol: str, user: Annotated[User, Depends(current_user)]
) -> dict[str, Any]:
    removed = _USER_STORE.remove_membership(user.user_id, symbol.strip().upper())
    return {"symbol": symbol.strip().upper(), "removed": removed}


def _membership_view(membership: Membership) -> dict[str, Any]:
    context = context_for(membership.symbol, membership.symbol)
    return {
        "symbol": membership.symbol,
        "company": context.name,
        "coverage_tier": context.tier.value,
        "added_at": membership.added_at.isoformat(),
        "watched_from": membership.added_at.isoformat(),
        "sector_index": context.sector_index,
        "sector_label": None if context.sector_index is None else index_label(context.sector_index),
        # Private state, returned only to its owner. It never reaches a shared verdict.
        "reason": membership.reason,
        "watch_for": membership.watch_for,
        "tags": list(membership.tags),
    }


# --- price context ------------------------------------------------------------

_RANGES: dict[str, int] = {"1d": 3, "1w": 8, "1m": 31, "3m": 93, "6m": 186, "1y": 366}
"""What a reader may ask for, expressed as a bounded stored-bar lookback."""


@api.get("/prices/status", response_model=PriceStatusesResponse)
def price_statuses(user: Annotated[User, Depends(current_user)]) -> dict[str, Any]:
    """One stored end-of-day price status per watched company (D34)."""
    memberships = _USER_STORE.memberships(user.user_id)
    symbols = [membership.symbol for membership in memberships]
    bars = _STORE.price_bars(symbols)
    return {
        "statuses": [
            _serialise_price_status(build_status(symbol, bars.get(symbol))) for symbol in symbols
        ]
    }


@api.get("/prices/{symbol}", response_model=PriceComparisonView)
def prices(symbol: str, range: str = "6m") -> dict[str, Any]:
    """A company against its sector and the broad market, over sessions they share.

    Context, not a claim. The alignment and the rebasing happen in ``core.prices`` — the
    client draws the points it is given and calculates nothing (D28).
    """
    wanted = symbol.strip().upper()
    if wanted not in curated_symbols():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{wanted} is not a supported security.")
    window = range if range in _RANGES else "6m"

    context = context_for(wanted, wanted)
    symbols = [wanted, BROAD_INDEX] + ([context.sector_index] if context.sector_index else [])
    bars = _STORE.price_bars(symbols)
    since = datetime.now(UTC).date() - timedelta(days=_RANGES[window])

    comparison = build_comparison(
        wanted,
        context.name,
        bars,
        sector_index=context.sector_index,
        sector_label=index_label(context.sector_index or ""),
        broad_index=BROAD_INDEX,
        broad_label=index_label(BROAD_INDEX),
        since=since,
    )
    market_run = _STORE.latest_run(MARKET_SOURCE)
    source_detail = (
        "No stored market run is available yet."
        if market_run is None
        else next(
            (
                record.detail
                for record in market_run.coverage.records
                if record.source == MARKET_SOURCE
            ),
            market_run.detail,
        )
    )
    return _serialise_prices(comparison, window, source_detail)


def _serialise_prices(
    comparison: PriceComparison, window: str, coverage_detail: str
) -> dict[str, Any]:
    return {
        "symbol": comparison.symbol,
        "range": window,
        "basis": "Daily closes, adjusted for splits and dividends, rebased to 100.",
        "sessions": comparison.sessions,
        "covered_from": _iso_date(comparison.covered_from),
        "covered_to": _iso_date(comparison.covered_to),
        "notes": list(comparison.notes),
        "source_detail": coverage_detail,
        "series": [
            {
                "symbol": series.symbol,
                "label": series.label,
                "role": series.role,
                "change_pct": round(series.change_pct, 2),
                "points": [
                    {"on": point.on.isoformat(), "value": round(point.value, 4)}
                    for point in series.points
                ],
            }
            for series in comparison.series
        ],
    }


def _serialise_price_status(status: PriceStatus) -> dict[str, Any]:
    return {
        "symbol": status.symbol,
        "as_of": _iso_date(status.as_of),
        "close": None if status.close is None else round(status.close, 2),
        "daily_change": None if status.daily_change is None else round(status.daily_change, 2),
        "daily_change_pct": (
            None if status.daily_change_pct is None else round(status.daily_change_pct, 2)
        ),
        "day_high": None if status.day_high is None else round(status.day_high, 2),
        "day_low": None if status.day_low is None else round(status.day_low, 2),
        "day_volume": status.day_volume,
        "points": [round(point, 2) for point in status.points],
        "sessions": [
            {"on": session.on.isoformat(), "close": round(session.close, 2)}
            for session in status.sessions
        ],
    }


def _iso_date(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


# --- review -------------------------------------------------------------------


@api.get("/review", response_model=ReviewPageView)
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
    tags = {m.symbol: m.tags for m in memberships}
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
        "needs_attention": _needs_attention(assembled, tags),
        # Surfaced on the next visit rather than pushed. The product is pull-based by
        # design (VISION §17): a level being reached waits for the reader, it does not
        # interrupt them.
        "triggered_watch_points": [
            _watch_point_view(point)
            for point in _USER_STORE.watch_points(user.user_id)
            if point.needs_attention
        ],
        "changed": [_line_view(line, tags) for line in assembled.changed],
        "newly_added": [_line_view(line, tags) for line in assembled.newly_added],
        "unable": [_line_view(line, tags) for line in assembled.unable],
        "quiet": [_line_view(line, tags) for line in assembled.quiet],
    }


@api.post("/review/complete", response_model=CompleteReviewResponse)
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


def _needs_attention(assembled: Review, tags: dict[str, tuple[str, ...]]) -> list[dict[str, Any]]:
    """Everything new since the last completed review, flat and in canonical order.

    Served flattened rather than left for a client to assemble from the per-company
    sections. Order across companies is the product's answer to "what deserves you
    first", and a client stitching sections together would be answering it again —
    differently, and without the engine's verdicts to hand (D26, D22).

    ``NO_MEANINGFUL_CHANGE`` and ``UNABLE_TO_EVALUATE_RELIABLY`` are absent here because
    neither asks anything of the reader. They are not hidden: the review's own sections
    carry them, which is where a coverage gap belongs.
    """
    surfaced = [
        assessment
        for line in (*assembled.changed, *assembled.newly_added)
        for assessment in line.assessments
        if assessment.attention in (Attention.HIGH, Attention.MEDIUM, Attention.LOW)
    ]
    names = {line.symbol: line.company_name for line in assembled.lines}
    ordered = canonical_order(surfaced)

    # Presentation grouping, computed here rather than in each client: the relation is
    # D12's calibrated similarity, and a second implementation in TypeScript would be a
    # second thing to keep calibrated (D43).
    groups = development_ids(ordered)
    by_development: dict[str, list[Assessment]] = {}
    for a in ordered:
        by_development.setdefault(groups[a.event.event_id], []).append(a)
    # Counted over the union of a development's evidence by D13's own rule, so a grouped
    # card cannot overstate corroboration by adding up overlapping publisher counts.
    sources = {
        development: assess_corroboration(
            [e for member in members for e in member.event.evidence]
        ).independent_source_count
        for development, members in by_development.items()
    }

    return [
        {
            "symbol": a.event.security_symbol,
            "company": names.get(a.event.security_symbol, a.event.company_name),
            "assessment": _serialise(a, _focus_for(a, tags)),
            "development_id": groups[a.event.event_id],
            "development_sources": sources[groups[a.event.event_id]],
        }
        for a in ordered
    ]


# --- watch points ---------------------------------------------------------------


@api.get("/watch-points", response_model=WatchPointsResponse)
def list_watch_points(user: Annotated[User, Depends(current_user)]) -> dict[str, Any]:
    """Every level this reader is watching for. Scoped by the session, never by an id."""
    return {"points": [_watch_point_view(p) for p in _USER_STORE.watch_points(user.user_id)]}


@api.post("/companies/{symbol}/watch-points", response_model=WatchPointView)
def add_watch_point(
    symbol: str, body: WatchPointRequest, user: Annotated[User, Depends(current_user)]
) -> dict[str, Any]:
    """Mark a level on one company, with a note saying what to watch out for (D37).

    The direction is inferred once, from the last stored close, and then frozen: a level
    set above today's price is a rise to wait for, and re-deriving that later would flip
    the point's meaning as the price moved.

    A level the company has already closed at is refused rather than created — an alert
    that fires the moment you set it teaches you to ignore it.
    """
    wanted = symbol.strip().upper()
    if wanted not in curated_symbols():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{wanted} is not a supported security.")

    # Stored bars only. Setting a watch point must not reach a price feed any more than
    # asking a question does.
    status_now = build_status(wanted, _STORE.price_bars([wanted]).get(wanted))

    if (body.level is None) == (body.percent is None):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Give either a price level or a percentage move to watch for, not both.",
        )

    if body.percent is not None:
        refusal = percent_rejection_for(body.percent, status_now.close)
        if refusal is not None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, refusal)
        level = abs(body.percent)
        direction = WatchDirection.PERCENT_UP if body.percent > 0 else WatchDirection.PERCENT_DOWN
    else:
        assert body.level is not None  # the exclusivity check above settles this
        refusal = rejection_for(body.level, status_now.close)
        if refusal is not None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, refusal)
        level = body.level
        direction = direction_for(body.level, status_now.close or 0.0)

    assert status_now.close is not None  # both refusals above cover the None case
    point = _USER_STORE.add_watch_point(
        user.user_id, wanted, level, direction, body.note, status_now.close
    )
    return _watch_point_view(point)


@api.post("/watch-points/{point_id}/acknowledge", response_model=WatchPointView)
def acknowledge_watch_point(
    point_id: str, user: Annotated[User, Depends(current_user)]
) -> dict[str, Any]:
    """Mark a triggered point as seen, so it stops asking.

    Deliberately separate from deleting it: the reader may want the record of a level that
    was reached, and dismissing a notice is not the same as saying it never mattered.
    """
    if not _USER_STORE.acknowledge_watch_point(user.user_id, point_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown or untriggered watch point.")
    point = next(
        (p for p in _USER_STORE.watch_points(user.user_id) if p.point_id == point_id), None
    )
    if point is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown watch point.")
    return _watch_point_view(point)


@api.delete("/watch-points/{point_id}", response_model=RemovedResponse)
def remove_watch_point(
    point_id: str, user: Annotated[User, Depends(current_user)]
) -> dict[str, Any]:
    removed = _USER_STORE.remove_watch_point(user.user_id, point_id)
    return {"symbol": point_id, "removed": removed}


def _watch_point_view(point: WatchPoint) -> dict[str, Any]:
    return {
        "point_id": point.point_id,
        "symbol": point.symbol,
        "company": context_for(point.symbol, point.symbol).name,
        "level": point.level,
        "direction": point.direction.value,
        "note": point.note,
        "created_at": point.created_at.isoformat(),
        "created_close": point.created_close,
        "triggered_on": None if point.triggered_on is None else point.triggered_on.isoformat(),
        "triggered_close": point.triggered_close,
        "acknowledged_at": (
            None if point.acknowledged_at is None else point.acknowledged_at.isoformat()
        ),
        "needs_attention": point.needs_attention,
    }


# --- judge mode -----------------------------------------------------------------


if JUDGE_MODE:

    @api.post("/judge/reset", response_model=StatusResponse)
    def judge_reset() -> dict[str, str]:
        """Restore the scenario for the next judge.

        Registered only when the process started in judge mode, so it does not exist as a
        route in live mode — there is nothing to authorise around, and nothing to reach by
        guessing a URL. ``reset`` refuses any database that is not a marked fixture, so a
        misconfigured path fails loudly rather than deleting real records.
        """
        reset(DB_PATH)
        log.info("judge.reset path=%s", DB_PATH)
        return {"status": "demo reset"}


# --- the conversational assistant -----------------------------------------------


@api.post("/assistant/ask", response_model=AssistantAnswerView)
def assistant_ask(
    body: AssistantRequest, user: Annotated[User, Depends(current_user)]
) -> dict[str, Any]:
    """Answer a question about one company or about the whole watchlist (D40).

    **An interface to the existing intelligence, not a second one.** Company questions go
    through exactly the code ``/explain`` uses. Watchlist questions read the same review
    assembly the dashboard reads. Nothing here fetches, scores, ranks or judges — no
    market call, no news call, no model — so a question cannot reach the outside world or
    produce a finding the engine did not already reach.
    """
    symbol = (body.symbol or "").strip().upper()
    if symbol and symbol not in curated_symbols():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{symbol} is not a supported security.")

    intent = resolve_intent(body.question)
    # Company context answers a company question. A watchlist question asked from a
    # company page is answered at the scope it belongs to rather than narrowed to fit.
    if symbol and intent not in WATCHLIST_INTENTS:
        answer = _answer_about_company(symbol, body.question, user)
        return {**answer, "scope": "company", "suggestions": list(SUGGESTIONS)}
    return _answer_about_watchlist(body.question, intent, user)


def _answer_about_watchlist(question: str, intent: Intent, user: User) -> dict[str, Any]:
    """The watchlist as a whole, from the same assembly the dashboard already performs.

    One review assembly and one bounded bar read — the cost of opening the page, not a
    new data path. Nothing is cached separately and nothing is recomputed per message
    beyond this.
    """
    store = _store()
    memberships = _USER_STORE.memberships(user.user_id)
    previous = _USER_STORE.checkpoint(user.user_id)
    now = datetime.now(UTC)

    assembled = assemble(
        user_id=user.user_id,
        memberships=memberships,
        previous_checkpoint=previous,
        review_cutoff=now,
        assessments=_rank(store.recent(500)),
        coverage=_current_coverage(store),
    )
    # Canonical order, produced once by the backend and read as given (D26).
    surfaced = tuple(
        (a.event.security_symbol, a)
        for a in canonical_order(
            [
                a
                for line in (*assembled.changed, *assembled.newly_added)
                for a in line.assessments
                if a.attention in (Attention.HIGH, Attention.MEDIUM, Attention.LOW)
            ]
        )
    )

    symbols = [m.symbol for m in memberships]
    bars = store.price_bars(symbols)
    movers = tuple(
        Mover(
            symbol=symbol,
            company=context_for(symbol, symbol).name,
            change_pct=build_status(symbol, bars.get(symbol)).daily_change_pct,
            as_of=_iso_date(build_status(symbol, bars.get(symbol)).as_of),
        )
        for symbol in symbols
    )
    alerts = tuple(
        AlertLine(
            symbol=point.symbol,
            condition=_condition_text(point),
            note=point.note,
            triggered_on=(None if point.triggered_on is None else point.triggered_on.isoformat()),
            triggered_close=point.triggered_close,
            acknowledged=point.acknowledged_at is not None,
        )
        for point in _USER_STORE.watch_points(user.user_id)
    )

    window = Window(
        start=previous,
        end=now,
        basis=(
            "since your last completed review"
            if previous is not None
            else "across everything we hold"
        ),
        considered=len(surfaced),
    )
    coverage = _current_coverage(store)
    answer = explain_watchlist(
        intent=intent,
        window=window,
        facts=WatchlistFacts(
            company_count=len(memberships), surfaced=surfaced, movers=movers, alerts=alerts
        ),
        coverage=coverage,
    )

    by_id = {a.event.event_id: a for _, a in surfaced}
    cited = [by_id[i] for i in answer.cited_event_ids if i in by_id]
    return {
        "scope": "watchlist",
        "symbol": None,
        "company": None,
        "question": question.strip(),
        "intent": answer.intent.value,
        "answered": answer.answered,
        "window": {
            "from": None if window.start is None else window.start.isoformat(),
            "to": window.end.isoformat(),
            "basis": window.basis,
            "assessments_considered": window.considered,
        },
        "coverage": {
            "complete": coverage.is_complete,
            "note": coverage_status_note(coverage),
            "records": [
                {"source": c.source, "status": c.status.value, "detail": c.detail}
                for c in coverage.records
            ],
        },
        "statements": [{"text": s.text, "event_ids": list(s.event_ids)} for s in answer.statements],
        "evidence": [_evidence_view(e) for a in cited for e in a.event.evidence],
        "insufficient_reason": answer.insufficient_reason,
        "suggestions": list(WATCHLIST_SUGGESTIONS),
        "generated_by": GENERATED_BY,
        "disclaimer": DISCLAIMER,
    }


def _condition_text(point: WatchPoint) -> str:
    """A watch point's condition in words, matching what the detail view shows."""
    if point.direction is WatchDirection.ABOVE:
        return f"at or above {point.level:,.2f}"
    if point.direction is WatchDirection.BELOW:
        return f"at or below {point.level:,.2f}"
    baseline = (
        "an unrecorded price" if point.created_close is None else f"{point.created_close:,.2f}"
    )
    way = "up" if point.direction is WatchDirection.PERCENT_UP else "down"
    return f"{way} {point.level:g}% from {baseline}"


# --- the bounded explainer ------------------------------------------------------

_EXPLAINER_HISTORY = 50
"""How much of a company's record an answer may consider.

Bounded for the same reason every other query here is: a company accumulates evidence
without limit, and an unbounded read is an unbounded response. Newest first, so the
boundary drops the least relevant end.
"""


@api.post("/companies/{symbol}/explain", response_model=ExplainerAnswerView)
def explain_company(
    symbol: str, body: ExplainRequest, user: Annotated[User, Depends(current_user)]
) -> dict[str, Any]:
    """Answer a bounded question about one company, from stored records only (D35).

    **Reads. Never fetches.** No ingestion is triggered, no market feed is called and no
    model is invoked: every fact in the response was already persisted and already served
    by other routes on this API. That is what makes a user's question incapable of
    reaching the outside world, rather than merely discouraged from it.

    The window is the reader's own — their last completed review — because "what changed"
    means something different to two people looking at the same company. The records are
    shared intelligence and identical for both.
    """
    wanted = symbol.strip().upper()
    if wanted not in curated_symbols():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{wanted} is not a supported security.")
    return _answer_about_company(wanted, body.question, user)


def _answer_about_company(symbol: str, question: str, user: User) -> dict[str, Any]:
    """One company's answer. The single implementation behind both callers.

    ``/companies/{symbol}/explain`` and the assistant reach the same records through the
    same code; a second implementation would be a second place for the grounding rules to
    drift (D40).
    """
    store = _store()
    context = context_for(symbol, symbol)
    everything = _rank(store.for_symbol(symbol, _EXPLAINER_HISTORY))

    membership = next(
        (m for m in _USER_STORE.memberships(user.user_id) if m.symbol == symbol), None
    )
    checkpoint = _USER_STORE.checkpoint(user.user_id)
    start = _later(checkpoint, membership.added_at if membership else None)
    in_window = [a for a in everything if start is None or a.assessed_at > start]

    window = Window(
        start=start,
        end=datetime.now(UTC),
        basis=_window_basis(membership is not None, checkpoint is not None),
        considered=len(in_window) if start is not None else len(everything),
    )

    answer = explain(
        intent=resolve_intent(question),
        company=context.name,
        window=window,
        in_window=in_window,
        everything=everything,
        coverage=_current_coverage(store),
    )
    return _serialise_answer(symbol, context.name, question, answer, window, store, everything)


def _window_basis(watched: bool, reviewed: bool) -> str:
    if not watched:
        return "across everything we hold — this company is not on your watchlist"
    if not reviewed:
        return "since you started watching it"
    return "since your last completed review"


def _later(a: datetime | None, b: datetime | None) -> datetime | None:
    """The later of two boundaries, treating absence as no boundary at all."""
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


def _evidence_view(evidence: Evidence) -> dict[str, Any]:
    """One evidence record on the wire, with its standing (D36).

    One serialiser for every caller — an assistant answer and an explainer answer must not
    be able to describe the same source differently.
    """
    standing = standing_of_publisher(evidence.publisher, evidence.tier)
    return {
        "source": evidence.source,
        "ref": evidence.source_ref,
        "tier": evidence.tier.name,
        "publisher": evidence.publisher,
        "standing": standing.value,
        "standing_label": standing_label(standing),
        "subject_company": evidence.subject_company,
        "published_at": evidence.published_at.isoformat(),
        "url": evidence.url,
    }


def _serialise_answer(
    symbol: str,
    company: str,
    question: str,
    answer: Answer,
    window: Window,
    store: SqliteAssessmentStore,
    everything: list[Assessment],
) -> dict[str, Any]:
    """The answer, with the evidence behind every statement travelling beside it.

    Evidence is resolved from the records already read rather than re-queried: a citation
    that pointed at something this response did not contain would be a citation the reader
    cannot check.
    """
    by_id = {a.event.event_id: a for a in everything}
    cited = [by_id[i] for i in answer.cited_event_ids if i in by_id]
    coverage = _current_coverage(store)
    return {
        "symbol": symbol,
        "company": company,
        "question": question.strip(),
        "intent": answer.intent.value,
        "answered": answer.answered,
        "window": {
            "from": None if window.start is None else window.start.isoformat(),
            "to": window.end.isoformat(),
            "basis": window.basis,
            "assessments_considered": window.considered,
        },
        "coverage": {
            "complete": coverage.is_complete,
            "note": coverage_status_note(coverage),
            "records": [
                {"source": c.source, "status": c.status.value, "detail": c.detail}
                for c in coverage.records
            ],
        },
        "statements": [{"text": s.text, "event_ids": list(s.event_ids)} for s in answer.statements],
        "evidence": [_evidence_view(e) for a in cited for e in a.event.evidence],
        "insufficient_reason": answer.insufficient_reason,
        "suggestions": list(SUGGESTIONS),
        "generated_by": GENERATED_BY,
        "disclaimer": DISCLAIMER,
    }


def _line_view(line: CompanyLine, tags: dict[str, tuple[str, ...]]) -> dict[str, Any]:
    return {
        "symbol": line.symbol,
        "company": line.company_name,
        "coverage_tier": line.coverage_tier,
        "state": line.state,
        "detail": line.detail,
        "assessments": [_serialise(a, _focus_for(a, tags)) for a in line.assessments],
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


app.include_router(api, prefix=f"/{API_VERSION}")


# --- serving the built frontend --------------------------------------------------
#
# Optional, and last so it can never shadow an API route. When ``WEB_DIST`` points at a
# built Astro site this process serves it, which makes the deployment one unit with one
# origin — and removes the cross-origin cookie problem rather than configuring around it.
# Absent, the API runs alone exactly as it does in development.
_WEB_DIST = Path(os.environ.get("WEB_DIST", "")) if os.environ.get("WEB_DIST") else None
if _WEB_DIST is not None and _WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_WEB_DIST), html=True), name="web")
    log.info("web.mounted path=%s", _WEB_DIST)
else:
    log.info("web.not_mounted reason=%s", "WEB_DIST unset" if _WEB_DIST is None else "missing")
