"""The conversational assistant (D40).

It is an interface to the existing intelligence, so the tests are mostly about what it
refuses to become: a second data path, a second explanation engine, or a route around the
grounding gate. The company-scope answers are the explainer's, already covered in
``test_explainer``; what is pinned here is scope routing, context handling, and the
boundaries.
"""

from __future__ import annotations

import importlib
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from support import coverage, make_evidence

from smart_watchlist.core.engine import assess
from smart_watchlist.core.market import Bar
from smart_watchlist.core.models import Event


@pytest.fixture
def app_module(tmp_path, monkeypatch):
    monkeypatch.setenv("WATCHLIST_DB", str(tmp_path / "assistant.db"))
    monkeypatch.setenv("DEMO_MODE", "on")
    import smart_watchlist.api.app as module

    importlib.reload(module)
    return module


@pytest.fixture
def client(app_module):
    return TestClient(app_module.app)


def store_event(
    app_module,
    *,
    ref: str,
    symbol: str = "RELIANCE",
    category: str = "Outcome of Board Meeting",
    source: str = "nse-disclosures",
    when: datetime | None = None,
) -> None:
    from dataclasses import replace

    moment = when or datetime.now(UTC)
    evidence = replace(
        make_evidence(symbol=symbol, category=category, ref=ref),
        source=source,
        published_at=moment,
    )
    app_module._store().save(
        assess(
            Event(
                event_id=ref,
                security_symbol=symbol,
                company_name=symbol,
                event_type=category,
                description=f"{symbol}: {category}",
                occurred_at=moment,
                evidence=(evidence,),
            ),
            coverage(),
        )
    )


def seed_bars(app_module, symbol: str, closes: list[tuple[str, float]]) -> None:
    app_module._store().save_price_bars(
        {
            symbol: [
                Bar(
                    on=date.fromisoformat(day),
                    close=close,
                    adjusted_close=close,
                    volume=1000.0,
                    split_ratio=0.0,
                    dividend=0.0,
                )
                for day, close in closes
            ]
        }
    )


def ask(client, question: str, symbol: str | None = None):
    body: dict[str, object] = {"question": question}
    if symbol is not None:
        body["symbol"] = symbol
    return client.post("/v1/assistant/ask", json=body)


# --- 1. watchlist-level question --------------------------------------------------


def test_a_watchlist_question_is_answered_across_the_watchlist(client, app_module) -> None:
    client.post("/v1/watchlist", json={"symbol": "RELIANCE"})
    client.post("/v1/watchlist", json={"symbol": "INFY"})
    store_event(app_module, ref="r1", symbol="RELIANCE")

    body = ask(client, "What needs my attention?").json()

    assert body["scope"] == "watchlist"
    assert body["symbol"] is None
    assert body["intent"] == "watchlist_attention"
    assert body["answered"] is True


def test_biggest_movers_come_from_stored_closes(client, app_module) -> None:
    client.post("/v1/watchlist", json={"symbol": "RELIANCE"})
    client.post("/v1/watchlist", json={"symbol": "INFY"})
    seed_bars(app_module, "RELIANCE", [("2026-09-03", 100.0), ("2026-09-04", 110.0)])
    # INFY has no stored close at all.

    body = ask(client, "What are my biggest movers?").json()
    text = " ".join(s["text"] for s in body["statements"])

    assert body["answered"] is True
    assert "RELIANCE" in text and "10.00%" in text
    assert "No stored close for INFY" in text, "absence is named, not counted as flat"


# --- 2 and 3. company questions, with and without a ticker -------------------------


def test_a_company_question_uses_the_symbol_it_is_given(client, app_module) -> None:
    client.post("/v1/watchlist", json={"symbol": "RELIANCE"})
    store_event(app_module, ref="r1")

    body = ask(client, "Why does this need my attention?", symbol="RELIANCE").json()

    assert body["scope"] == "company"
    assert body["symbol"] == "RELIANCE"
    assert body["intent"] == "why_attention"
    assert body["answered"] is True


