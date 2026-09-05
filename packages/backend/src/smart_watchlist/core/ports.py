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

    from .market import Bar
    from .models import Assessment, CoverageRecord, Evidence, IngestRun

__all__ = ["AssessmentStore", "DisclosureSource", "MarketSource"]


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


class AssessmentStore(Protocol):
    """Persistence for shared intelligence.

    Writes are idempotent on the source-native reference: re-ingesting the same
    disclosure updates one row rather than creating a second event.
    """

    def save(self, assessment: Assessment) -> None: ...

    def recent(self, limit: int = 50) -> list[Assessment]: ...

    def save_run(self, run: IngestRun) -> None: ...

    """Record that a run happened and what it could see — even when it produced nothing."""

    def latest_run(self, source: str) -> IngestRun | None: ...

    """The most recent run for a source, which is what current source health means."""
