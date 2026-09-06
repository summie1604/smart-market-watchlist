"""Judge mode (D42).

The fixture exists to make the real product logic demonstrable, not to fake it. So the
tests are mostly about the boundary: that seeding runs the production path, that judge
state cannot reach a live database, and that nothing about live mode moved.
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from smart_watchlist.adapters.sqlite_store import SqliteAssessmentStore
from smart_watchlist.adapters.user_store import SqliteUserStore
from smart_watchlist.core.models import CoverageStatus
from smart_watchlist.demo import judge_db_path, reset, seed, seeded

FIXED = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


def _bar():
    from smart_watchlist.core.market import Bar

    return Bar(
        on=FIXED.date(),
        close=100.0,
        adjusted_close=100.0,
        volume=1000.0,
        split_ratio=0.0,
        dividend=0.0,
    )


@pytest.fixture
def judge_db(tmp_path):
    return str(tmp_path / "judge.db")


def levels(path: str) -> dict[str, list[tuple[str, int, tuple[str, ...]]]]:
    """Every company's assessments, as the engine produced them."""
    out: dict[str, list[tuple[str, int, tuple[str, ...]]]] = {}
    for a in SqliteAssessmentStore(path).recent(200):
        out.setdefault(a.event.security_symbol, []).append(
            (a.attention.value, a.score, tuple(r.code for r in a.reasons))
        )
    return out


# --- seeding ---------------------------------------------------------------------


def test_seeding_an_empty_database_produces_the_scenario(judge_db) -> None:
    seed(judge_db, now=FIXED)

    by_symbol = levels(judge_db)
    assert seeded(judge_db)
    assert set(by_symbol) >= {"RELIANCE", "TCS", "INFY"}


def test_seeding_is_idempotent(judge_db) -> None:
    """A restarting container must not accumulate a second copy of the scenario."""
    seed(judge_db, now=FIXED)
    before = levels(judge_db)

    seed(judge_db, now=FIXED)

    assert levels(judge_db) == before


def test_no_provider_is_reachable_during_seeding(judge_db, monkeypatch) -> None:
    """The whole point: judging cannot depend on NSE, Google News, yfinance or a quota."""
    from smart_watchlist.adapters.gemini_extractor import GeminiExtractor
    from smart_watchlist.adapters.google_news import GoogleNewsSource
    from smart_watchlist.adapters.nse_disclosures import NseDisclosureSource
    from smart_watchlist.adapters.yfinance_market import YFinanceMarketSource

    def explode(*args, **kwargs):
        raise AssertionError("judge mode reached an external provider")

    monkeypatch.setattr(YFinanceMarketSource, "fetch", explode)
    monkeypatch.setattr(GoogleNewsSource, "fetch", explode)
    monkeypatch.setattr(NseDisclosureSource, "fetch", explode)
    monkeypatch.setattr(GeminiExtractor, "extract", explode)

    seed(judge_db, now=FIXED)

    assert levels(judge_db)


# --- what the engine decided, not what the fixture asserted ------------------------


def test_the_high_attention_company_reaches_high_through_the_real_ledger(judge_db) -> None:
    """RELIANCE: a filing, an unusual company-specific move, three independent reports."""
    seed(judge_db, now=FIXED)

    reliance = levels(judge_db)["RELIANCE"]
    highs = [entry for entry in reliance if entry[0] == "HIGH"]
    assert highs, "the scenario must actually produce a HIGH through the engine"

    filed = next(e for e in reliance if "AUTHORITATIVE_DISCLOSURE" in e[2])
    assert filed[0] == "HIGH"
    assert "MATERIAL_EVENT_TYPE" in filed[2]

    reported = next(e for e in reliance if "INDEPENDENT_CORROBORATION" in e[2])
    assert reported[0] == "HIGH"
    assert "NEWS_COINCIDES_WITH_MOVE" in reported[2], "the move and the report coincide"
    assert "MOVE_EXPLAINED_BY_SECTOR" not in reported[2], "and the sector does not explain it"


def test_the_medium_company_proves_attention_is_not_price_movement(judge_db) -> None:
    """TCS: corroborated reporting, no unusual move. MEDIUM, and for a stated reason."""
    seed(judge_db, now=FIXED)

    tcs = next(e for e in levels(judge_db)["TCS"] if "COMPANY_SPECIFIC_EVENT" in e[2])

    assert tcs[0] == "MEDIUM"
    assert "INDEPENDENT_CORROBORATION" in tcs[2]
    assert "NO_MARKET_REACTION" in tcs[2]


def test_the_sector_explained_company_says_the_sector_explains_it(judge_db) -> None:
    seed(judge_db, now=FIXED)

    tmpv = levels(judge_db)["TMPV"][0]

    assert "UNUSUAL_PRICE_MOVE" in tmpv[2]
    assert "MOVE_EXPLAINED_BY_SECTOR" in tmpv[2]