def test_a_question_with_no_ticker_uses_the_company_in_view(client, app_module) -> None:
    """The context requirement: "why did this fall?" while looking at RELIANCE."""
    store_event(app_module, ref="r1")

    body = ask(client, "Why did this fall?", symbol="RELIANCE").json()

    assert body["scope"] == "company"
    assert body["company"] == "Reliance Industries Limited"


def test_the_same_question_without_context_asks_which_company(client) -> None:
    body = ask(client, "Why did this fall?").json()

    assert body["answered"] is False
    assert body["insufficient_reason"] == "needs-a-company"
    assert body["suggestions"], "a refusal still offers what can be asked"


def test_a_watchlist_question_asked_from_a_company_page_answers_at_its_own_scope(
    client, app_module
) -> None:
    """Context is a hint, not a cage. Narrowing "what are my biggest movers" to one
    company would answer a question nobody asked."""
    client.post("/v1/watchlist", json={"symbol": "RELIANCE"})
    seed_bars(app_module, "RELIANCE", [("2026-09-03", 100.0), ("2026-09-04", 110.0)])

    body = ask(client, "What are my biggest movers?", symbol="RELIANCE").json()

    assert body["scope"] == "watchlist"


# --- 5 and 6. evidence, and its absence -------------------------------------------


def test_an_answer_carries_the_evidence_behind_it(client, app_module) -> None:
    client.post("/v1/watchlist", json={"symbol": "RELIANCE"})
    store_event(app_module, ref="r1")

    body = ask(client, "What needs my attention?").json()

    assert body["evidence"], "cited events travel with their sources"
    assert all("standing_label" in e for e in body["evidence"]), (
        "the same source-standing labels the rest of the product uses (D36)"
    )


def test_no_relevant_evidence_says_so(client) -> None:
    client.post("/v1/watchlist", json={"symbol": "RELIANCE"})

    body = ask(client, "What alerts have triggered?").json()

    assert body["answered"] is False
    assert body["insufficient_reason"] == "no-record-of-that"
    assert body["evidence"] == []


def test_disclosures_are_selected_by_evidence_not_by_wording(client, app_module) -> None:
    client.post("/v1/watchlist", json={"symbol": "RELIANCE"})
    store_event(app_module, ref="filed", source="nse-disclosures")
    store_event(app_module, ref="reported", source="news", category="Agreements")

    body = ask(client, "Any important disclosures?").json()
    cited = {i for s in body["statements"] for i in s["event_ids"]}

    assert body["answered"] is True
    assert "filed" in cited
    assert "reported" not in cited, "a report about a filing is not a filing"


# --- 7 and 9. what it will not do --------------------------------------------------


def test_advice_is_refused_at_both_scopes(client, app_module) -> None:
    client.post("/v1/watchlist", json={"symbol": "RELIANCE"})
    store_event(app_module, ref="r1")

    for symbol in (None, "RELIANCE"):
        body = ask(client, "Should I buy this?", symbol=symbol).json()
        assert body["answered"] is False, symbol
        assert body["intent"] == "out_of_scope_advice", symbol
        assert body["evidence"] == [], "a refusal cites nothing because it claims nothing"


def test_an_unsupported_question_offers_what_can_be_asked(client) -> None:
    body = ask(client, "Who is the chief executive?").json()

    assert body["answered"] is False
    assert body["insufficient_reason"] == "unsupported"
    assert len(body["suggestions"]) >= 3


