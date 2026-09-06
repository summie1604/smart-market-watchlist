"""Login-free demo mode.

Authentication is not removed — it is bypassed for callers who present no session, and
every query is still scoped to whichever user was resolved. These tests pin both halves:
that the demo account is real and persistent, and that turning the switch off restores
the sign-in wall exactly as it was.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

PASSWORD = "correct horse battery staple"


@pytest.fixture
def demo_app(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "on")
    monkeypatch.setenv("WATCHLIST_DB", str(tmp_path / "demo.db"))
    import smart_watchlist.api.app as module

    importlib.reload(module)
    return module


@pytest.fixture
def client(demo_app):
    return TestClient(demo_app.app)


# --- the demo experience -------------------------------------------------------


def test_an_anonymous_caller_reaches_the_dashboard(client) -> None:
    """No sign-in, no wall — the point of the switch."""
    me = client.get("/v1/auth/me")

    assert me.status_code == 200
    assert me.json()["is_demo"] is True
    assert me.json()["demo_mode"] is True
    assert client.get("/v1/watchlist").status_code == 200
    assert client.get("/v1/review").status_code == 200


def test_the_demo_watchlist_and_checkpoint_are_real_state(client) -> None:
    """Not simulated: the same rows an account would own, so reviews genuinely work."""
    client.post("/v1/watchlist", json={"symbol": "RELIANCE"})

    assert [c["symbol"] for c in client.get("/v1/watchlist").json()["companies"]] == ["RELIANCE"]

    first = client.get("/v1/review").json()
    assert first["previous_checkpoint"] is None

    client.post("/v1/review/complete", json={"review_id": first["review_id"]})
    second = client.get("/v1/review").json()

    assert second["previous_checkpoint"] == first["review_cutoff"], (
        "the checkpoint advanced to the issued cutoff, exactly as for a real account"
    )


def test_the_demo_account_persists_across_separate_clients(demo_app) -> None:
    """One server-owned account, so a reload does not reset the demo."""
    first = TestClient(demo_app.app)
    first.post("/v1/watchlist", json={"symbol": "INFY"})

    second = TestClient(demo_app.app)  # a fresh browser, no cookies

    assert [c["symbol"] for c in second.get("/v1/watchlist").json()["companies"]] == ["INFY"]
    assert second.get("/v1/auth/me").json()["user_id"] == first.get("/v1/auth/me").json()["user_id"]


def test_a_real_session_still_wins_over_the_demo_account(client) -> None:
    """Signing in works while demo mode is on, so the authenticated path stays live."""
    demo_id = client.get("/v1/auth/me").json()["user_id"]

    client.post("/v1/auth/register", json={"email": "real@example.com", "password": PASSWORD})
    me = client.get("/v1/auth/me").json()

    assert me["user_id"] != demo_id
    assert me["is_demo"] is False
    assert me["email"] == "real@example.com"


def test_a_signed_in_user_does_not_inherit_the_demo_watchlist(client) -> None:
    """Resolving differently must not blur the two accounts' state together."""
    client.post("/v1/watchlist", json={"symbol": "RELIANCE"})
    client.post("/v1/auth/register", json={"email": "real@example.com", "password": PASSWORD})

    assert client.get("/v1/watchlist").json()["companies"] == []


def test_signing_out_returns_to_the_demo_account_not_a_wall(client) -> None:
    client.post("/v1/auth/register", json={"email": "real@example.com", "password": PASSWORD})
    client.post("/v1/auth/logout")

    me = client.get("/v1/auth/me")

    assert me.status_code == 200
    assert me.json()["is_demo"] is True


def test_a_forged_cookie_grants_the_demo_account_and_nothing_more(client) -> None:
    """Falling through to the demo account is the safe failure: it is nobody's data."""
    client.post("/v1/auth/register", json={"email": "real@example.com", "password": PASSWORD})
    real_id = client.get("/v1/auth/me").json()["user_id"]
    client.cookies.set("swl_session", "forged-session-identifier")

    me = client.get("/v1/auth/me").json()

    assert me["user_id"] != real_id
    assert me["is_demo"] is True


# --- the switch ----------------------------------------------------------------


def test_turning_demo_mode_off_restores_the_sign_in_wall(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_MODE", "off")
    monkeypatch.setenv("WATCHLIST_DB", str(tmp_path / "walled.db"))
    import smart_watchlist.api.app as module

    importlib.reload(module)
    walled = TestClient(module.app)

    assert walled.get("/v1/auth/me").status_code == 401
    assert walled.get("/v1/watchlist").status_code == 401
    assert walled.get("/v1/review").status_code == 401


@pytest.mark.parametrize("value", ["off", "OFF", "0", "false", "False"])
def test_the_switch_accepts_the_obvious_off_spellings(tmp_path, monkeypatch, value) -> None:
    monkeypatch.setenv("DEMO_MODE", value)
    from smart_watchlist.api.auth import demo_mode_enabled

    assert demo_mode_enabled() is False


def test_the_demo_account_cannot_be_signed_into_or_claimed(demo_app) -> None:
    """Its stored hash is not a hash of anything, so the credential path cannot match —
    and its address is already taken, so it cannot be registered out from under itself."""
    client = TestClient(demo_app.app)
    client.get("/v1/auth/me")  # ensure the account exists

    # All at least the minimum length, so the credential path is genuinely exercised
    # rather than rejected by input validation before it gets there.
    for attempt in ("demo1234", "password", "demo-account-has-no-password"):
        response = client.post(
            "/v1/auth/login", json={"email": "demo@example.com", "password": attempt}
        )
        assert response.status_code == 401, f"{attempt!r} must not authenticate"

    claimed = client.post(
        "/v1/auth/register", json={"email": "demo@example.com", "password": PASSWORD}
    )
    assert claimed.status_code == 409, "the demo address cannot be registered"


def test_the_supported_universe_is_discoverable(client) -> None:
    """The interface offers what can be added without keeping its own copy of the list."""
    companies = client.get("/v1/universe").json()["companies"]

    symbols = {c["symbol"] for c in companies}
    assert {"RELIANCE", "INFY", "HDFCBANK", "TMCV"} <= symbols
    assert all(c["company"] and c["coverage_tier"] for c in companies)
