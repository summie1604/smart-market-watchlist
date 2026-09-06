"""Watch points (D37): a level the reader asked about, settled on stored closes.

The feature is small; what makes it safe is what it refuses to do. It never predicts,
never pushes, never fires twice, never fires from a session that had already closed when
the level was set, and never changes a verdict anyone else can see.
"""

from __future__ import annotations

import importlib
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from smart_watchlist.core.market import Bar
from smart_watchlist.core.watchpoints import (
    WatchDirection,
    WatchPoint,
    direction_for,
    evaluate,
    rejection_for,
)

NOW = datetime(2026, 9, 5, 12, tzinfo=UTC)


def bar(day: str, close: float) -> Bar:
    return Bar(
        on=date.fromisoformat(day),
        close=close,
        adjusted_close=close,
        volume=1000.0,
        split_ratio=0.0,
        dividend=0.0,
    )


def point(**over) -> WatchPoint:
    base = {
        "point_id": "p1",
        "user_id": "u1",
        "symbol": "RELIANCE",
        "level": 1400.0,
        "direction": WatchDirection.ABOVE,
        "note": "watch out for the Jio listing",
        "created_at": NOW,
        "created_close": 1300.0,
    }
    return WatchPoint(**{**base, **over})


# --- setting one -----------------------------------------------------------------


def test_direction_is_inferred_from_where_the_price_is_now() -> None:
    """Asking the reader would be a question with only one correct answer."""
    assert direction_for(1400.0, 1300.0) is WatchDirection.ABOVE
    assert direction_for(1200.0, 1300.0) is WatchDirection.BELOW


def test_a_level_is_refused_when_there_is_nothing_to_measure_it_against() -> None:
    assert "no end-of-day close" in (rejection_for(1400.0, None) or "")


def test_a_level_exactly_where_it_closed_is_refused() -> None:
    """There is no crossing to wait for, and the reader meant a different number."""
    assert "Choose a level above or below" in (rejection_for(1300.0, 1300.0) or "")


def test_a_usable_level_is_accepted_in_either_direction() -> None:
    assert rejection_for(1400.0, 1300.0) is None
    assert rejection_for(1200.0, 1300.0) is None


def test_a_negative_level_is_not_a_price() -> None:
    assert rejection_for(-5.0, 1300.0) is not None


# --- settling one ----------------------------------------------------------------


def test_a_close_at_or_beyond_the_level_satisfies_it() -> None:
    """At the level counts: a close exactly on the number the reader named is the thing
    they asked about."""
    trigger = evaluate(point(), [bar("2026-09-08", 1400.0)])

    assert trigger is not None
    assert trigger.on == date(2026, 9, 8)
    assert trigger.close == 1400.0


def test_a_close_short_of_the_level_does_not() -> None:
    assert evaluate(point(), [bar("2026-09-08", 1399.99)]) is None


def test_a_downward_point_is_satisfied_by_a_fall() -> None:
    falling = point(level=1200.0, direction=WatchDirection.BELOW)

    assert evaluate(falling, [bar("2026-09-08", 1199.0)]) is not None
    assert evaluate(falling, [bar("2026-09-08", 1250.0)]) is None


def test_the_first_crossing_wins() -> None:
    trigger = evaluate(
        point(),
        [bar("2026-09-10", 1500.0), bar("2026-09-08", 1405.0), bar("2026-09-09", 1450.0)],
    )

    assert trigger is not None
    assert trigger.on == date(2026, 9, 8), "unordered bars must not change the answer"


def test_a_session_that_had_already_closed_is_not_news() -> None:
    """A point is a question about what happens next. Answering it from a session that
    had already closed when it was set would report history as news."""
    assert evaluate(point(), [bar("2026-09-04", 1500.0), bar("2026-09-05", 1500.0)]) is None


def test_an_already_triggered_point_never_triggers_again() -> None:
    """The idempotence that lets an unattended schedule run as often as it likes."""
    fired = point(triggered_on=date(2026, 9, 8), triggered_close=1405.0)

    assert evaluate(fired, [bar("2026-09-09", 1600.0)]) is None


def test_only_a_triggered_and_unseen_point_asks_for_anything() -> None:
    assert point().needs_attention is False
    assert point(triggered_on=date(2026, 9, 8), triggered_close=1405.0).needs_attention is True
    assert (
        point(
            triggered_on=date(2026, 9, 8), triggered_close=1405.0, acknowledged_at=NOW
        ).needs_attention
        is False
    )


# --- over HTTP -------------------------------------------------------------------


@pytest.fixture
def app_module(tmp_path, monkeypatch):
    monkeypatch.setenv("WATCHLIST_DB", str(tmp_path / "watch.db"))
    monkeypatch.setenv("DEMO_MODE", "on")
    import smart_watchlist.api.app as module

    importlib.reload(module)
    return module


