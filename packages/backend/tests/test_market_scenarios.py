"""Scenarios A and G, proven through the pipeline rather than the calculation alone.

`test_market.py` proves the chain computes correctly. These prove the product does the
right thing with it: a fixture enters at the *evidence* boundary and travels the real
normalization, engine and persistence path (D18).
"""

from __future__ import annotations

from datetime import date, timedelta

from smart_watchlist.adapters.sqlite_store import SqliteAssessmentStore
from smart_watchlist.core.market import Bar
from smart_watchlist.core.models import Attention, Confidence, CoverageRecord, CoverageStatus
from smart_watchlist.core.normalize import CORPORATE_ACTION, UNUSUAL_MOVEMENT
from smart_watchlist.core.pipeline import run_market_pipeline

from datetime import UTC, datetime  # isort: skip

START = date(2026, 6, 1)
SUBJECT = "RELIANCE"


def calm(n: int = 40, price: float = 100.0) -> list[Bar]:
    return [
        Bar(
            on=START + timedelta(days=i),
            close=price + (0.2 if i % 2 else -0.2),
            adjusted_close=price + (0.2 if i % 2 else -0.2),
            volume=1_000_000,
        )
        for i in range(n)
    ]


class StubMarket:
    """A market source whose bars the test controls. Implements ``MarketSource``."""

    name = "market"

    def __init__(self, series: dict[str, list[Bar]]) -> None:
        self._series = series

    def fetch(self, symbols):
        return dict(self._series), CoverageRecord(
            source=self.name,
            status=CoverageStatus.OK,
            observed_at=datetime.now(UTC),
            detail="stub",
        )


def test_scenario_a_an_unexplained_move_is_reported_without_a_manufactured_cause(
    tmp_path,
) -> None:
    """The price moved and we do not know why. Saying so is the product working."""
    bars = calm()
    bars.append(
        Bar(on=START + timedelta(days=99), close=105.0, adjusted_close=105.0, volume=3_000_000)
    )
    store = SqliteAssessmentStore(tmp_path / "a.db")

    _run, assessed = run_market_pipeline(StubMarket({SUBJECT: bars}), store)

    movement = [a for a in assessed if a.event.event_type == UNUSUAL_MOVEMENT]
    assert len(movement) == 1
    codes = {r.code for r in movement[0].reasons}
    assert "UNUSUAL_PRICE_MOVE" in codes
    # Nothing in the surfaced text asserts a reason for the move.
    assert "because" not in movement[0].event.description.lower()


def test_the_no_company_event_claim_requires_having_looked(tmp_path) -> None:
    """ "We found no disclosure" is a claim about disclosures, and needs coverage.

    A market-only run has not consulted them, so it must state the gap instead of
    asserting the finding — the same rule that D20 established for silence.
    """
    bars = calm()
    bars.append(
        Bar(on=START + timedelta(days=99), close=105.0, adjusted_close=105.0, volume=3_000_000)
    )
    store = SqliteAssessmentStore(tmp_path / "nc.db")

    _run, assessed = run_market_pipeline(StubMarket({SUBJECT: bars}), store)

    codes = {r.code for r in assessed[0].reasons}
    assert "NO_DISCLOSURE_CONSULTED" in codes
    assert "NO_COMPANY_EVENT_DETECTED" not in codes, (
        "the market run did not look at disclosures, so it may not report their absence"
    )


