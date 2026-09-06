"""Interests over HTTP: captured on the way in, returned to their owner, never scored.

Covers the boundary the design leans on (D27): what a user says they are watching for is
private state that annotates shared intelligence and changes nothing about it.
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from support import coverage, make_evidence

from smart_watchlist.core.engine import assess
from smart_watchlist.core.models import Event


@pytest.fixture
def app_module(tmp_path, monkeypatch):
    monkeypatch.setenv("WATCHLIST_DB", str(tmp_path / "interests.db"))
    monkeypatch.setenv("DEMO_MODE", "on")
    import smart_watchlist.api.app as module

    importlib.reload(module)
    return module


@pytest.fixture
def client(app_module):
    return TestClient(app_module.app)


def store_event(app_module, *, ref: str, symbol: str, category: str, when: datetime) -> None:
    evidence = make_evidence(symbol=symbol, category=category, ref=ref)
    event = Event(
        event_id=ref,
        security_symbol=symbol,
        company_name=symbol,
        event_type=category,
        description=f"{symbol}: {category}",
        occurred_at=when,
        evidence=(evidence,),
    )
    app_module._store().save(assess(event, coverage()))


def test_adding_a_company_records_why_and_what_to_watch_for(client) -> None:
    added = client.post(
        "/v1/watchlist",
        json={
            "symbol": "RELIANCE",
            "reason": "Largest holding in my portfolio.",
            "watch_for": "Anything about the refining margin.",
            "tags": ["commodities", "earnings"],
        },
    ).json()

    assert added["reason"] == "Largest holding in my portfolio."
    assert added["watch_for"] == "Anything about the refining margin."
    assert added["tags"] == ["commodities", "earnings"]

    listed = client.get("/v1/watchlist").json()["companies"][0]
    assert listed["tags"] == ["commodities", "earnings"]
    assert listed["sector_index"] == "^NSEI"


def test_every_interest_is_optional(client) -> None:
    """The questions are worth asking and never worth blocking on."""
    added = client.post("/v1/watchlist", json={"symbol": "INFY"})

    assert added.status_code == 200
    assert added.json()["tags"] == []
    assert added.json()["reason"] == ""


def test_re_adding_without_interests_does_not_erase_them(client) -> None:
    client.post("/v1/watchlist", json={"symbol": "INFY", "tags": ["earnings"]})
    client.post("/v1/watchlist", json={"symbol": "INFY"})

    assert client.get("/v1/watchlist").json()["companies"][0]["tags"] == ["earnings"]


def test_re_adding_with_interests_updates_them(client) -> None:
    client.post("/v1/watchlist", json={"symbol": "INFY", "tags": ["earnings"]})
    client.post("/v1/watchlist", json={"symbol": "INFY", "tags": ["management"]})

    assert client.get("/v1/watchlist").json()["companies"][0]["tags"] == ["management"]


def test_a_tag_nothing_could_match_is_refused_entry(client) -> None:
    added = client.post("/v1/watchlist", json={"symbol": "INFY", "tags": ["vibes"]}).json()

    assert added["tags"] == [], "a filter that can never match reads as missed news"


def test_the_focus_vocabulary_is_served_rather_than_duplicated(client) -> None:
    tags = client.get("/v1/focus-tags").json()["tags"]

    assert {t["tag"] for t in tags} >= {"earnings", "regulation", "contracts"}
    assert all(t["label"] and t["because"] for t in tags)


def test_matching_events_are_annotated_with_the_reason_they_matched(client, app_module) -> None:
    client.post("/v1/watchlist", json={"symbol": "RELIANCE", "tags": ["regulation"]})
    store_event(
        app_module,
        ref="reg-1",
        symbol="RELIANCE",
        category="Regulatory Action",
        when=datetime.now(UTC),
    )

    served = client.get("/v1/assessments").json()["assessments"][0]

    assert [f["tag"] for f in served["focus"]] == ["regulation"]
    assert served["focus"][0]["why"]


def test_focus_annotation_does_not_change_the_verdict_or_the_order(client, app_module) -> None:
    """The same events, two different sets of interests, one identical answer."""
    now = datetime.now(UTC)
    store_event(
        app_module,
        ref="reg-1",
        symbol="RELIANCE",
        category="Regulatory Action",
        when=now - timedelta(days=1),
    )
    store_event(
        app_module,
        ref="res-1",
        symbol="INFY",
        category="Financial Result Updates",
        when=now,
    )

    client.post("/v1/watchlist", json={"symbol": "RELIANCE", "tags": ["regulation"]})
    client.post("/v1/watchlist", json={"symbol": "INFY", "tags": ["regulation"]})
    with_regulation = client.get("/v1/assessments").json()["assessments"]

    client.post("/v1/watchlist", json={"symbol": "RELIANCE", "tags": ["earnings"]})
    client.post("/v1/watchlist", json={"symbol": "INFY", "tags": ["earnings"]})
    with_earnings = client.get("/v1/assessments").json()["assessments"]

    assert [a["event_id"] for a in with_regulation] == [a["event_id"] for a in with_earnings]
    assert [a["attention"] for a in with_regulation] == [a["attention"] for a in with_earnings]
    assert [a["confidence"] for a in with_regulation] == [a["confidence"] for a in with_earnings]


def test_a_review_carries_the_same_annotation(client, app_module) -> None:
    client.post("/v1/watchlist", json={"symbol": "RELIANCE", "tags": ["regulation"]})
    store_event(
        app_module,
        ref="reg-1",
        symbol="RELIANCE",
        category="Regulatory Action",
        when=datetime.now(UTC),
    )

    page = client.get("/v1/review").json()
    lines = [*page["changed"], *page["newly_added"]]

    assert lines, "the event arrived after the company was added, so it is in the window"
    assert [f["tag"] for f in lines[0]["assessments"][0]["focus"]] == ["regulation"]


def test_price_context_is_refused_for_an_unsupported_security(client) -> None:
    """A chart for something we do not cover would be a picture with no provenance."""
    response = client.get("/v1/prices/NOTREAL")

    assert response.status_code == 404


def test_needs_attention_is_served_flat_and_in_canonical_order(client, app_module) -> None:
    """Order across companies is the backend's answer, not something a client stitches."""
    now = datetime.now(UTC)
    client.post("/v1/watchlist", json={"symbol": "RELIANCE"})
    client.post("/v1/watchlist", json={"symbol": "INFY"})

    # A routine disclosure for one company, a material one for the other, older.
    store_event(
        app_module,
        ref="material",
        symbol="INFY",
        category="Outcome of Board Meeting",
        when=now - timedelta(days=2),
    )
    store_event(
        app_module,
        ref="routine",
        symbol="RELIANCE",
        category="Shareholders meeting",
        when=now,
    )

    items = client.get("/v1/review").json()["needs_attention"]
    levels = [i["assessment"]["attention"] for i in items]

    assert levels == sorted(levels, key=["HIGH", "MEDIUM", "LOW"].index)
    assert all(level in ("HIGH", "MEDIUM", "LOW") for level in levels), (
        "a coverage gap is not something that asks the reader for anything"
    )