@pytest.fixture
def client(app_module):
    return TestClient(app_module.app)


def seed_bars(app_module, closes: list[tuple[str, float]], symbol: str = "RELIANCE") -> None:
    app_module._store().save_price_bars({symbol: [bar(day, close) for day, close in closes]})


def test_a_level_can_be_set_with_a_note(client, app_module) -> None:
    seed_bars(app_module, [("2026-09-03", 1290.0), ("2026-09-04", 1300.0)])

    created = client.post(
        "/v1/companies/RELIANCE/watch-points",
        json={"level": 1400, "note": "watch out for the Jio listing"},
    )

    assert created.status_code == 200
    body = created.json()
    assert body["direction"] == "ABOVE"
    assert body["created_close"] == 1300.0
    assert body["note"] == "watch out for the Jio listing"
    assert body["needs_attention"] is False


def test_a_level_already_reached_is_refused_with_the_reason(client, app_module) -> None:
    seed_bars(app_module, [("2026-09-04", 1300.0)])

    refused = client.post("/v1/companies/RELIANCE/watch-points", json={"level": 1300})

    assert refused.status_code == 422
    assert "Choose a level above or below" in refused.json()["detail"]


def test_an_unsupported_security_has_no_levels(client) -> None:
    assert client.post("/v1/companies/NOTREAL/watch-points", json={"level": 10}).status_code == 404


def test_setting_a_level_never_reaches_a_price_feed(client, app_module, monkeypatch) -> None:
    from smart_watchlist.adapters.yfinance_market import YFinanceMarketSource

    def explode(*args, **kwargs):
        raise AssertionError("setting a watch point reached an external source")

    monkeypatch.setattr(YFinanceMarketSource, "fetch", explode)
    seed_bars(app_module, [("2026-09-04", 1300.0)])

    assert (
        client.post("/v1/companies/RELIANCE/watch-points", json={"level": 1400}).status_code == 200
    )


def test_a_cycle_settles_a_point_against_stored_bars_and_surfaces_it(client, app_module) -> None:
    """End to end: set a level, a later session crosses it, the review carries it."""
    from smart_watchlist.core.ingestion import _settle_watch_points

    client.post("/v1/watchlist", json={"symbol": "RELIANCE"})
    seed_bars(app_module, [("2026-09-04", 1300.0)])
    client.post("/v1/companies/RELIANCE/watch-points", json={"level": 1400, "note": "Jio listing"})

    seed_bars(app_module, [("2026-09-08", 1405.0)])
    settled = _settle_watch_points(app_module._store(), app_module._USER_STORE)

    assert settled == 1
    triggered = client.get("/v1/review").json()["triggered_watch_points"]
    assert len(triggered) == 1
    assert triggered[0]["triggered_close"] == 1405.0
    assert triggered[0]["triggered_on"] == "2026-09-08"


def test_a_second_cycle_announces_nothing_twice(client, app_module) -> None:
    """The property that makes a fifteen-minute schedule safe."""
    from smart_watchlist.core.ingestion import _settle_watch_points

    seed_bars(app_module, [("2026-09-04", 1300.0)])
    client.post("/v1/companies/RELIANCE/watch-points", json={"level": 1400})
    seed_bars(app_module, [("2026-09-08", 1405.0)])

    assert _settle_watch_points(app_module._store(), app_module._USER_STORE) == 1
    assert _settle_watch_points(app_module._store(), app_module._USER_STORE) == 0


def test_acknowledging_stops_it_asking_without_deleting_it(client, app_module) -> None:
    from smart_watchlist.core.ingestion import _settle_watch_points

    seed_bars(app_module, [("2026-09-04", 1300.0)])
    created = client.post("/v1/companies/RELIANCE/watch-points", json={"level": 1400}).json()
    seed_bars(app_module, [("2026-09-08", 1405.0)])
    _settle_watch_points(app_module._store(), app_module._USER_STORE)

    client.post(f"/v1/watch-points/{created['point_id']}/acknowledge")

    assert client.get("/v1/review").json()["triggered_watch_points"] == []
    kept = client.get("/v1/watch-points").json()["points"][0]
    assert kept["triggered_on"] == "2026-09-08", "the record of what happened survives"
    assert kept["needs_attention"] is False


def test_a_watch_point_is_private_to_its_owner(client, app_module) -> None:
    """It is the reader's bookmark, not a verdict anyone else can see."""
    monkey = TestClient(app_module.app)
    seed_bars(app_module, [("2026-09-04", 1300.0)])
    client.post("/v1/companies/RELIANCE/watch-points", json={"level": 1400})
    created = client.get("/v1/watch-points").json()["points"][0]

    other = monkey.post(
        "/v1/auth/register", json={"email": "other@example.com", "password": "a long password"}
    )
    assert other.status_code == 201

    assert monkey.get("/v1/watch-points").json()["points"] == []
    assert monkey.delete(f"/v1/watch-points/{created['point_id']}").json()["removed"] is False


