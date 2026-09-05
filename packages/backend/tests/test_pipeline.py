"""The spine, exercised with a fake source.

The fake implements the same protocol as the NSE adapter and returns evidence, not
verdicts — so this test covers the real normalization, engine and persistence path.
"""

from __future__ import annotations

from datetime import UTC, datetime

from support import make_evidence

from smart_watchlist.adapters.sqlite_store import SqliteAssessmentStore
from smart_watchlist.core.models import CoverageRecord, CoverageStatus, Evidence
from smart_watchlist.core.pipeline import run_disclosure_pipeline


class FakeDisclosureSource:
    """A stand-in for the exchange. Implements ``DisclosureSource``."""

    name = "fake-disclosures"

    def __init__(self, evidence: list[Evidence], status: CoverageStatus = CoverageStatus.OK):
        self._evidence = evidence
        self._status = status

    def fetch(self) -> tuple[list[Evidence], CoverageRecord]:
        return self._evidence, CoverageRecord(
            source=self.name,
            status=self._status,
            observed_at=datetime.now(UTC),
            detail="",
        )


def test_evidence_becomes_a_persisted_assessment(tmp_path) -> None:
    store = SqliteAssessmentStore(tmp_path / "t.db")
    source = FakeDisclosureSource([make_evidence()])

    _run, assessed = run_disclosure_pipeline(source, store)

    assert len(assessed) == 1
    stored = store.recent()
    assert len(stored) == 1
    assert stored[0].event.security_symbol == "TATAMOTORS"
    assert stored[0].reasons, "a persisted verdict must keep the reasons that produced it"


def test_reingesting_the_same_disclosure_does_not_duplicate_it(tmp_path) -> None:
    store = SqliteAssessmentStore(tmp_path / "t.db")
    source = FakeDisclosureSource([make_evidence(ref="same-ref")])

    run_disclosure_pipeline(source, store)
    run_disclosure_pipeline(source, store)

    assert len(store.recent()) == 1


def test_unbuilt_source_families_are_declared_as_missing_coverage(tmp_path) -> None:
    """An expected source that does not exist yet is a coverage gap, not silence."""
    store = SqliteAssessmentStore(tmp_path / "t.db")

    _run, assessed = run_disclosure_pipeline(FakeDisclosureSource([make_evidence()]), store)

    missing = {r.source for r in assessed[0].coverage.missing}
    assert {"market", "news"} <= missing
    assert not assessed[0].coverage.is_complete


def test_provenance_survives_the_round_trip(tmp_path) -> None:
    """Step 0's actual claim: the architecture preserves provenance end to end."""
    store = SqliteAssessmentStore(tmp_path / "t.db")
    run_disclosure_pipeline(FakeDisclosureSource([make_evidence(ref="106770850")]), store)

    evidence = store.recent()[0].event.evidence[0]

    assert evidence.source_ref == "106770850"
    assert evidence.tier.name == "OFFICIAL_DISCLOSURE"
    assert evidence.url.startswith("https://")
    assert evidence.retrieved_at is not None
