"""The seams.

Protocols rather than concrete classes, so ``core`` states what it needs without
knowing who provides it. This is what keeps the engine testable with no network, no
model and no database, and what makes a source swap a swap rather than a rewrite
(DESIGN.md D5, open question 5).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import date, datetime

    from .extraction import ExtractedEvent
    from .market import Bar
    from .models import Assessment, ContradictionState, CoverageRecord, Evidence, IngestRun
    from .watchpoints import WatchPoint

__all__ = [
    "AssessmentStore",
    "DisclosureSource",
    "Extractor",
    "MarketSource",
    "NewsSource",
    "WatchPointStore",
]


class DisclosureSource(Protocol):
    """An authoritative disclosure feed.

    Returns evidence and a coverage record together, always — including on failure,
    where the evidence is empty and the coverage record says why. A source that fails
    silently would let blindness read as quiet.
    """

    name: str

    def fetch(self) -> tuple[list[Evidence], CoverageRecord]: ...


class MarketSource(Protocol):
    """Primary price and volume data.

    Returns bars per symbol plus one coverage record. A symbol absent from the mapping
    has no data — which the caller must treat as missing coverage, never as a calm
    session.
    """

    name: str

    def fetch(self, symbols: Sequence[str]) -> tuple[dict[str, list[Bar]], CoverageRecord]: ...


class NewsSource(Protocol):
    """Articles about companies, from publishers that are not the companies."""

    name: str

    def fetch(
        self, companies: Sequence[tuple[str, str]]
    ) -> tuple[list[Evidence], CoverageRecord]: ...


class Extractor(Protocol):
    """Proposes structure from evidence. Never asserts it.

    Returns ``None`` when it cannot produce anything it can support — unavailable,
    malformed, or simply unrecognisable. The caller degrades; it does not crash.
    """

    name: str

    def extract(self, evidence: Evidence) -> ExtractedEvent | None: ...


class AssessmentStore(Protocol):
    """Persistence for shared intelligence.

    Writes are idempotent on the source-native reference: re-ingesting the same
    disclosure updates one row rather than creating a second event.
    """

    def save(
        self,
        assessment: Assessment,
        extraction: dict[str, object] | None = None,
        link_state: str | None = None,
    ) -> None: ...

    def get(self, event_id: str) -> Assessment | None: ...

    """One event by id — linking must reach events of any age."""

    def recent(self, limit: int = 50) -> list[Assessment]: ...

    def for_symbol(self, symbol: str, limit: int = 50) -> list[Assessment]: ...

    """One company's record, newest first and bounded — never a filtered full scan."""

    def set_contradiction(
        self, event_id: str, state: ContradictionState, disputed_by: str, detail: str
    ) -> bool: ...

    """Record how an earlier event stands once something later contradicted it (D29).

    Narrow deliberately: it changes what we can say about a claim, never the verdict the
    engine reached when the claim was made."""

    def candidates(
        self, symbol: str, event_type: str, since: datetime
    ) -> list[tuple[Assessment, dict[str, object] | None]]: ...

    """Events that could be the same occurrence — bucketed, not identified (D12)."""

    def save_run(self, run: IngestRun) -> None: ...

    """Record that a run happened and what it could see — even when it produced nothing."""

    def save_price_bars(self, bars: dict[str, list[Bar]]) -> None: ...

    def price_bars(self, symbols: list[str]) -> dict[str, list[Bar]]: ...

    """Stored EOD context. API reads never trigger a provider call (D3, D28)."""

    def latest_run(self, source: str) -> IngestRun | None: ...

    """The most recent run for a source, which is what current source health means."""

    def fail_running_runs(self, source: str, detail: str, finished_at: datetime) -> int: ...

    """Reconcile in-flight runs for a source into a failed state."""

    def reap_interrupted_runs(self) -> int: ...

    """Marks runs left RUNNING by a dead process as interrupted."""

    def record_rejection(
        self, evidence: Evidence, reason: str, extractor: str, recorded_at: datetime
    ) -> None: ...

    """Preserve an article we refused to interpret, with the reason."""

    def delete_assessment(self, event_id: str) -> bool: ...

    """The most recent run for a source, which is what current source health means."""


class WatchPointStore(Protocol):
    """The private levels readers asked to be told about (D37).

    A separate port from :class:`AssessmentStore` because the data is separate: watch
    points belong to one person, assessments belong to everyone. An ingestion cycle needs
    both and is the only thing that does.
    """

    def open_watch_points(self) -> list[WatchPoint]: ...

    """Every untriggered point, across readers. Triggered ones are never re-examined."""

    def mark_triggered(self, point_id: str, on: date, close: float) -> bool: ...

    """Record the session that satisfied a point. False when it already had one, which is
    what makes re-running a cycle announce nothing twice."""
