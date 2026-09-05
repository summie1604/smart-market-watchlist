"""The product's load-bearing claim: silence is only reported when we actually looked.

These cover the failure the code review found — coverage was computed and then thrown
away whenever a run produced no assessments, so a failed ingest left the previous run's
healthy coverage standing as though it were current.
"""

from __future__ import annotations

from datetime import UTC, datetime

from support import make_evidence

from smart_watchlist.adapters.sqlite_store import SqliteAssessmentStore
from smart_watchlist.core.models import CoverageRecord, CoverageStatus, Evidence
from smart_watchlist.core.pipeline import run_disclosure_pipeline

SOURCE = "nse-disclosures"


class StubSource:
    """A disclosure source whose health the test controls."""

    name = SOURCE

    def __init__(self, evidence: list[Evidence], status: CoverageStatus) -> None:
        self._evidence = evidence
        self._status = status

    def fetch(self) -> tuple[list[Evidence], CoverageRecord]:
        return self._evidence, CoverageRecord(
            source=self.name,
            status=self._status,
            observed_at=datetime.now(UTC),
            detail=f"stub: {self._status.value}",
        )


def healthy() -> StubSource:
    return StubSource([make_evidence()], CoverageStatus.OK)


def unreachable() -> StubSource:
    return StubSource([], CoverageStatus.UNAVAILABLE)


def test_a_failed_ingest_persists_its_coverage_even_with_zero_assessments(tmp_path) -> None:
    """A run that saw nothing still happened, and the store must say so."""
    store = SqliteAssessmentStore(tmp_path / "t.db")

    run, assessments = run_disclosure_pipeline(unreachable(), store)

    assert assessments == []
    assert run.assessed_count == 0
    assert not run.is_healthy

    persisted = store.latest_run(SOURCE)
    assert persisted is not None, "a failed run must leave a record, not nothing"
    assert not persisted.is_healthy
    statuses = {r.source: r.status for r in persisted.coverage.records}
    assert statuses[SOURCE] is CoverageStatus.UNAVAILABLE


def test_an_empty_but_successful_feed_is_healthy_not_failed(tmp_path) -> None:
    """A quiet exchange is a conclusion. It must not read as an outage."""
    store = SqliteAssessmentStore(tmp_path / "t.db")

    run, assessments = run_disclosure_pipeline(StubSource([], CoverageStatus.OK), store)

    assert assessments == []
    assert run.is_healthy


def test_yesterdays_success_does_not_imply_todays_source_health(tmp_path) -> None:
    """The regression the review caught.

    Older assessments legitimately remain on display. What must not survive is the
    impression that the sources behind them are currently healthy.
    """
    store = SqliteAssessmentStore(tmp_path / "t.db")

    run_disclosure_pipeline(healthy(), store)
    assert store.latest_run(SOURCE) is not None
    assert store.latest_run(SOURCE).is_healthy  # type: ignore[union-attr]

    run_disclosure_pipeline(unreachable(), store)

    assert len(store.recent()) == 1, "the earlier verdict is still shown"
    latest = store.latest_run(SOURCE)
    assert latest is not None
    assert not latest.is_healthy, "but current source health must reflect the failed run"


def test_source_health_is_readable_without_any_assessments(tmp_path) -> None:
    """Health must not be reachable only through an assessment that may not exist."""
    store = SqliteAssessmentStore(tmp_path / "t.db")

    run_disclosure_pipeline(unreachable(), store)

    assert store.recent() == []
    assert store.latest_run(SOURCE) is not None


def test_no_run_at_all_is_distinguishable_from_a_failed_run(tmp_path) -> None:
    """Never looked and looked-and-failed are different, and both differ from quiet."""
    store = SqliteAssessmentStore(tmp_path / "t.db")

    assert store.latest_run(SOURCE) is None

    run_disclosure_pipeline(unreachable(), store)
    assert store.latest_run(SOURCE) is not None


def test_a_run_with_no_record_for_its_own_source_is_not_healthy() -> None:
    """Absence of a failure record is not evidence of success.

    `all()` over an empty sequence is True, so this would otherwise report healthy —
    the same absence-reads-as-OK mistake the product exists to avoid, turned inward.
    """
    from smart_watchlist.core.models import Coverage, IngestRun

    now = datetime.now(UTC)
    run = IngestRun(
        run_id="x",
        source=SOURCE,
        started_at=now,
        coverage=Coverage(
            records=(
                CoverageRecord(source="market", status=CoverageStatus.NOT_BUILT, observed_at=now),
            )
        ),
        assessed_count=0,
    )

    assert not run.is_healthy
