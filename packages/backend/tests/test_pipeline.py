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


def test_an_unconsulted_source_family_is_still_declared(tmp_path) -> None:
    """Every source family this run did not consult is named, never omitted.

    The news adapter exists now, so ``NOT_BUILT_SOURCES`` is empty — but a disclosure run
    that does not consult market or news must still say so, because a verdict produced
    without them is a weaker verdict.
    """
    store = SqliteAssessmentStore(tmp_path / "t.db")

    _run, assessed = run_disclosure_pipeline(FakeDisclosureSource([make_evidence()]), store)

    missing = {r.source for r in assessed[0].coverage.missing}
    assert "market" in missing, "market was not consulted by this run"
    assert not assessed[0].coverage.is_complete


def test_market_data_not_consulted_is_stated_not_omitted(tmp_path) -> None:
    """Market data exists now, so silence about it would be a lie of omission.

    A capability existing elsewhere in the system never licenses a claim that this
    verdict's own evidence and coverage do not support.
    """
    store = SqliteAssessmentStore(tmp_path / "t.db")

    _run, assessed = run_disclosure_pipeline(
        FakeDisclosureSource([make_evidence()]), store, market=None
    )

    market = next(r for r in assessed[0].coverage.records if r.source == "market")
    assert market.status is not CoverageStatus.OK
    assert "not consulted" in market.detail.lower()


def test_provenance_survives_the_round_trip(tmp_path) -> None:
    """Step 0's actual claim: the architecture preserves provenance end to end."""
    store = SqliteAssessmentStore(tmp_path / "t.db")
    run_disclosure_pipeline(FakeDisclosureSource([make_evidence(ref="106770850")]), store)

    evidence = store.recent()[0].event.evidence[0]

    assert evidence.source_ref == "106770850"
    assert evidence.tier.name == "OFFICIAL_DISCLOSURE"
    assert evidence.url.startswith("https://")
    assert evidence.retrieved_at is not None