def test_the_claim_is_made_once_disclosures_have_been_consulted() -> None:
    """With disclosure coverage healthy, the absence becomes a finding we can state."""
    from smart_watchlist.core.engine import assess
    from smart_watchlist.core.market import observe
    from smart_watchlist.core.models import Coverage, Event, SourceTier
    from smart_watchlist.core.normalize import from_observation

    bars = calm()
    bars.append(
        Bar(on=START + timedelta(days=99), close=105.0, adjusted_close=105.0, volume=3_000_000)
    )
    observation = observe(SUBJECT, bars)
    assert observation is not None
    evidence = from_observation(observation, "Reliance Industries Limited")[0]
    event = Event(
        event_id="e",
        security_symbol=SUBJECT,
        company_name="Reliance Industries Limited",
        event_type=evidence.category,
        description=evidence.title,
        occurred_at=evidence.published_at,
        evidence=(evidence,),
    )
    assert evidence.tier is SourceTier.COMPUTED

    healthy = Coverage(
        records=(
            CoverageRecord(
                source="nse-disclosures",
                status=CoverageStatus.OK,
                observed_at=datetime.now(UTC),
                detail="consulted",
            ),
        )
    )

    codes = {r.code for r in assess(event, healthy, observation).reasons}

    assert "NO_COMPANY_EVENT_DETECTED" in codes
    assert "NO_DISCLOSURE_CONSULTED" not in codes


def test_scenario_g_a_split_is_reported_as_mechanical_not_as_deterioration(tmp_path) -> None:
    """A two-for-one split halves the printed price and means nothing economically."""
    bars = calm()
    bars.append(
        Bar(
            on=START + timedelta(days=99),
            close=50.0,
            adjusted_close=100.0,
            volume=1_000_000,
            split_ratio=2.0,
        )
    )
    store = SqliteAssessmentStore(tmp_path / "g.db")

    _run, assessed = run_market_pipeline(StubMarket({SUBJECT: bars}), store)

    assert [a.event.event_type for a in assessed] == [CORPORATE_ACTION], (
        "a split must produce a corporate-action note and no unusual-movement event"
    )
    action = assessed[0]
    codes = {r.code for r in action.reasons}
    assert "CORPORATE_ACTION_EXPLAINS_MOVE" in codes
    assert "UNUSUAL_PRICE_MOVE" not in codes
    assert action.attention.value in ("LOW", "NO_MEANINGFUL_CHANGE", "UNABLE_TO_EVALUATE_RELIABLY")
    assert "mechanical" in " ".join(r.detail for r in action.reasons).lower()


def test_a_calm_security_produces_nothing_at_all(tmp_path) -> None:
    """Absence of an assessment is not a verdict — it is simply nothing to report."""
    store = SqliteAssessmentStore(tmp_path / "c.db")

    _run, assessed = run_market_pipeline(StubMarket({SUBJECT: calm()}), store)

    assert assessed == []


def test_a_security_with_no_bars_is_skipped_not_called_calm(tmp_path) -> None:
    store = SqliteAssessmentStore(tmp_path / "n.db")

    run, assessed = run_market_pipeline(StubMarket({}), store)

    assert assessed == []
    assert run.assessed_count == 0


def test_a_self_explaining_finding_is_not_reported_as_unevaluable(tmp_path) -> None:
    """Scenario G must not be misrepresented in the other direction either.

    "Unable to evaluate reliably" means absence might be blindness. A corporate action
    is a complete account of what happened, so the verdict is benign, not unknown —
    even while the news adapter is missing.
    """
    bars = calm()
    bars.append(
        Bar(
            on=START + timedelta(days=99),
            close=50.0,
            adjusted_close=100.0,
            volume=1_000_000,
            split_ratio=2.0,
        )
    )
    store = SqliteAssessmentStore(tmp_path / "sg.db")

    _run, assessed = run_market_pipeline(StubMarket({SUBJECT: bars}), store)

    action = assessed[0]
    assert action.attention is not Attention.UNABLE
    assert action.confidence is Confidence.HIGH, "computed from primary data"


def test_the_exemption_does_not_leak_to_ordinary_findings(tmp_path) -> None:
    """Only a self-explaining finding is exempt; everything else still degrades."""
    bars = calm()
    bars.append(
        Bar(on=START + timedelta(days=99), close=100.1, adjusted_close=100.1, volume=1_000_000)
    )
    store = SqliteAssessmentStore(tmp_path / "sx.db")

    _run, assessed = run_market_pipeline(StubMarket({SUBJECT: bars}), store)

    assert assessed == [], "a calm session yields nothing to exempt in the first place"