def test_a_company_with_nothing_new_is_not_silently_called_quiet(judge_db) -> None:
    """ITC has no assessment at all, and the market family is degraded — so the review owes
    the reader "could not evaluate", never "nothing happened"."""
    seed(judge_db, now=FIXED)
    store = SqliteAssessmentStore(judge_db)

    assert "ITC" not in levels(judge_db)

    market = store.latest_run("market")
    assert market is not None
    assert not market.is_healthy, "a missing security degrades the family, honestly"
    assert any(record.status is not CoverageStatus.OK for record in market.coverage.records)


def test_the_coverage_gap_is_visible_on_the_company_that_causes_it(judge_db) -> None:
    """INFY: no market data, so its assessment records the missing observation and its
    price is unavailable rather than guessed."""
    seed(judge_db, now=FIXED)

    infy = levels(judge_db)["INFY"][0]

    assert "NO_MARKET_OBSERVATION" in infy[2]
    assert SqliteAssessmentStore(judge_db).price_bars(["INFY"]).get("INFY") is None


def test_the_watch_point_settles_through_the_ordinary_evaluator(judge_db) -> None:
    """Not a badge written by hand: a level set before the session that crosses it."""
    seed(judge_db, now=FIXED)

    users = SqliteUserStore(judge_db)
    point = users.watch_points(users.demo_user().user_id)[0]

    assert point.symbol == "HDFCBANK"
    assert point.triggered_on is not None
    assert point.triggered_close is not None and point.triggered_close >= point.level
    assert point.created_at.date() < point.triggered_on, "set before the crossing session"
    assert point.needs_attention


def test_the_review_window_holds_the_whole_scenario(judge_db) -> None:
    seed(judge_db, now=FIXED)

    users = SqliteUserStore(judge_db)
    checkpoint = users.checkpoint(users.demo_user().user_id)

    assert checkpoint is not None
    assert timedelta(hours=18) < FIXED - checkpoint < timedelta(hours=20)


# --- isolation from live state -----------------------------------------------------


def test_the_judge_path_is_never_the_live_path(monkeypatch) -> None:
    monkeypatch.setenv("WATCHLIST_DB", "/data/watchlist.db")
    monkeypatch.delenv("JUDGE_DB", raising=False)

    assert judge_db_path() != "/data/watchlist.db"
    assert "judge" in judge_db_path()


def test_seeding_refuses_a_database_that_holds_real_records(tmp_path) -> None:
    """A misconfigured path fails loudly rather than writing fixtures over live data."""
    live = str(tmp_path / "live.db")
    store = SqliteAssessmentStore(live)
    # A real record, not just an empty schema — that is what makes it somebody's data.
    store.save_price_bars({"RELIANCE": [_bar()]})

    with pytest.raises(RuntimeError, match="Refusing to seed"):
        seed(live, now=FIXED)


def test_reset_refuses_a_database_that_is_not_a_fixture(tmp_path) -> None:
    live = str(tmp_path / "live.db")
    SqliteAssessmentStore(live).save_price_bars({"RELIANCE": [_bar()]})

    with pytest.raises(RuntimeError, match="Refusing to reset"):
        reset(live, now=FIXED)


def test_reset_restores_the_initial_scenario(judge_db) -> None:
    seed(judge_db, now=FIXED)
    users = SqliteUserStore(judge_db)
    user = users.demo_user()
    users.set_checkpoint(user.user_id, FIXED)  # as if a judge completed the review
    before = levels(judge_db)

    reset(judge_db, now=FIXED)

    after_users = SqliteUserStore(judge_db)
    restored = after_users.checkpoint(after_users.demo_user().user_id)
    assert levels(judge_db) == before
    assert restored is not None and restored < FIXED, "the review window is back"
    assert after_users.watch_points(after_users.demo_user().user_id)[0].needs_attention


# --- the application in each mode ---------------------------------------------------


@pytest.fixture
def judge_app(tmp_path, monkeypatch):
    monkeypatch.setenv("SMART_WATCHLIST_MODE", "judge")
    monkeypatch.setenv("JUDGE_DB", str(tmp_path / "judge.db"))
    monkeypatch.setenv("WATCHLIST_DB", str(tmp_path / "live.db"))
    monkeypatch.setenv("DEMO_MODE", "on")
    import smart_watchlist.api.app as module

    importlib.reload(module)
    return module


def test_judge_mode_serves_the_scenario_and_says_it_is_judge_mode(judge_app) -> None:
    with TestClient(judge_app.app) as client:
        meta = client.get("/v1/meta").json()
        review = client.get("/v1/review").json()

    assert meta["mode"] == "judge"
    assert review["needs_attention"], "the hero must have something in it"
    assert review["triggered_watch_points"], "and a triggered level"


def test_judge_mode_runs_no_scheduler(judge_app) -> None:
    """A cycle would replace the scenario with whatever the market is doing."""
    with TestClient(judge_app.app) as client:
        status = client.get("/v1/scheduler").json()
        triggered = client.post("/v1/ingest")

    assert status["enabled"] is False
    assert triggered.status_code == 409


