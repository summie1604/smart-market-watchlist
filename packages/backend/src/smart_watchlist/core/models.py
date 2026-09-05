"""Domain types.

Contract-first: these shapes are decisions, and they encode two boundaries that
`DESIGN.md` treats as load-bearing.

*Evidence is not fact.* An :class:`Evidence` record says a source said something at a
time. An :class:`EventCandidate` says we read that as a claim about a company. Only an
:class:`Assessment` says it deserves attention, and it carries the reason codes that
produced that verdict.

*Coverage constrains what may be concluded.* A verdict computed while a source family
was missing is a different verdict, and :class:`Coverage` travels with it so nothing
downstream can forget.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

__all__ = [
    "Assessment",
    "Attention",
    "Confidence",
    "Coverage",
    "CoverageRecord",
    "CoverageStatus",
    "Event",
    "EventCandidate",
    "Evidence",
    "IngestRun",
    "ReasonCode",
    "SourceTier",
]


class SourceTier(Enum):
    """How much epistemic weight a source carries (VISION.md §12).

    Ordered deliberately: comparisons decide confidence, so the order is the claim.
    """

    COMPUTED = 5
    """Derived by us from primary data — a price change, a volume ratio."""
    OFFICIAL_DISCLOSURE = 4
    """Exchange filing, regulatory decision, company statement."""
    CREDIBLE_REPORTING = 3
    """Established outlet, attributed."""
    SOCIAL_DISCUSSION = 2
    """Real as a signal of attention; never as evidence of fact."""
    INFERENCE = 1
    """Our own conclusion. Labelled as ours, never laundered into apparent fact."""


class Attention(Enum):
    """What the system asks of the user. Deliberately not BUY/SELL/HOLD (VISION.md §6)."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NO_MEANINGFUL_CHANGE"
    UNABLE = "UNABLE_TO_EVALUATE_RELIABLY"


class Confidence(Enum):
    """How sure we are — a separate axis from attention, never blended into it."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class CoverageStatus(Enum):
    """Whether a source family could be consulted for a given window."""

    OK = "OK"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_BUILT = "NOT_BUILT"
    """Honest about the build: this source family does not exist yet."""


@dataclass(frozen=True)
class CoverageRecord:
    """One source family's availability for one ingestion window."""

    source: str
    status: CoverageStatus
    observed_at: datetime
    detail: str = ""


@dataclass(frozen=True)
class Coverage:
    """What could and could not be consulted when a verdict was produced.

    This is a domain input, not logging. It is what separates "nothing happened" from
    "we could not look" (DESIGN.md D15).
    """

    records: tuple[CoverageRecord, ...]

    @property
    def missing(self) -> tuple[CoverageRecord, ...]:
        """Source families that could not be consulted."""
        return tuple(r for r in self.records if r.status is not CoverageStatus.OK)

    @property
    def is_complete(self) -> bool:
        """True only when every expected source family was consulted successfully."""
        return not self.missing


@dataclass(frozen=True)
class Evidence:
    """Something a source said, at a time. Never an interpretation.

    ``source_ref`` is the source-native identifier, and it is what makes re-fetching
    idempotent: the same disclosure ingested twice is one row, not two.
    """

    source: str
    source_ref: str
    tier: SourceTier
    publisher: str
    """The organisation that published this — the exchange, the wire, the outlet.

    Not the company the evidence is *about*. For a filing those differ (the NSE
    published it; the company is its subject), and for news they always differ.
    """
    subject_company: str
    """The company this evidence concerns. The only source of company identity.

    Derived from ``publisher`` would be wrong the moment a news adapter lands: Reuters
    publishes, Tata Motors is the subject.
    """
    retrieved_at: datetime
    published_at: datetime
    title: str
    body: str
    url: str
    security_symbol: str
    category: str = ""
    """The source's own classification, verbatim. Empty for sources that do not classify.

    Kept as the source stated it rather than mapped on ingest: a category we translated
    is an interpretation, and interpretations belong downstream of evidence.
    """


@dataclass(frozen=True)
class EventCandidate:
    """A claim derived from evidence — structured, and still not a fact.

    ``extraction`` records how the claim was produced. Step 0 reads structured
    disclosure fields, so extraction is deterministic and says so; when a model is
    involved it names the model, prompt and schema version instead (DESIGN.md D5).
    """

    security_symbol: str
    company_name: str
    event_type: str
    description: str
    occurred_at: datetime
    evidence_refs: tuple[str, ...]
    extraction: str


@dataclass(frozen=True)
class Event:
    """A candidate that has been given identity.

    Step 0 creates one event per candidate. Linking, and the AMBIGUOUS outcome that
    holds the merge rather than the event, arrive with D12 in step 2.
    """

    event_id: str
    security_symbol: str
    company_name: str
    event_type: str
    description: str
    occurred_at: datetime
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class ReasonCode:
    """One signed contribution to an attention decision.

    These are the decision, not a commentary on it. An attention level that cannot
    produce its reason codes cannot be ranked (DESIGN.md D4).
    """

    code: str
    contribution: int
    detail: str

    @property
    def direction(self) -> str:
        """``+`` argued for surfacing, ``-`` argued against."""
        return "+" if self.contribution >= 0 else "-"


@dataclass(frozen=True)
class IngestRun:
    """One pass of the pipeline, and what it could see.

    Persisted whether or not it produced assessments. A run that fetched nothing still
    happened, and the record of *why* it produced nothing is the difference between
    "nothing changed" and "we could not look" (DESIGN.md D15).
    """

    run_id: str
    source: str
    started_at: datetime
    coverage: Coverage
    assessed_count: int

    @property
    def is_healthy(self) -> bool:
        """True when the source family this run targeted was consulted successfully.

        A run carrying no record for its own source is *not* healthy. Absence of a
        failure record is not evidence of success — the same distinction the product
        makes between "nothing changed" and "we could not look", applied to itself.
        """
        own = [r for r in self.coverage.records if r.source == self.source]
        return bool(own) and all(r.status is CoverageStatus.OK for r in own)


@dataclass(frozen=True)
class Assessment:
    """A verdict about one event, and the record of how it was reached."""

    event: Event
    attention: Attention
    confidence: Confidence
    reasons: tuple[ReasonCode, ...]
    coverage: Coverage
    scoring_version: str
    assessed_at: datetime
    score: int = field(default=0)
