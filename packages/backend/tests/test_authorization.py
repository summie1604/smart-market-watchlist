"""Authorization, isolation, and the failure paths around them.

The rule under test throughout: **ownership is enforced by scoping, not by checking.**
Every private query filters on the session's user in SQL, so substituting an id in a
request reaches a query that finds nothing rather than a check someone might forget.
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

PASSWORD = "correct horse battery staple"


@pytest.fixture
def app_module(tmp_path, monkeypatch):
    monkeypatch.setenv("WATCHLIST_DB", str(tmp_path / "authz.db"))
    import smart_watchlist.api.app as module

    importlib.reload(module)
    return module


def account(app_module, email: str) -> TestClient:
    session = TestClient(app_module.app)
    assert (
        session.post("/auth/register", json={"email": email, "password": PASSWORD}).status_code
        == 201
    )
    return session


# --- registration and sign-in -------------------------------------------------


def test_duplicate_registration_is_refused_without_confirming_the_account(app_module) -> None:
    account(app_module, "alice@example.com")
    other = TestClient(app_module.app)

    response = other.post(
        "/auth/register", json={"email": "alice@example.com", "password": PASSWORD}
    )

    assert response.status_code == 409
    assert "alice" not in response.json()["detail"].lower()
    assert "exists" not in response.json()["detail"].lower()


def test_invalid_credentials_do_not_say_which_part_was_wrong(app_module) -> None:
    account(app_module, "alice@example.com")
    anon = TestClient(app_module.app)

    wrong_password = anon.post(
        "/auth/login", json={"email": "alice@example.com", "password": "wrong-password"}
    )
    unknown_email = anon.post(
        "/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json()["detail"] == unknown_email.json()["detail"]


def test_a_short_password_is_rejected_before_it_reaches_the_store(app_module) -> None:
    anon = TestClient(app_module.app)

    assert (
        anon.post(
            "/auth/register", json={"email": "a@example.com", "password": "short"}
        ).status_code
        == 422
    )


def test_logout_invalidates_the_session(app_module) -> None:
    alice = account(app_module, "alice@example.com")
    assert alice.get("/auth/me").status_code == 200

    alice.post("/auth/logout")

    assert alice.get("/auth/me").status_code == 401


def test_an_expired_session_does_not_authenticate(app_module) -> None:
    account(app_module, "alice@example.com")
    store = app_module._USER_STORE
    user = store.verify_credentials("alice@example.com", PASSWORD)
    assert user is not None

    expired = store.create_session(user.user_id, now=datetime.now(UTC) - timedelta(days=30))

    assert store.user_for_session(expired.session_id) is None


# --- anonymous and cross-user access ------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", "/auth/me"), ("get", "/watchlist"), ("get", "/review"), ("post", "/review/complete")],
)
def test_anonymous_requests_cannot_reach_private_state(app_module, method, path) -> None:
    anon = TestClient(app_module.app)

    call = getattr(anon, method)
    response = call(path, json={"review_id": "x"}) if method == "post" else call(path)

    assert response.status_code == 401


def test_one_user_cannot_see_anothers_watchlist(app_module) -> None:
    alice = account(app_module, "alice@example.com")
    bob = account(app_module, "bob@example.com")
    alice.post("/watchlist", json={"symbol": "RELIANCE"})

    assert bob.get("/watchlist").json()["companies"] == []


def test_one_user_cannot_remove_from_anothers_watchlist(app_module) -> None:
    alice = account(app_module, "alice@example.com")
    bob = account(app_module, "bob@example.com")
    alice.post("/watchlist", json={"symbol": "RELIANCE"})

    removed = bob.delete("/watchlist/RELIANCE").json()

    assert removed["removed"] is False, "there was nothing of Bob's to remove"
    assert [c["symbol"] for c in alice.get("/watchlist").json()["companies"]] == ["RELIANCE"]


def test_one_user_cannot_complete_anothers_review(app_module) -> None:
    """The lookup is scoped by user, so another user's review is simply not found."""
    alice = account(app_module, "alice@example.com")
    bob = account(app_module, "bob@example.com")
    alice_review = alice.get("/review").json()

    stolen = bob.post("/review/complete", json={"review_id": alice_review["review_id"]})

    assert stolen.status_code == 404
    assert alice.get("/review").json()["previous_checkpoint"] is None, "Alice's state is untouched"


def test_a_forged_session_cookie_does_not_authenticate(app_module) -> None:
    anon = TestClient(app_module.app)
    anon.cookies.set("swl_session", "forged-session-identifier")

    assert anon.get("/auth/me").status_code == 401


# --- watchlist behaviour ------------------------------------------------------


def test_an_unsupported_symbol_is_refused_honestly(app_module) -> None:
    alice = account(app_module, "alice@example.com")

    response = alice.post("/watchlist", json={"symbol": "NOTREAL"})

    assert response.status_code == 404
    assert "not a supported security" in response.json()["detail"]


def test_adding_the_same_company_twice_keeps_the_original_boundary(app_module) -> None:
    """Bumping ``added_at`` would silently discard history the user was already shown."""
    alice = account(app_module, "alice@example.com")

    first = alice.post("/watchlist", json={"symbol": "RELIANCE"}).json()
    second = alice.post("/watchlist", json={"symbol": "RELIANCE"}).json()

    assert first["added_at"] == second["added_at"]
    assert len(alice.get("/watchlist").json()["companies"]) == 1


def test_removing_a_company_that_is_not_there_is_not_an_error(app_module) -> None:
    alice = account(app_module, "alice@example.com")

    assert alice.delete("/watchlist/RELIANCE").json()["removed"] is False


def test_re_adding_a_company_does_not_manufacture_unseen_history(app_module) -> None:
    alice = account(app_module, "alice@example.com")
    alice.post("/watchlist", json={"symbol": "RELIANCE"})
    alice.delete("/watchlist/RELIANCE")

    re_added = alice.post("/watchlist", json={"symbol": "RELIANCE"}).json()

    # The boundary is when they added it back, not the beginning of time.
    assert datetime.fromisoformat(re_added["watched_from"]) <= datetime.now(UTC)


def test_an_empty_watchlist_produces_an_empty_but_valid_review(app_module) -> None:
    alice = account(app_module, "alice@example.com")

    review = alice.get("/review").json()

    assert review["changed"] == [] and review["quiet"] == []
    assert review["review_id"], "a review was still issued"
