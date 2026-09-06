"""The wire contract.

Declared once, in one place, because it is the thing two clients agree on. The web app
and a later mobile client do not read this file — they read the TypeScript generated from
it (``make api-types``), which is what stops a client's idea of an assessment from drifting
away from the server's without anyone noticing (D33).

These are *view* models, not domain models. The domain types in ``core.models`` are free
to change shape; this layer is where a change becomes a promise to somebody else. Keeping
them apart is what lets the engine be refactored without breaking a shipped app, and what
makes an actual breaking change visible as a diff in this file.

Every field is required unless the server can genuinely omit it. An optional field that is
always present teaches a client to write defensive code it does not need; a required field
that is sometimes missing teaches it to crash.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

__all__ = [
    "AccountView",
    "AssessmentView",
    "AssessmentsResponse",
    "AssistantAnswerView",
    "AttentionItemView",
    "CompleteReviewResponse",
    "ContradictionView",
    "CorroborationView",
    "CoverageRecordView",
    "CoverageView",
    "EvidenceRefView",
    "ExplainerAnswerView",
    "ExplainerStatementView",
    "ExplainerWindowView",
    "FocusMatchView",
    "FocusTagView",
    "FocusTagsResponse",
    "IngestResponse",
    "MetaResponse",
    "PriceComparisonView",
    "PricePointView",
    "PriceSeriesView",
    "PriceSessionView",
    "PriceStatusView",
    "PriceStatusesResponse",
    "ReasonView",
    "RemovedResponse",
    "ReviewLineView",
    "ReviewPageView",
    "RunView",
    "SchedulerResponse",
    "SessionView",
    "StatusResponse",
    "UniverseCompanyView",
    "UniverseResponse",
    "WatchPointRejection",
    "WatchPointView",
    "WatchPointsResponse",
    "WatchedCompanyView",
    "WatchlistResponse",
]

Attention = Literal["HIGH", "MEDIUM", "LOW", "NO_MEANINGFUL_CHANGE", "UNABLE_TO_EVALUATE_RELIABLY"]
Confidence = Literal["HIGH", "MEDIUM", "LOW"]
ContradictionState = Literal["STANDING", "DISPUTED", "WITHDRAWN"]
SourceStanding = Literal[
    "OFFICIAL", "ESTABLISHED", "SYNDICATED_RELEASE", "UNRECOGNISED", "COMPUTED"
]
RowState = Literal["changed", "quiet", "unable", "new"]


class ReasonView(BaseModel):
    """One signed contribution to a verdict. The verdict *is* these (D4)."""

    code: str
    direction: Literal["+", "-"]
    contribution: int
    detail: str


class CoverageRecordView(BaseModel):
    source: str
    status: str
    detail: str


class CoverageView(BaseModel):
    """What could and could not be consulted. A domain input, never logging (D15)."""

    complete: bool
    note: str
    records: list[CoverageRecordView]


class EvidenceRefView(BaseModel):
    source: str
    ref: str
    tier: str
    publisher: str
    """Who published it — never who it is about."""
    standing: SourceStanding
    """What kind of source this is. Descriptive, never a rating: ``UNRECOGNISED`` means
    absent from a curated list, not untrustworthy."""
    standing_label: str
    subject_company: str
    published_at: str
    url: str


class CorroborationView(BaseModel):
    """Independent publishers, not article count (D13). Repetition is not confirmation."""

    article_count: int
    independent_source_count: int
    summary: str
    has_authoritative: bool


class ContradictionView(BaseModel):
    """Where an event stands after everything published since (D29)."""

    state: ContradictionState
    disputed_by: str | None
    detail: str
    confirmed: bool
    """False with a link present means *possibly related*, never *contradicted*."""


class FocusMatchView(BaseModel):
    """Why an event was relevant to what this reader said they watch for (D27)."""

    tag: str
    label: str
    why: str


class AssessmentView(BaseModel):
    """One verdict, and everything needed to argue with it."""

    event_id: str
    symbol: str
    company: str
    event_type: str
    description: str
    occurred_at: str
    attention: Attention
    confidence: Confidence
    """A separate axis from attention, never blended into it."""
    score: int
    scoring_version: str
    reasons: list[ReasonView]
    coverage: CoverageView
    corroboration: CorroborationView
    evidence: list[EvidenceRefView]
    contradiction: ContradictionView
    source_standing: SourceStanding
    """The strongest standing among this event's evidence. A separate axis from attention
    and from confidence: what kind of source said it, not how much it matters."""
    source_standing_label: str
    focus: list[FocusMatchView]
    """Annotation derived from private state. It never altered anything above it."""


class RunView(BaseModel):
    run_id: str
    source: str
    started_at: str
    assessed_count: int
    healthy: bool
    records: list[CoverageRecordView]


class AssessmentsResponse(BaseModel):
    count: int
    source_health: RunView | None
    """``null`` means nothing has ever run — not that a run failed."""
    runs: list[RunView]
    assessments: list[AssessmentView]


class WatchPointView(BaseModel):
    """A level this reader asked to be told about, and where it stands.

    Private state. It never becomes an assessment, never changes an attention level, and
    is never visible to another reader.
    """

    point_id: str
    symbol: str
    company: str
    level: float
    """A price for ABOVE/BELOW, a percentage magnitude for the percentage directions."""
    direction: Literal["ABOVE", "BELOW", "PERCENT_UP", "PERCENT_DOWN"]
    note: str
    created_at: str
    created_close: float | None
    """The last stored close when the point was set. For a percentage point this is the
    frozen baseline the move is measured from (D39)."""
    triggered_on: str | None
    """The session that satisfied it. An end-of-day close, never an intraday touch."""
    triggered_close: float | None
    acknowledged_at: str | None
    needs_attention: bool
    """Triggered and not yet seen. The only state that asks anything of the reader."""


class AttentionItemView(BaseModel):
    """One item the review says is new. Served flat and already ordered (D26)."""

    symbol: str
    company: str
    assessment: AssessmentView
    development_id: str
    """The development this record belongs to, for presentation grouping (D43).

    Equal to the primary record's ``event_id``; an ungrouped item points at itself. It is
    a display key, not event identity — every record keeps its own id, score, reason codes
    and evidence, and nothing was merged to produce it."""
    development_sources: int
    """Independent publishers across the whole development, counted by D13's own rule so a
    grouped card never overstates its corroboration by summing overlapping counts."""


class ReviewLineView(BaseModel):
    symbol: str
    company: str
    coverage_tier: str
    state: RowState
    detail: str
    assessments: list[AssessmentView]


class ReviewPageView(BaseModel):
    review_id: str
    """The identity a client returns to complete this review. Never its cutoff: a client
    returning a timestamp is returning a claim (D7)."""
    previous_checkpoint: str | None
    review_cutoff: str
    attention_count: int
    needs_attention: list[AttentionItemView]
    triggered_watch_points: list[WatchPointView]
    """Levels this reader asked about that a stored close has since crossed, and which
    they have not yet acknowledged. Carried beside the assessments rather than mixed into
    them: one is a verdict about evidence, the other is the reader's own bookmark (D37)."""
    changed: list[ReviewLineView]
    newly_added: list[ReviewLineView]
    unable: list[ReviewLineView]
    quiet: list[ReviewLineView]


