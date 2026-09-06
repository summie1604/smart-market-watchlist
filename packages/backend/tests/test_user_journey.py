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
    # Authenticated mode: the sign-in wall is what these tests are about, so demo mode
    # is off. Demo mode has its own suite.
    monkeypatch.setenv("DEMO_MODE", "off")
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
    response = session.post("/v1/auth/register", json={"email": email, "password": PASSWORD})
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

    assert alice.get("/v1/auth/me").json()["email"] == "alice@example.com"
    assert alice.get("/v1/watchlist").json()["companies"] == []

    added = alice.post("/v1/watchlist", json={"symbol": "RELIANCE"}).json()
    assert added["symbol"] == "RELIANCE"
    assert added["coverage_tier"] == "FULL", "the tier is shown when adding"

    first = alice.get("/v1/review").json()
    assert first["previous_checkpoint"] is None, "no checkpoint before the first review"

    complete = alice.post("/v1/review/complete", json={"review_id": first["review_id"]}).json()
    assert complete["outcome"] == "advanced"
    assert complete["checkpoint"] == first["review_cutoff"], "advances to the cutoff"

    # Something happens, then a second review sees it.
    store_assessment(app_module, "RELIANCE", datetime.now(UTC), "ref-new")
    second = alice.get("/v1/review").json()
    assert second["previous_checkpoint"] == complete["checkpoint"]
    assert any(line["symbol"] == "RELIANCE" for line in second["changed"])


def test_two_users_share_intelligence_but_not_reviews(app_module) -> None:
    """The central claim: one analysis, two different answers."""
    alice = account(app_module, "alice@example.com")
    bob = account(app_module, "bob@example.com")
    for session in (alice, bob):
        session.post("/v1/watchlist", json={"symbol": "RELIANCE"})

    store_assessment(app_module, "RELIANCE", datetime.now(UTC), "shared-1")

    # Alice reviews and completes; Bob does not.
    alice_review = alice.get("/v1/review").json()
    alice.post("/v1/review/complete", json={"review_id": alice_review["review_id"]})

    store_assessment(app_module, "RELIANCE", datetime.now(UTC), "shared-2")

    alice_second = alice.get("/v1/review").json()
    bob_first = bob.get("/v1/review").json()

    def surfaced(review: dict) -> set[str]:
        """Everything the user is shown, whichever section carries it."""
        return {
            a["event_id"]
            for section in ("changed", "newly_added")
            for line in review[section]
            for a in line["assessments"]
        }

    alice_refs = surfaced(alice_second)
    bob_refs = surfaced(bob_first)

    assert alice_refs == {"shared-2"}, "Alice already reviewed the first"
    assert bob_refs == {"shared-1", "shared-2"}, "Bob has never reviewed"

    # And there is exactly one underlying record per event, not one per user.
    stored = app_module._store().recent(100)
    assert len([a for a in stored if a.event.event_id == "shared-1"]) == 1


# --- the review window (D7) ---------------------------------------------------


def test_an_event_arriving_during_an_open_review_stays_new(app_module) -> None:
    """The invariant D7 exists for: completion advances to the cutoff, not the click."""
    alice = account(app_module, "alice@example.com")
    alice.post("/v1/watchlist", json={"symbol": "RELIANCE"})

    opened = alice.get("/v1/review").json()
    # Arrives after the issued cutoff, while the user is still reading. Its timestamp is
    # "now", which is already later than the cutoff the server committed to above.
    arrived_at = datetime.now(UTC)
    assert arrived_at > datetime.fromisoformat(opened["review_cutoff"])
    store_assessment(app_module, "RELIANCE", arrived_at, "arrived-during")
    alice.post("/v1/review/complete", json={"review_id": opened["review_id"]})

    following = alice.get("/v1/review").json()
    refs = {a["event_id"] for line in following["changed"] for a in line["assessments"]}
    assert "arrived-during" in refs, "it was never part of the review that was completed"


def test_rendering_a_review_does_not_advance_the_checkpoint(app_module) -> None:
    alice = account(app_module, "alice@example.com")
    alice.post("/v1/watchlist", json={"symbol": "RELIANCE"})

    alice.get("/v1/review")
    alice.get("/v1/review")
    alice.get("/v1/review")

    assert alice.get("/v1/review").json()["previous_checkpoint"] is None


def test_completion_is_idempotent(app_module) -> None:
    alice = account(app_module, "alice@example.com")
    review = alice.get("/v1/review").json()

    first = alice.post("/v1/review/complete", json={"review_id": review["review_id"]}).json()
    second = alice.post("/v1/review/complete", json={"review_id": review["review_id"]}).json()

    assert first["checkpoint"] == second["checkpoint"]
    assert second["outcome"] == "already-at-this-cutoff"


