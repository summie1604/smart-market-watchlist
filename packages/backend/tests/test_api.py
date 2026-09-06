"""The HTTP surface.

The shape claim under test: source health is reachable independently of assessments,
because the case that matters is the one where there are none.
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A client over an empty database, isolated per test."""
    monkeypatch.setenv("WATCHLIST_DB", str(tmp_path / "api.db"))
    import smart_watchlist.api.app as app_module

    importlib.reload(app_module)
    return TestClient(app_module.app)


def test_health_reports_ok(client) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_source_health_is_present_even_with_no_assessments(client) -> None:
    """An empty store must still be able to say whether we have looked."""
    body = client.get("/v1/assessments").json()

    assert body["count"] == 0
    assert body["assessments"] == []
    assert "source_health" in body, "health must not be reachable only via an assessment"
    assert body["source_health"] is None, "never having run is not the same as running and failing"


def test_assessments_arrive_in_canonical_order(client, monkeypatch) -> None:
    """Ranking is the engine's answer; the response carries it so clients need not re-derive it."""
    from support import coverage, make_event, make_evidence

    import smart_watchlist.api.app as app_module
    from smart_watchlist.core.engine import assess

    store = app_module._store()
    for category in ("Shareholders meeting", "Outcome of Board Meeting"):
        evidence = make_evidence(category=category, ref=f"ref-{category}")
        store.save(assess(make_event(evidence), coverage()))

    returned = client.get("/v1/assessments").json()["assessments"]

    # A material disclosure for a curated company under full coverage outranks a
    # routine one; the API returns them in that order so the client need not decide.
    assert [a["attention"] for a in returned] == ["HIGH", "NO_MEANINGFUL_CHANGE"]


def test_health_covers_every_source_family_that_has_run(client) -> None:
    """The banner must not claim nothing was looked at while showing results.

    Regression: health was read from the disclosure source alone, so a news-only run
    rendered "No ingest has run" above three assessments produced by that very run.
    """
    import smart_watchlist.api.app as app_module
    from smart_watchlist.core.models import Coverage, CoverageRecord, CoverageStatus, IngestRun

    now = datetime.now(UTC)
    store = app_module._store()
    store.save_run(
        IngestRun(
            run_id="news:1",
            source="news",
            started_at=now,
            coverage=Coverage(
                records=(
                    CoverageRecord(
                        source="news", status=CoverageStatus.OK, observed_at=now, detail="ok"
                    ),
                )
            ),
            assessed_count=3,
        )
    )

    body = client.get("/v1/assessments").json()

    assert body["source_health"] is not None, "a news run is a run"
    assert body["source_health"]["healthy"] is True
    assert any(r["source"] == "news" for r in body["runs"])


def test_health_is_none_only_when_nothing_has_ever_run(client) -> None:
    body = client.get("/v1/assessments").json()

    assert body["source_health"] is None
    assert body["runs"] == []


def test_each_source_family_is_judged_by_its_own_run(client) -> None:
    """A run saying "I did not consult news" is not a statement about news's health.

    Regression: pooling every run's records let a market run's "news not consulted"
    override the news run's own healthy record, so news read as missing while it was
    fine — and every company came back "unable to evaluate", making the honest quiet
    verdict unreachable.
    """
    import smart_watchlist.api.app as app_module
    from smart_watchlist.core.models import Coverage, CoverageRecord, CoverageStatus, IngestRun

    now = datetime.now(UTC)
    store = app_module._store()
    store.save_run(
        IngestRun(
            run_id="news:1",
            source="news",
            started_at=now,
            coverage=Coverage(
                records=(
                    CoverageRecord(
                        source="news", status=CoverageStatus.OK, observed_at=now, detail="ok"
                    ),
                )
            ),
            assessed_count=1,
        )
    )
    store.save_run(
        IngestRun(
            run_id="market:1",
            source="market",
            started_at=now,
            coverage=Coverage(
                records=(
                    CoverageRecord(
                        source="market", status=CoverageStatus.OK, observed_at=now, detail="ok"
                    ),
                    CoverageRecord(
                        source="news",
                        status=CoverageStatus.UNAVAILABLE,
                        observed_at=now,
                        detail="not consulted by this run",
                    ),
                )
            ),
            assessed_count=1,
        )
    )

    coverage = app_module._current_coverage(store)

    assert {r.source for r in coverage.missing} == set(), "news is healthy per its own run"
    assert coverage.is_complete
