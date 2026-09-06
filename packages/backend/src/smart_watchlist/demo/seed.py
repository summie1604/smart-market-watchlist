"""Seeding judge mode: run the ordinary cycle over fixture sources.

The whole point is that nothing downstream knows. `run_cycle` is the production function,
the extractor is the production rule extractor, the store is the production store, and the
watch point settles through the production evaluator. A judge inspecting any impressive
state finds the same deterministic engine (D42).

Two safety properties matter more than anything else here:

*Judge state cannot land in a live database.* The path is derived, not passed, and the
seeded database carries a marker row. Seeding refuses to touch a database that has no
marker and is not empty.

*Seeding is idempotent.* A marked, populated database is left alone, so a container that
restarts does not accumulate a second copy of the scenario.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from ..adapters.rule_extractor import RuleExtractor
from ..adapters.sqlite_store import SqliteAssessmentStore
from ..adapters.user_store import SqliteUserStore
from ..core.ingestion import IngestionSources, run_cycle
from ..core.watchpoints import direction_for
from .scenario import REVIEW_WINDOW, SCENARIO, WATCH_POINT_AGE
from .sources import FixtureDisclosureSource, FixtureMarketSource, FixtureNewsSource

if TYPE_CHECKING:
    from ..core.userstate import User

__all__ = ["JUDGE_MARKER", "judge_db_path", "reset", "seed", "seeded"]

log = logging.getLogger("smart_watchlist.demo")

JUDGE_MARKER = "judge-fixture"
"""Written into the seeded database so live data can never be mistaken for it, or wiped
as though it were."""

_DEFAULT_JUDGE_DB = "judge.db"


def judge_db_path() -> str:
    """Where judge state lives — always distinct from the live database.

    ``JUDGE_DB`` overrides it; otherwise the live path is used with a ``judge-`` prefix so
    the two cannot collide even if someone sets only ``WATCHLIST_DB``. A deployment that
    pointed both at one file would let a reset destroy real data, so the paths are derived
    rather than trusted.
    """
    explicit = os.environ.get("JUDGE_DB", "").strip()
    if explicit:
        return explicit
    live = Path(os.environ.get("WATCHLIST_DB", "watchlist.db"))
    return str(live.with_name(f"judge-{live.name}") if live.name else _DEFAULT_JUDGE_DB)


def seeded(path: str) -> bool:
    """Whether this database already holds the fixture scenario."""
    import sqlite3

    if not Path(path).exists():
        return False
    with sqlite3.connect(path) as connection:
        try:
            row = connection.execute(
                "SELECT 1 FROM demo_marker WHERE marker = ?", (JUDGE_MARKER,)
            ).fetchone()
        except sqlite3.OperationalError:
            return False
    return row is not None


def _mark(path: str, now: datetime) -> None:
    import sqlite3

    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS demo_marker (marker TEXT PRIMARY KEY, seeded_at TEXT)"
        )
        connection.execute(
            "INSERT OR REPLACE INTO demo_marker (marker, seeded_at) VALUES (?,?)",
            (JUDGE_MARKER, now.isoformat()),
        )


def _refuse_if_live(path: str) -> None:
    """Never write fixtures into a database that holds real records.

    An unmarked file with tables in it is somebody's live state. Failing loudly here is the
    difference between a misconfiguration and a data loss.
    """
    import sqlite3

    if not Path(path).exists() or seeded(path):
        return
    # Rows, not tables. The application constructs its stores at import, so migrations
    # have already created an empty schema by the time seeding runs — refusing on the
    # presence of tables would refuse every fresh judge container.
    with sqlite3.connect(path) as connection:
        rows = 0
        for table in ("assessments", "memberships", "market_bars"):
            try:
                rows += connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            except sqlite3.OperationalError:
                continue
    if rows:
        raise RuntimeError(
            f"{path} holds data and is not a judge fixture database. Refusing to seed it. "
            "Set JUDGE_DB to a separate path."
        )


def seed(path: str | None = None, now: datetime | None = None, force: bool = False) -> str:
    """Create the scenario, through the ordinary ingestion path.

    Idempotent: an already-seeded database is returned untouched unless ``force``. The
    clock is injectable so tests do not depend on the wall clock while the demo still
    looks current.
    """
    target = path or judge_db_path()
    moment = now or datetime.now(UTC)

    if seeded(target) and not force:
        log.info("demo.seed.skipped path=%s reason=already-seeded", target)
        return target
    _refuse_if_live(target)

    store = SqliteAssessmentStore(target)
    users = SqliteUserStore(target)

    # The production cycle, over fixture sources. Nothing below this line is demo-specific:
    # the extractor, engine, linking, corroboration and persistence are all the real ones.
    result = run_cycle(
        IngestionSources(
            market=FixtureMarketSource(moment),
            disclosures=FixtureDisclosureSource(moment),
            news=FixtureNewsSource(moment),
            # Deterministic by choice: judge mode must not depend on a model quota, and the
            # rule extractor is the same fallback production uses when one is exhausted.
            extractor=RuleExtractor(),
            fallback=None,
        ),
        store,
        now=lambda: moment,
        watch_points=users,
    )

    user = users.demo_user()
    _seed_user_state(users, user, moment)

    # Settled after the watch point exists, through the ordinary evaluator — a triggered
    # badge is never written by hand (D37).
    settled = _settle(store, users)

    _mark(target, moment)
    log.info(
        "demo.seeded path=%s assessed=%d families=%s watch_points_triggered=%d",
        target,
        result.assessed,
        result.healthy_families,
        settled,
    )
    return target


def _seed_user_state(users: SqliteUserStore, user: User, now: datetime) -> None:
    """The watchlist, the interests, the watch points and the checkpoint."""
    # Watched from before the last completed review. ``added_at`` is the observation
    # boundary (D7): a membership created after an assessment correctly hides it, so a
    # fixture that added companies last would surface nothing at all.
    watching_since = now - REVIEW_WINDOW - timedelta(days=2)
    for company in SCENARIO:
        users.add_membership(
            user.user_id,
            company.symbol,
            reason="",
            watch_for="",
            tags=company.interests,
            added_at=watching_since,
        )

    for company in SCENARIO:
        if company.watch_margin_pct is None or len(company.closes) < 2:
            continue
        # Set against the close *before* the session that crosses it, so the point is a
        # question about what happened next rather than a fact recorded after the event.
        baseline = company.closes[-2]
        level = round(baseline * (1 + company.watch_margin_pct / 100), 2)
        users.add_watch_point(
            user.user_id,
            company.symbol,
            level,
            direction_for(level, baseline),
            company.watch_note,
            baseline,
            created_at=now - WATCH_POINT_AGE,
        )

    # A completed review far enough back that the whole scenario falls inside the window.
    users.set_checkpoint(user.user_id, now - REVIEW_WINDOW)


def _settle(store: SqliteAssessmentStore, users: SqliteUserStore) -> int:
    from ..core.ingestion import _settle_watch_points

    return _settle_watch_points(store, users)


def reset(path: str | None = None, now: datetime | None = None) -> str:
    """Restore the scenario for the next judge.

    Refuses anything that is not a judge fixture database, so a misconfigured environment
    fails loudly instead of deleting real records.
    """
    target = path or judge_db_path()
    if Path(target).exists() and not seeded(target):
        raise RuntimeError(f"{target} is not a judge fixture database. Refusing to reset it.")

    for suffix in ("", "-wal", "-shm"):
        candidate = Path(f"{target}{suffix}")
        if candidate.exists():
            candidate.unlink()
    log.info("demo.reset path=%s", target)
    return seed(target, now=now, force=True)


def watch_point_age() -> timedelta:
    """Exposed for tests that assert the fixture's ordering rather than its wall clock."""
    return WATCH_POINT_AGE