class CompleteReviewResponse(BaseModel):
    checkpoint: str
    outcome: Literal["advanced", "already-at-this-cutoff", "stale-cutoff-ignored"]


class WatchedCompanyView(BaseModel):
    symbol: str
    company: str
    coverage_tier: str
    added_at: str
    watched_from: str
    sector_index: str | None
    sector_label: str | None
    """The index a move is judged against, in a reader's words rather than as a ticker."""
    reason: str
    """Private to its owner, and never parsed into behaviour."""
    watch_for: str
    tags: list[str]


class WatchlistResponse(BaseModel):
    companies: list[WatchedCompanyView]


class RemovedResponse(BaseModel):
    symbol: str
    removed: bool


class UniverseCompanyView(BaseModel):
    symbol: str
    company: str
    coverage_tier: str


class UniverseResponse(BaseModel):
    companies: list[UniverseCompanyView]


class FocusTagView(BaseModel):
    tag: str
    label: str
    because: str


class FocusTagsResponse(BaseModel):
    tags: list[FocusTagView]


class AccountView(BaseModel):
    user_id: str
    email: str
    demo_mode: bool
    is_demo: bool
    transport: Literal["cookie", "bearer"]


class SessionView(BaseModel):
    """What signing in returns. ``session`` is present only for a bearer client (D30)."""

    user_id: str
    email: str
    transport: Literal["cookie", "bearer"]
    expires_at: str
    session: str | None = None


class StatusResponse(BaseModel):
    status: str


class PricePointView(BaseModel):
    on: str
    value: float
    """Rebased to 100 at the first shared session — a relative level, never a price."""


class PriceSeriesView(BaseModel):
    symbol: str
    label: str
    role: Literal["security", "sector", "broad"]
    change_pct: float
    points: list[PricePointView]


class PriceComparisonView(BaseModel):
    """Context, not a claim. Aligned and rebased server-side (D28)."""

    symbol: str
    range: str
    basis: str
    sessions: int
    covered_from: str | None
    covered_to: str | None
    notes: list[str]
    """Everything needed to trust or discount the picture, in the reader's language."""
    source_detail: str
    series: list[PriceSeriesView]


