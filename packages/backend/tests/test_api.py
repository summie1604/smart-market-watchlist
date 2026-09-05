"""The HTTP surface.

The shape claim under test: source health is reachable independently of assessments,
because the case that matters is the one where there are none.
"""

from __future__ import annotations

import importlib

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
    body = client.get("/assessments").json()

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

    returned = client.get("/assessments").json()["assessments"]

    # A material disclosure for a curated company under full coverage outranks a
    # routine one; the API returns them in that order so the client need not decide.
    assert [a["attention"] for a in returned] == ["HIGH", "NO_MEANINGFUL_CHANGE"]