def test_the_assistant_answers_from_the_seeded_records(judge_app) -> None:
    with TestClient(judge_app.app) as client:
        watchlist = client.post(
            "/v1/assistant/ask", json={"question": "What needs my attention?"}
        ).json()
        company = client.post(
            "/v1/assistant/ask", json={"question": "Why did this move?", "symbol": "RELIANCE"}
        ).json()
        advice = client.post("/v1/assistant/ask", json={"question": "Should I buy this?"}).json()

    assert watchlist["answered"] and "RELIANCE" in " ".join(
        s["text"] for s in watchlist["statements"]
    )
    assert company["answered"] and company["evidence"]
    assert advice["answered"] is False and advice["evidence"] == []


def test_completing_a_review_advances_the_checkpoint_in_judge_mode(judge_app) -> None:
    with TestClient(judge_app.app) as client:
        issued = client.get("/v1/review").json()
        client.post("/v1/review/complete", json={"review_id": issued["review_id"]})
        after = client.get("/v1/review").json()

    assert after["previous_checkpoint"] == issued["review_cutoff"]
    assert after["needs_attention"] == [], "caught up"


def test_reset_restores_the_demo_over_http(judge_app) -> None:
    with TestClient(judge_app.app) as client:
        issued = client.get("/v1/review").json()
        client.post("/v1/review/complete", json={"review_id": issued["review_id"]})
        assert client.get("/v1/review").json()["needs_attention"] == []

        assert client.post("/v1/judge/reset").status_code == 200
        assert client.get("/v1/review").json()["needs_attention"]


def test_live_mode_has_no_reset_route_and_no_fixtures(tmp_path, monkeypatch) -> None:
    """Live mode is unchanged: no fixture records, and the reset route does not exist."""
    monkeypatch.setenv("SMART_WATCHLIST_MODE", "live")
    monkeypatch.setenv("WATCHLIST_DB", str(tmp_path / "live.db"))
    monkeypatch.setenv("INGEST_SCHEDULER", "off")
    monkeypatch.setenv("DEMO_MODE", "on")
    import smart_watchlist.api.app as module

    importlib.reload(module)
    client = TestClient(module.app)

    assert module.MODE == "live"
    assert client.get("/v1/meta").json()["mode"] == "live"
    assert client.get("/v1/assessments").json()["count"] == 0, "no fixtures leaked in"
    assert client.post("/v1/judge/reset").status_code == 404


def test_an_unknown_mode_fails_visibly(tmp_path, monkeypatch) -> None:
    """Misconfiguration must not silently mix modes."""
    monkeypatch.setenv("SMART_WATCHLIST_MODE", "demo")
    monkeypatch.setenv("WATCHLIST_DB", str(tmp_path / "live.db"))
    import smart_watchlist.api.app as module

    with pytest.raises(RuntimeError, match="must be 'live' or 'judge'"):
        importlib.reload(module)


def test_the_fixture_scenario_collapses_to_one_reliance_development(judge_app) -> None:
    """The presentation problem this grouping exists to fix, on the real fixture (D43).

    Generic: the assertion is about how many developments the grouping produced, never
    about RELIANCE or a fixture event id.
    """
    with TestClient(judge_app.app) as client:
        items = client.get("/v1/review").json()["needs_attention"]

    reliance = [i for i in items if i["symbol"] == "RELIANCE"]
    story = [i for i in reliance if "approves" in i["assessment"]["description"]]
    developments = {i["development_id"] for i in story}

    assert len(story) >= 3, "the underlying records are all still there"
    assert len(developments) == 1, "and a reader sees one development"
    assert story[0]["development_id"] == story[0]["assessment"]["event_id"], (
        "the primary is the canonical first, pointing at itself"
    )
    assert story[0]["development_sources"] >= 2, "counted across the whole development"

    # The unusual move coincides with the story and stays its own item: grouping it in
    # would assert a cause the system deliberately does not claim.
    move = next(i for i in reliance if "moved" in i["assessment"]["description"])
    assert move["development_id"] not in developments


def test_grouping_never_reaches_across_companies_in_the_fixture(judge_app) -> None:
    with TestClient(judge_app.app) as client:
        items = client.get("/v1/review").json()["needs_attention"]

    by_development: dict[str, set[str]] = {}
    for item in items:
        by_development.setdefault(item["development_id"], set()).add(item["symbol"])

    assert all(len(symbols) == 1 for symbols in by_development.values())


def test_grouping_does_not_change_what_the_review_covers(judge_app) -> None:
    """Completing a review advances across the same underlying records, grouped or not.

    A collapsed child must never survive as unreviewed.
    """
    with TestClient(judge_app.app) as client:
        before = client.get("/v1/review").json()
        underlying = {i["assessment"]["event_id"] for i in before["needs_attention"]}
        client.post("/v1/review/complete", json={"review_id": before["review_id"]})
        after = client.get("/v1/review").json()

    assert len(underlying) >= len({i["development_id"] for i in before["needs_attention"]})
    assert after["needs_attention"] == [], "every grouped record was part of the window"
    assert after["previous_checkpoint"] == before["review_cutoff"]