def test_a_triggered_point_changes_no_assessment(client, app_module) -> None:
    """Private state produces a private observation. Shared verdicts are untouched."""
    from smart_watchlist.core.ingestion import _settle_watch_points

    seed_bars(app_module, [("2026-09-04", 1300.0)])
    client.post("/v1/companies/RELIANCE/watch-points", json={"level": 1400})
    before = client.get("/v1/assessments").json()

    seed_bars(app_module, [("2026-09-08", 1405.0)])
    _settle_watch_points(app_module._store(), app_module._USER_STORE)

    assert client.get("/v1/assessments").json() == before


# --- percentage points (D39) ------------------------------------------------------


def percent_point(**over) -> WatchPoint:
    defaults = {
        "level": 5.0,
        "direction": WatchDirection.PERCENT_DOWN,
        "created_close": 1000.0,
    }
    return point(**{**defaults, **over})


def test_a_percentage_fall_is_measured_from_the_frozen_baseline() -> None:
    """Down 5% means down from where it was when you said so, not from yesterday."""
    assert evaluate(percent_point(), [bar("2026-09-08", 950.0)]) is not None
    assert evaluate(percent_point(), [bar("2026-09-08", 951.0)]) is None


def test_a_percentage_rise_uses_the_same_baseline() -> None:
    rising = percent_point(direction=WatchDirection.PERCENT_UP)

    assert evaluate(rising, [bar("2026-09-08", 1050.0)]) is not None
    assert evaluate(rising, [bar("2026-09-08", 1049.0)]) is None


def test_the_baseline_does_not_follow_the_price() -> None:
    """The property that makes a slow decline reachable.

    Three sessions each 2% below the last: no single step is a 5% move, but the total is,
    and a baseline that reset each session would never register it.
    """
    steps = [bar("2026-09-08", 980.0), bar("2026-09-09", 960.4), bar("2026-09-10", 941.2)]

    trigger = evaluate(percent_point(), steps)

    assert trigger is not None
    assert trigger.on == date(2026, 9, 10)


def test_a_percentage_point_without_a_baseline_cannot_be_satisfied() -> None:
    """No baseline is not a reason to guess one."""
    assert evaluate(percent_point(created_close=None), [bar("2026-09-08", 1.0)]) is None


def test_a_zero_percent_move_is_refused() -> None:
    from smart_watchlist.core.watchpoints import percent_rejection_for

    assert percent_rejection_for(0, 1000.0) is not None
    assert percent_rejection_for(-5, 1000.0) is None
    assert percent_rejection_for(-5, None) is not None


def test_absolute_points_are_unchanged_by_the_percentage_path() -> None:
    """Existing ABOVE/BELOW behaviour must be untouched."""
    assert evaluate(point(), [bar("2026-09-08", 1400.0)]) is not None
    assert (
        evaluate(point(level=1200.0, direction=WatchDirection.BELOW), [bar("2026-09-08", 1199.0)])
        is not None
    )


def test_a_percentage_point_can_be_set_over_http(client, app_module) -> None:
    seed_bars(app_module, [("2026-09-04", 1000.0)])

    created = client.post(
        "/v1/companies/RELIANCE/watch-points",
        json={"percent": -5, "note": "watch out for a sharp fall"},
    )

    assert created.status_code == 200
    body = created.json()
    assert body["direction"] == "PERCENT_DOWN"
    assert body["level"] == 5.0, "the magnitude is stored; the sign is the direction"
    assert body["created_close"] == 1000.0, "the baseline is frozen at creation"


def test_giving_both_a_level_and_a_percent_is_refused(client, app_module) -> None:
    seed_bars(app_module, [("2026-09-04", 1000.0)])

    both = client.post("/v1/companies/RELIANCE/watch-points", json={"level": 1200, "percent": -5})
    neither = client.post("/v1/companies/RELIANCE/watch-points", json={"note": "hm"})

    assert both.status_code == 422
    assert neither.status_code == 422


def test_a_percentage_point_settles_through_the_cycle(client, app_module) -> None:
    from smart_watchlist.core.ingestion import _settle_watch_points

    seed_bars(app_module, [("2026-09-04", 1000.0)])
    client.post("/v1/companies/RELIANCE/watch-points", json={"percent": -5})
    seed_bars(app_module, [("2026-09-08", 940.0)])

    assert _settle_watch_points(app_module._store(), app_module._USER_STORE) == 1
    triggered = client.get("/v1/review").json()["triggered_watch_points"][0]
    assert triggered["direction"] == "PERCENT_DOWN"
    assert triggered["triggered_close"] == 940.0
