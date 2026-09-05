"""The Step 4 journey, and the invariants that make it correct.

Two users, one shared intelligence store, two different reviews. The review window is
the part most easily got subtly wrong, so it is tested from several directions rather
than once.
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from smart_watchlist.core.corroboration import assess_corroboration
from smart_watchlist.core.engine import assess
from smart_watchlist.core.models import (
    Coverage,
    CoverageRecord,
    CoverageStatus,
    Event,
    Evidence,
    SourceTier,
)

PASSWORD = "correct horse battery staple"


@pytest.fixture
def app_module(tmp_path, monkeypatch):
    monkeypatch.setenv("WATCHLIST_DB", str(tmp_path / "journey.db"))
    import smart_watchlist.api.app as module

    importlib.reload(module)
    return module


@pytest.fixture
def client(app_module):
    return TestClient(app_module.app)


def account(app_module, email: str) -> TestClient:
    """A signed-in client with its own cookie jar — i.e. its own device."""
    session = TestClient(app_module.app)
    response = session.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201
    return session


def store_assessment(app_module, symbol: str, when: datetime, ref: str) -> None:
    """Put one shared assessment in the world. Not owned by anyone."""
    evidence = Evidence(
        source="news",
        source_ref=ref,
        tier=SourceTier.CREDIBLE_REPORTING,
        publisher="Reuters",
        subject_company=symbol,
        retrieved_at=when,
        published_at=when,
        title=f"{symbol} announced something",
        body="",
        url="https://example.invalid",
        security_symbol=symbol,
        category="News",
    )
    event = Event(
        event_id=ref,
        security_symbol=symbol,
        company_name=symbol,
        event_type="Agreements",
        description=f"{symbol} announced something",
        occurred_at=when,
        evidence=(evidence,),
    )
    coverage = Coverage(
        records=tuple(
            CoverageRecord(source=s, status=CoverageStatus.OK, observed_at=when, detail="")
            for s in ("news", "market", "nse-disclosures")
        )
    )
    app_module._store().save(
        assess(event, coverage, corroboration=assess_corroboration(event.evidence))
    )


# --- the journey --------------------------------------------------------------


def test_the_full_journey(app_module) -> None:
    alice = account(app_module, "alice@example.com")

    assert alice.get("/auth/me").json()["email"] == "alice@example.com"
    assert alice.get("/watchlist").json()["companies"] == []

    added = alice.post("/watchlist", json={"symbol": "RELIANCE"}).json()
    assert added["symbol"] == "RELIANCE"
    assert added["coverage_tier"] == "FULL", "the tier is shown when adding"

    first = alice.get("/review").json()
    assert first["previous_checkpoint"] is None, "no checkpoint before the first review"

    complete = alice.post("/review/complete", json={"review_id": first["review_id"]}).json()
    assert complete["outcome"] == "advanced"
    assert complete["checkpoint"] == first["review_cutoff"], "advances to the cutoff"

    # Something happens, then a second review sees it.
    store_assessment(app_module, "RELIANCE", datetime.now(UTC), "ref-new")
    second = alice.get("/review").json()
    assert second["previous_checkpoint"] == complete["checkpoint"]
    assert any(line["symbol"] == "RELIANCE" for line in second["changed"])


def test_two_users_share_intelligence_but_not_reviews(app_module) -> None:
    """The central claim: one analysis, two different answers."""
    alice = account(app_module, "alice@example.com")
    bob = account(app_module, "bob@example.com")
    for session in (alice, bob):
        session.post("/watchlist", json={"symbol": "RELIANCE"})

    store_assessment(app_module, "RELIANCE", datetime.now(UTC), "shared-1")

    # Alice reviews and completes; Bob does not.
    alice_review = alice.get("/review").json()
    alice.post("/review/complete", json={"review_id": alice_review["review_id"]})

    store_assessment(app_module, "RELIANCE", datetime.now(UTC), "shared-2")

    alice_second = alice.get("/review").json()
    bob_first = bob.get("/review").json()

    alice_refs = {a["event_id"] for line in alice_second["changed"] for a in line["assessments"]}
    bob_refs = {a["event_id"] for line in bob_first["changed"] for a in line["assessments"]}

    assert alice_refs == {"shared-2"}, "Alice already reviewed the first"
    assert bob_refs == {"shared-1", "shared-2"}, "Bob has never reviewed"

    # And there is exactly one underlying record per event, not one per user.
    stored = app_module._store().recent(100)
    assert len([a for a in stored if a.event.event_id == "shared-1"]) == 1


# --- the review window (D7) ---------------------------------------------------


def test_an_event_arriving_during_an_open_review_stays_new(app_module) -> None:
    """The invariant D7 exists for: completion advances to the cutoff, not the click."""
    alice = account(app_module, "alice@example.com")
    alice.post("/watchlist", json={"symbol": "RELIANCE"})

    opened = alice.get("/review").json()
    # Arrives after the issued cutoff, while the user is still reading. Its timestamp is
    # "now", which is already later than the cutoff the server committed to above.
    arrived_at = datetime.now(UTC)
    assert arrived_at > datetime.fromisoformat(opened["review_cutoff"])
    store_assessment(app_module, "RELIANCE", arrived_at, "arrived-during")
    alice.post("/review/complete", json={"review_id": opened["review_id"]})

    following = alice.get("/review").json()
    refs = {a["event_id"] for line in following["changed"] for a in line["assessments"]}
    assert "arrived-during" in refs, "it was never part of the review that was completed"


def test_rendering_a_review_does_not_advance_the_checkpoint(app_module) -> None:
    alice = account(app_module, "alice@example.com")
    alice.post("/watchlist", json={"symbol": "RELIANCE"})

    alice.get("/review")
    alice.get("/review")
    alice.get("/review")

    assert alice.get("/review").json()["previous_checkpoint"] is None


def test_completion_is_idempotent(app_module) -> None:
    alice = account(app_module, "alice@example.com")
    review = alice.get("/review").json()

    first = alice.post("/review/complete", json={"review_id": review["review_id"]}).json()
    second = alice.post("/review/complete", json={"review_id": review["review_id"]}).json()

    assert first["checkpoint"] == second["checkpoint"]
    assert second["outcome"] == "already-at-this-cutoff"


def test_a_stale_tab_cannot_move_the_checkpoint_backwards(app_module) -> None:
    """Two devices, completed out of order. The later cutoff must stand."""
    alice = account(app_module, "alice@example.com")

    old_review = alice.get("/review").json()  # opened on the laptop
    newer_review = alice.get("/review").json()  # opened later on the phone

    alice.post("/review/complete", json={"review_id": newer_review["review_id"]})
    after_newer = alice.get("/review").json()["previous_checkpoint"]

    stale = alice.post("/review/complete", json={"review_id": old_review["review_id"]}).json()

    assert stale["outcome"] == "stale-cutoff-ignored"
    assert stale["checkpoint"] == after_newer, "the checkpoint did not regress"


def test_a_client_cannot_submit_a_cutoff_it_was_never_issued(app_module) -> None:
    """Completion resolves a review id, never a timestamp the client supplies."""
    alice = account(app_module, "alice@example.com")

    forged = alice.post("/review/complete", json={"review_id": "made-up-review-id"})

    assert forged.status_code == 404
    assert alice.get("/review").json()["previous_checkpoint"] is None
