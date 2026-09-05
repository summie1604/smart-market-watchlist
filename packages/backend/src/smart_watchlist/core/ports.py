"""The seams.

Protocols rather than concrete classes, so ``core`` states what it needs without
knowing who provides it. This is what keeps the engine testable with no network, no
model and no database, and what makes a source swap a swap rather than a rewrite
(DESIGN.md D5, open question 5).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .models import Assessment, CoverageRecord, Evidence, IngestRun

__all__ = ["AssessmentStore", "DisclosureSource"]


class DisclosureSource(Protocol):
    """An authoritative disclosure feed.

    Returns evidence and a coverage record together, always — including on failure,
    where the evidence is empty and the coverage record says why. A source that fails
    silently would let blindness read as quiet.
    """

    name: str

    def fetch(self) -> tuple[list[Evidence], CoverageRecord]: ...


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