def test_the_assistant_cannot_reach_outside_the_system(client, app_module, monkeypatch) -> None:
    """The grounding boundary, tested rather than asserted: every route out is closed and
    every question still answers."""
    from smart_watchlist.adapters.gemini_extractor import GeminiExtractor
    from smart_watchlist.adapters.google_news import GoogleNewsSource
    from smart_watchlist.adapters.nse_disclosures import NseDisclosureSource
    from smart_watchlist.adapters.yfinance_market import YFinanceMarketSource

    def explode(*args, **kwargs):
        raise AssertionError("the assistant reached an external source")

    monkeypatch.setattr(YFinanceMarketSource, "fetch", explode)
    monkeypatch.setattr(GoogleNewsSource, "fetch", explode)
    monkeypatch.setattr(NseDisclosureSource, "fetch", explode)
    monkeypatch.setattr(GeminiExtractor, "extract", explode)

    client.post("/v1/watchlist", json={"symbol": "RELIANCE"})
    store_event(app_module, ref="r1")
    before = len(app_module._store().recent(200))

    for question, symbol in (
        ("What needs my attention?", None),
        ("What are my biggest movers?", None),
        ("Any important disclosures?", None),
        ("Why does this need my attention?", "RELIANCE"),
        ("What did the price do?", "RELIANCE"),
    ):
        assert ask(client, question, symbol).status_code == 200, question

    assert len(app_module._store().recent(200)) == before, "no ingestion happened"


def test_every_statement_about_the_world_names_its_records(client, app_module) -> None:
    """The grounding gate the explainer already enforces, at the new scope."""
    client.post("/v1/watchlist", json={"symbol": "RELIANCE"})
    store_event(app_module, ref="r1")

    body = ask(client, "What needs my attention?").json()
    described = [s for s in body["statements"] if "RELIANCE" in s["text"]]

    assert described
    assert all(s["event_ids"] for s in described)


def test_the_answer_names_the_path_that_produced_it(client) -> None:
    body = ask(client, "What needs my attention?").json()

    assert body["generated_by"] == "deterministic/explainer/v1"
    assert "not investment advice" in body["disclaimer"]


def test_an_unsupported_security_as_context_is_refused(client) -> None:
    assert ask(client, "what changed?", symbol="NOTREAL").status_code == 404


# --- 10 and 11. nothing else moved -------------------------------------------------


def test_the_existing_explain_endpoint_is_unchanged(client, app_module) -> None:
    """Both routes reach the same records through the same code; the older contract keeps
    its exact shape."""
    client.post("/v1/watchlist", json={"symbol": "RELIANCE"})
    store_event(app_module, ref="r1")

    direct = client.post(
        "/v1/companies/RELIANCE/explain", json={"question": "Why does this matter?"}
    ).json()
    via_assistant = ask(client, "Why does this matter?", symbol="RELIANCE").json()

    assert "scope" not in direct, "the explainer's response shape did not change"
    assert direct["symbol"] == "RELIANCE"
    assert [s["text"] for s in direct["statements"]] == [
        s["text"] for s in via_assistant["statements"]
    ], "one implementation behind both callers"


def test_the_dashboard_endpoints_still_answer(client, app_module) -> None:
    client.post("/v1/watchlist", json={"symbol": "RELIANCE"})
    store_event(app_module, ref="r1")

    assert client.get("/v1/review").status_code == 200
    assert client.get("/v1/assessments").status_code == 200
    assert client.get("/v1/watchlist").status_code == 200
    assert client.get("/v1/prices/status").status_code == 200
    assert client.get("/v1/watch-points").status_code == 200


def test_alerts_are_reported_from_the_watch_points_that_exist(client, app_module) -> None:
    from smart_watchlist.core.ingestion import _settle_watch_points

    client.post("/v1/watchlist", json={"symbol": "RELIANCE"})
    seed_bars(app_module, "RELIANCE", [("2026-09-04", 1000.0)])
    client.post("/v1/companies/RELIANCE/watch-points", json={"level": 1100, "note": "the IPO"})

    waiting = ask(client, "What alerts have triggered?").json()
    assert waiting["answered"] is True
    assert "still waiting" in " ".join(s["text"] for s in waiting["statements"])

    seed_bars(app_module, "RELIANCE", [("2026-09-08", 1150.0)])
    _settle_watch_points(app_module._store(), app_module._USER_STORE)

    reached = ask(client, "What alerts have triggered?").json()
    text = " ".join(s["text"] for s in reached["statements"])
    assert "at or above 1,100.00" in text
    assert "the IPO" in text
    assert "2026-09-08" in text