def test_a_stale_tab_cannot_move_the_checkpoint_backwards(app_module) -> None:
    """Two devices, completed out of order. The later cutoff must stand."""
    alice = account(app_module, "alice@example.com")

    old_review = alice.get("/v1/review").json()  # opened on the laptop
    newer_review = alice.get("/v1/review").json()  # opened later on the phone

    alice.post("/v1/review/complete", json={"review_id": newer_review["review_id"]})
    after_newer = alice.get("/v1/review").json()["previous_checkpoint"]

    stale = alice.post("/v1/review/complete", json={"review_id": old_review["review_id"]}).json()

    assert stale["outcome"] == "stale-cutoff-ignored"
    assert stale["checkpoint"] == after_newer, "the checkpoint did not regress"


def test_a_client_cannot_submit_a_cutoff_it_was_never_issued(app_module) -> None:
    """Completion resolves a review id, never a timestamp the client supplies."""
    alice = account(app_module, "alice@example.com")

    forged = alice.post("/v1/review/complete", json={"review_id": "made-up-review-id"})

    assert forged.status_code == 404
    assert alice.get("/v1/review").json()["previous_checkpoint"] is None


def test_a_first_review_calls_companies_newly_added_not_quiet(app_module) -> None:
    """There was no last review, so "nothing since your last review" would invent one.

    Found live: a user who registered and added a company immediately saw it reported as
    quiet, even though the system had not been watching it for them at all.
    """
    alice = account(app_module, "alice@example.com")
    alice.post("/v1/watchlist", json={"symbol": "RELIANCE"})

    first = alice.get("/v1/review").json()

    assert first["previous_checkpoint"] is None
    assert [line["symbol"] for line in first["newly_added"]] == ["RELIANCE"]
    assert first["quiet"] == [], "nothing can be quiet before we started watching"
    assert "not watching it for you yet" in first["newly_added"][0]["detail"]


def test_after_a_completed_review_a_company_can_be_quiet(app_module) -> None:
    """Once a checkpoint exists, silence is a conclusion the system has standing to draw."""
    alice = account(app_module, "alice@example.com")
    alice.post("/v1/watchlist", json={"symbol": "RELIANCE"})
    first = alice.get("/v1/review").json()
    alice.post("/v1/review/complete", json={"review_id": first["review_id"]})

    second = alice.get("/v1/review").json()

    assert [line["symbol"] for line in second["quiet"]] == ["RELIANCE"]
    assert second["newly_added"] == []


def test_an_event_published_before_the_checkpoint_but_learned_after_is_still_new(
    app_module,
) -> None:
    """The window measures when we learned, not when it happened.

    Found live: a scheduled cycle ingested 218 assessments while the user was away, and
    their review showed nothing — every article had been *published* before their
    checkpoint even though the system only learned of it afterwards. DESIGN.md §20
    requires late-arriving events to stay new to the user.
    """
    from datetime import timedelta

    alice = account(app_module, "alice@example.com")
    alice.post("/v1/watchlist", json={"symbol": "RELIANCE"})
    first = alice.get("/v1/review").json()
    alice.post("/v1/review/complete", json={"review_id": first["review_id"]})

    # Published yesterday; ingested now, after the checkpoint.
    store_assessment(
        app_module, "RELIANCE", datetime.now(UTC) - timedelta(days=1), "published-yesterday"
    )

    following = alice.get("/v1/review").json()

    surfaced = {a["event_id"] for line in following["changed"] for a in line["assessments"]}
    assert "published-yesterday" in surfaced
    # And the event still reports its own publication time, not the time we learned it.
    shown = next(
        a
        for line in following["changed"]
        for a in line["assessments"]
        if a["event_id"] == "published-yesterday"
    )
    assert datetime.fromisoformat(shown["occurred_at"]) < datetime.fromisoformat(
        following["previous_checkpoint"]
    )


def test_a_first_review_counts_the_changes_it_is_holding(app_module) -> None:
    """ "Nothing is asking for your attention" must not be said while holding changes.

    Found in the demo gate: a newly-added company's line carries the assessments that
    arrived after the user started watching, but only `changed` was counted — so the page
    claimed quiet while nine assessed events sat underneath it.
    """
    alice = account(app_module, "alice@example.com")
    alice.post("/v1/watchlist", json={"symbol": "RELIANCE"})
    store_assessment(app_module, "RELIANCE", datetime.now(UTC), "after-adding")

    first = alice.get("/v1/review").json()

    surfaced = sum(len(line["assessments"]) for line in first["changed"] + first["newly_added"])
    assert surfaced == 1
    assert first["attention_count"] == surfaced, "the count must match what is shown"
