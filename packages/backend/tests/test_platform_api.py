"""One versioned API, two transports (D30, D33).

The claim under test is not that a header parses. It is that a native client and a
browser reach the *same* authorization, the same review window and the same canonical
order — because a second client that quietly got a second answer would be the failure
mode the single-API decision exists to prevent.
"""

from __future__ import annotations

import importlib
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from support import coverage, make_evidence

from smart_watchlist.core.engine import assess
from smart_watchlist.core.market import Bar
from smart_watchlist.core.models import Event

PASSWORD = "correct horse battery staple"


@pytest.fixture
def app_module(tmp_path, monkeypatch):
    monkeypatch.setenv("WATCHLIST_DB", str(tmp_path / "platform.db"))
    monkeypatch.setenv("DEMO_MODE", "off")
    import smart_watchlist.api.app as module

    importlib.reload(module)
    return module


@pytest.fixture
def client(app_module):
    return TestClient(app_module.app)


def store_event(app_module, *, ref: str, symbol: str, category: str, when: datetime) -> None:
    evidence = make_evidence(symbol=symbol, category=category, ref=ref)
    app_module._store().save(
        assess(
            Event(
                event_id=ref,
                security_symbol=symbol,
                company_name=symbol,
                event_type=category,
                description=f"{symbol}: {category}",
                occurred_at=when,
                evidence=(evidence,),
            ),
            coverage(),
        )
    )


# --- versioning ----------------------------------------------------------------


def test_health_is_unversioned_because_a_probe_is_not_a_domain_resource(client) -> None:
    assert client.get("/health").status_code == 200