class PriceSessionView(BaseModel):
    """One stored end-of-day session behind a card's trace."""

    on: str
    close: float


class PriceStatusView(BaseModel):
    """Stored end-of-day price context for one watchlist card (D34)."""

    symbol: str
    as_of: str | None
    """The session these figures describe. End-of-day, never a live quote (D28)."""
    close: float | None
    daily_change: float | None
    """The move in rupees. Derived from the two stored closes, not persisted."""
    daily_change_pct: float | None
    day_high: float | None
    """The session range where the provider gave one. ``null`` means it did not."""
    day_low: float | None
    day_volume: float | None
    points: list[float]
    """Closes alone. Kept for clients that only draw a line."""
    sessions: list[PriceSessionView]
    """The same closes with their dates, so a reader pointing at the trace is told which
    day rather than left to guess one."""


class PriceStatusesResponse(BaseModel):
    statuses: list[PriceStatusView]


class MetaResponse(BaseModel):
    """What this API is, so a client can refuse to guess."""

    api_version: str
    scoring_version: str
    mode: Literal["live", "judge"]
    """``judge`` means every record on screen is a simulated scenario, seeded through the
    real pipelines. Clients must label it (D42)."""
    demo_mode: bool
    attention_levels: list[str]
    confidence_levels: list[str]
    contradiction_states: list[str]
    focus_tags: list[str]
    price_ranges: list[str]
    source_families: list[str]


class IngestResponse(BaseModel):
    outcome: str
    assessed: int
    healthy_families: list[str]
    failed_families: list[str]
    runs: list[RunView]


class SchedulerResponse(BaseModel):
    enabled: bool
    started: bool
    cycle_active: bool
    interval_seconds: float
    cycles_completed: int
    next_run_at: str | None = None
    last_cycle: dict[str, object] | None = Field(default=None)


# --- the bounded explainer (D35) ------------------------------------------------


class ExplainerStatementView(BaseModel):
    """One factual sentence and the stored events it came from.

    ``event_ids`` is empty only for a refusal or a pointer to the suggestions. A statement
    about the company always names the records behind it, so a reader can check any claim
    against the evidence the same response already carries.
    """

    text: str
    event_ids: list[str]


class ExplainerWindowView(BaseModel):
    """The evidence window an answer speaks for. Present on every response, including
    refusals — a reader must never have to infer how far back an answer looked."""

    from_: str | None = Field(alias="from", serialization_alias="from")
    to: str
    basis: str
    assessments_considered: int

    model_config = {"populate_by_name": True}


class ExplainerAnswerView(BaseModel):
    """An answer composed only from persisted records (D35).

    ``answered=false`` is a normal outcome, not an error: out of scope, unsupported, or
    simply nothing on file. Each carries an ``insufficient_reason`` so a client can say
    *why* rather than showing an empty box.
    """

    symbol: str
    company: str
    question: str
    intent: str
    answered: bool
    window: ExplainerWindowView
    coverage: CoverageView
    """Source-by-source, as recorded. Stated whether or not it was asked about."""
    statements: list[ExplainerStatementView]
    evidence: list[EvidenceRefView]
    """Every cited event's evidence, so each statement can be followed to a source."""
    insufficient_reason: str | None
    suggestions: list[str]
    generated_by: str
    """Which answer path produced this. No model participates in the deterministic one."""
    disclaimer: str


# --- watch points (D37) ---------------------------------------------------------


class WatchPointsResponse(BaseModel):
    points: list[WatchPointView]


class WatchPointRejection(BaseModel):
    """Why a level could not be set, in the reader's words."""

    detail: str


# --- the conversational assistant (D40) -----------------------------------------


class AssistantAnswerView(BaseModel):
    """One assistant reply.

    A thin envelope around exactly the same parts an ``/explain`` answer carries — the
    statements, the window, the coverage and the cited evidence. It is a separate model
    only because the scope differs: a watchlist answer has no single company. Nothing here
    is a second taxonomy for anything (D40).
    """

    scope: Literal["company", "watchlist"]
    symbol: str | None
    company: str | None
    question: str
    intent: str
    answered: bool
    window: ExplainerWindowView
    coverage: CoverageView
    statements: list[ExplainerStatementView]
    evidence: list[EvidenceRefView]
    """Cited evidence, carrying the same source standing labels the rest of the product
    uses (D36) — never a credibility scheme invented for chat."""
    insufficient_reason: str | None
    suggestions: list[str]
    generated_by: str
    disclaimer: str