def test_local_astro_fallback_port_is_permitted_for_credentialed_browser_calls(client) -> None:
    response = client.options(
        "/v1/assessments",
        headers={
            "Origin": "http://localhost:4323",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:4323"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_domain_routes_live_under_the_version_prefix(client) -> None:
    assert client.get("/v1/universe").status_code == 200
    assert client.get("/universe").status_code == 404, (
        "one surface, not two: an unversioned alias is a second contract to keep working"
    )


def test_meta_lets_a_client_refuse_to_guess(client, app_module) -> None:
    """A shipped mobile app keeps running against a server that moved on without it."""
    body = client.get("/v1/meta").json()

    assert body["api_version"] == app_module.API_VERSION
    assert "HIGH" in body["attention_levels"]
    assert "DISPUTED" in body["contradiction_states"]
    assert body["scoring_version"], "every verdict is produced by a named scoring version"


def test_price_reads_use_ingested_bars_and_never_fetch_on_page_view(
    client, app_module, monkeypatch
) -> None:
    def no_page_fetch(*_args, **_kwargs):
        raise AssertionError("a page request must not call a market provider")

    monkeypatch.setattr(app_module.YFinanceMarketSource, "fetch", no_page_fetch)
    sessions = [date(2026, 9, 4), date(2026, 9, 5)]

    def series(start: float) -> list[Bar]:
        return [
            Bar(
                on=session,
                close=start + index,
                adjusted_close=start + index,
                volume=1_000,
            )
            for index, session in enumerate(sessions)
        ]

    app_module._store().save_price_bars(
        {"RELIANCE": series(100), "^CNXENERGY": series(200), "^NSEI": series(300)}
    )

    response = client.get("/v1/prices/RELIANCE?range=1m")

    assert response.status_code == 200
    assert response.json()["sessions"] == 2


# --- the two transports --------------------------------------------------------


def register(client, email: str, transport: str = "cookie"):
    return client.post(
        "/v1/auth/register",
        json={"email": email, "password": PASSWORD, "transport": transport},
    )


def test_a_browser_gets_a_cookie_and_no_readable_token(client) -> None:
    """The HttpOnly cookie exists so scripts cannot read the session. Returning the token
    in the body for everyone would hand every browser a copy an XSS could steal."""
    response = register(client, "web@example.com")

    assert response.status_code == 201
    assert "session" not in response.json()
    assert client.cookies.get("swl_session") is not None


def test_a_native_client_gets_a_token_and_no_cookie(client) -> None:
    response = register(client, "mobile@example.com", transport="bearer")

    assert response.status_code == 201
    assert response.json()["session"]
    assert client.cookies.get("swl_session") is None, (
        "a token holder must not also carry an ambient credential"
    )


def test_a_bearer_token_reaches_the_same_authorization(client) -> None:
    token = register(client, "mobile@example.com", transport="bearer").json()["session"]
    client.cookies.clear()
    auth = {"Authorization": f"Bearer {token}"}

    assert client.get("/v1/auth/me", headers=auth).status_code == 200
    assert client.post("/v1/watchlist", json={"symbol": "INFY"}, headers=auth).status_code == 200
    assert [c["symbol"] for c in client.get("/v1/watchlist", headers=auth).json()["companies"]] == [
        "INFY"
    ]


def test_a_request_with_no_credential_is_still_refused(client) -> None:
    """Adding a transport must not add a way in."""
    assert client.get("/v1/watchlist").status_code == 401
    assert (
        client.get("/v1/watchlist", headers={"Authorization": "Bearer nonsense"}).status_code == 401
    )
    assert (
        client.get("/v1/watchlist", headers={"Authorization": "Basic whatever"}).status_code == 401
    )


def test_logout_revokes_the_session_whichever_transport_presented_it(client) -> None:
    """A native client discarding its token locally leaves the row usable by anyone who
    copied it. Revocation deletes the row, and there is only one row to delete."""
    token = register(client, "mobile@example.com", transport="bearer").json()["session"]
    client.cookies.clear()
    auth = {"Authorization": f"Bearer {token}"}

    client.post("/v1/auth/logout", headers=auth)

    assert client.get("/v1/auth/me", headers=auth).status_code == 401


def test_both_transports_see_one_review_window_and_one_order(client, app_module) -> None:
    """The whole point of one API: the same account reached two ways is the same state."""
    cookie_client = TestClient(app_module.app)
    register(cookie_client, "shared@example.com")
    token = cookie_client.post(
        "/v1/auth/login",
        json={"email": "shared@example.com", "password": PASSWORD, "transport": "bearer"},
    ).json()["session"]

    cookie_client.post("/v1/watchlist", json={"symbol": "RELIANCE", "tags": ["regulation"]})
    now = datetime.now(UTC)
    store_event(
        app_module, ref="high", symbol="RELIANCE", category="Outcome of Board Meeting", when=now
    )
    store_event(
        app_module,
        ref="routine",
        symbol="RELIANCE",
        category="Shareholders meeting",
        when=now - timedelta(days=1),
    )

    native = TestClient(app_module.app, headers={"Authorization": f"Bearer {token}"})
    from_web = cookie_client.get("/v1/review").json()
    from_native = native.get("/v1/review").json()

    assert [i["assessment"]["event_id"] for i in from_web["needs_attention"]] == [
        i["assessment"]["event_id"] for i in from_native["needs_attention"]
    ]
    assert from_web["attention_count"] == from_native["attention_count"]
    assert [i["assessment"]["focus"] for i in from_web["needs_attention"]] == [
        i["assessment"]["focus"] for i in from_native["needs_attention"]
    ]


def test_a_review_completed_on_one_transport_is_completed_on_the_other(client, app_module) -> None:
    """Checkpoints are server-authoritative, so the device that completed a review is
    not a property of the review."""
    register(client, "shared@example.com")
    token = client.post(
        "/v1/auth/login",
        json={"email": "shared@example.com", "password": PASSWORD, "transport": "bearer"},
    ).json()["session"]
    client.post("/v1/watchlist", json={"symbol": "RELIANCE"})

    native = TestClient(app_module.app, headers={"Authorization": f"Bearer {token}"})
    issued = native.get("/v1/review").json()
    native.post("/v1/review/complete", json={"review_id": issued["review_id"]})

    assert client.get("/v1/review").json()["previous_checkpoint"] == issued["review_cutoff"]
