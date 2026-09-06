"""Persistence for private user state.

Separate from the assessment store because the data is separate: this file holds what
belongs to one person, and every query is scoped by ``user_id`` at the SQL level rather
than filtered afterwards. Ownership that depends on the caller remembering to check is
ownership that eventually leaks.

Password hashes are produced by argon2 with library defaults. Nothing here implements
cryptography, and no method returns or logs a hash.
"""

from __future__ import annotations

import contextlib
import secrets
import sqlite3
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from ..core.userstate import IssuedReview, Membership, Session, User
from ..core.watchpoints import MAX_NOTE, WatchDirection, WatchPoint

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

__all__ = ["SESSION_LIFETIME", "SqliteUserStore"]

SESSION_LIFETIME = timedelta(days=7)

_MIGRATIONS: tuple[str, ...] = (
    """
    CREATE TABLE users (
        user_id       TEXT PRIMARY KEY,
        email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
        password_hash TEXT NOT NULL,
        created_at    TEXT NOT NULL
    );
    CREATE TABLE sessions (
        session_id TEXT PRIMARY KEY,
        user_id    TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    );
    CREATE INDEX idx_sessions_user ON sessions (user_id);
    CREATE TABLE memberships (
        user_id  TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
        symbol   TEXT NOT NULL,
        added_at TEXT NOT NULL,
        PRIMARY KEY (user_id, symbol)
    );
    CREATE TABLE checkpoints (
        user_id    TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
        checked_at TEXT NOT NULL
    );
    CREATE TABLE issued_reviews (
        review_id           TEXT PRIMARY KEY,
        user_id             TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
        previous_checkpoint TEXT,
        review_cutoff       TEXT NOT NULL,
        issued_at           TEXT NOT NULL
    );
    CREATE INDEX idx_issued_user ON issued_reviews (user_id, issued_at DESC);
    """,
    """
    ALTER TABLE memberships ADD COLUMN reason TEXT NOT NULL DEFAULT '';
    ALTER TABLE memberships ADD COLUMN watch_for TEXT NOT NULL DEFAULT '';
    ALTER TABLE memberships ADD COLUMN tags TEXT NOT NULL DEFAULT '';
    """,
    """
    CREATE TABLE watch_points (
        point_id        TEXT PRIMARY KEY,
        user_id         TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
        symbol          TEXT NOT NULL,
        level           REAL NOT NULL,
        direction       TEXT NOT NULL,
        note            TEXT NOT NULL DEFAULT '',
        created_at      TEXT NOT NULL,
        created_close   REAL,
        triggered_on    TEXT,
        triggered_close REAL,
        acknowledged_at TEXT
    );
    CREATE INDEX idx_watch_points_user ON watch_points (user_id, symbol);
    CREATE INDEX idx_watch_points_open ON watch_points (triggered_on);
    """,
)


class SqliteUserStore:
    """Accounts, sessions, watchlists and checkpoints."""

    def __init__(self, path: Path | str = "watchlist.db") -> None:
        self._path = str(path)
        self._hasher = PasswordHasher()
        self._migrate()

    @contextlib.contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._path)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _migrate(self) -> None:
        with self._connect() as connection:
            # A counter of its own, kept in a table rather than in PRAGMA user_version,
            # because the assessment store owns that pragma on the same database file.
            connection.execute(
                "CREATE TABLE IF NOT EXISTS user_schema_version (version INTEGER NOT NULL)"
            )
            row = connection.execute("SELECT version FROM user_schema_version").fetchone()
            applied = 0 if row is None else int(row["version"])
            for version, statements in enumerate(_MIGRATIONS[applied:], start=applied + 1):
                connection.executescript(statements)
                connection.execute("DELETE FROM user_schema_version")
                connection.execute(
                    "INSERT INTO user_schema_version (version) VALUES (?)", (version,)
                )

    # --- accounts ---------------------------------------------------------

    def create_user(self, email: str, password: str) -> User | None:
        """Register. ``None`` when the email is taken.

        The caller must not distinguish "taken" from any other failure in what it tells
        the client — that would confirm an account exists.
        """
        user = User(
            user_id=uuid.uuid4().hex,
            email=email.strip(),
            created_at=datetime.now(UTC),
        )
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO users (user_id, email, password_hash, created_at) VALUES (?,?,?,?)",
                    (
                        user.user_id,
                        user.email,
                        self._hasher.hash(password),
                        user.created_at.isoformat(),
                    ),
                )
        except sqlite3.IntegrityError:
            return None
        return user

    def verify_credentials(self, email: str, password: str) -> User | None:
        """Check an email and password. ``None`` for any failure, without saying which.

        A missing account still runs a hash verification against a dummy value, so the
        response time does not reveal whether the email exists.
        """
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE email = ? COLLATE NOCASE", (email.strip(),)
            ).fetchone()

        if row is None:
            self._waste_time()
            return None
        try:
            self._hasher.verify(row["password_hash"], password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return None
        return User(
            user_id=row["user_id"],
            email=row["email"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def _waste_time(self) -> None:
        """Verify against a throwaway hash so a missing account costs the same as a wrong
        password. Timing is an oracle if one path is cheap."""
        with contextlib.suppress(Exception):  # the mismatch is the point
            self._hasher.verify(self._hasher.hash("timing-equaliser"), "wrong")

    def demo_user(self, email: str = "demo@example.com") -> User:
        """The persistent account a login-free demo resolves to.

        ``example.com`` is IANA-reserved, so the address is well-formed and belongs to
        nobody. Registering it is refused by the unique constraint — the demo account
        cannot be taken over by claiming its address.

        Server-owned and created on first use, with an unusable password hash rather than
        a known one — nothing should be able to sign in *as* the demo user through the
        normal credential path. Its watchlist and checkpoint are ordinary rows, so
        "since you last checked" is genuinely real rather than simulated.
        """
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE email = ? COLLATE NOCASE", (email,)
            ).fetchone()
            if row is None:
                user = User(user_id=uuid.uuid4().hex, email=email, created_at=datetime.now(UTC))
                connection.execute(
                    "INSERT INTO users (user_id, email, password_hash, created_at) VALUES (?,?,?,?)",
                    (
                        user.user_id,
                        user.email,
                        # Deliberately not a hash of anything: argon2 verification of any
                        # candidate against this fails, so the demo account has no password.
                        "demo-account-has-no-password",
                        user.created_at.isoformat(),
                    ),
                )
                return user
        return User(
            user_id=row["user_id"],
            email=row["email"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    # --- sessions ---------------------------------------------------------

    def create_session(self, user_id: str, now: datetime | None = None) -> Session:
        moment = now or datetime.now(UTC)
        session = Session(
            session_id=secrets.token_urlsafe(32),
            user_id=user_id,
            created_at=moment,
            expires_at=moment + SESSION_LIFETIME,
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO sessions (session_id, user_id, created_at, expires_at) VALUES (?,?,?,?)",
                (
                    session.session_id,
                    session.user_id,
                    session.created_at.isoformat(),
                    session.expires_at.isoformat(),
                ),
            )
        return session

    def user_for_session(self, session_id: str, now: datetime | None = None) -> User | None:
        """Resolve a session to its owner. Expired sessions resolve to nothing."""
        moment = now or datetime.now(UTC)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT u.user_id, u.email, u.created_at, s.expires_at
                FROM sessions s JOIN users u ON u.user_id = s.user_id
                WHERE s.session_id = ?
                """,
                (session_id,),
            ).fetchone()
        if row is None or datetime.fromisoformat(row["expires_at"]) <= moment:
            return None
        return User(
            user_id=row["user_id"],
            email=row["email"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def end_session(self, session_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

    # --- watchlist --------------------------------------------------------

    def add_membership(
        self,
        user_id: str,
        symbol: str,
        reason: str = "",
        watch_for: str = "",
        tags: tuple[str, ...] = (),
        added_at: datetime | None = None,
    ) -> Membership:
        """Add a company, with what the user said they were watching for.

        ``added_at`` is injectable for fixtures, which need a watchlist that predates the
        records it is meant to surface — ``added_at`` is the observation boundary, so a
        membership created after an assessment correctly hides it. Live callers never pass
        it.

        Idempotent — re-adding keeps the original observation boundary. Keeping
        ``added_at`` on conflict matters: bumping it would silently discard the history
        the user has already been shown.

        Interests are written on the way in and updated only when something was supplied.
        Re-adding a company without them must not erase what the user wrote the first
        time, and every field is optional by design: the questions are worth asking and
        never worth blocking on.
        """
        membership = Membership(
            user_id=user_id,
            symbol=symbol,
            added_at=added_at or datetime.now(UTC),
            reason=reason.strip(),
            watch_for=watch_for.strip(),
            tags=tags,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO memberships (user_id, symbol, added_at, reason, watch_for, tags)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(user_id, symbol) DO NOTHING
                """,
                (
                    membership.user_id,
                    membership.symbol,
                    membership.added_at.isoformat(),
                    membership.reason,
                    membership.watch_for,
                    _pack_tags(tags),
                ),
            )
            if membership.reason or membership.watch_for or tags:
                connection.execute(
                    """
                    UPDATE memberships SET reason = ?, watch_for = ?, tags = ?
                    WHERE user_id = ? AND symbol = ?
                    """,
                    (
                        membership.reason,
                        membership.watch_for,
                        _pack_tags(tags),
                        user_id,
                        symbol,
                    ),
                )
            row = connection.execute(
                "SELECT * FROM memberships WHERE user_id = ? AND symbol = ?",
                (user_id, symbol),
            ).fetchone()
        return _to_membership(row)

    def remove_membership(self, user_id: str, symbol: str) -> bool:
        """Remove a company. ``False`` when it was not there — not an error."""
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM memberships WHERE user_id = ? AND symbol = ?", (user_id, symbol)
            )
            return cursor.rowcount > 0

    def memberships(self, user_id: str) -> list[Membership]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM memberships WHERE user_id = ? ORDER BY symbol", (user_id,)
            ).fetchall()
        return [_to_membership(r) for r in rows]

    # --- watch points -----------------------------------------------------

    def add_watch_point(
        self,
        user_id: str,
        symbol: str,
        level: float,
        direction: WatchDirection,
        note: str,
        created_close: float | None,
        created_at: datetime | None = None,
    ) -> WatchPoint:
        """Record a level this reader asked to be told about.

        ``created_at`` is injectable for the same reason every other clock here is: a
        fixture needs to place a point *before* the session that crosses it, because a
        point is a question about what happens next (D37). Live callers never pass it.
        """
        point = WatchPoint(
            point_id=secrets.token_urlsafe(12),
            user_id=user_id,
            symbol=symbol,
            level=level,
            direction=direction,
            note=note.strip()[:MAX_NOTE],
            created_at=created_at or datetime.now(UTC),
            created_close=created_close,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO watch_points
                    (point_id, user_id, symbol, level, direction, note, created_at,
                     created_close)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    point.point_id,
                    point.user_id,
                    point.symbol,
                    point.level,
                    point.direction.value,
                    point.note,
                    point.created_at.isoformat(),
                    point.created_close,
                ),
            )
        return point

    def watch_points(self, user_id: str, symbol: str | None = None) -> list[WatchPoint]:
        """This reader's points, newest first. Scoped in SQL, never filtered afterwards."""
        with self._connect() as connection:
            if symbol is None:
                rows = connection.execute(
                    "SELECT * FROM watch_points WHERE user_id = ? ORDER BY created_at DESC",
                    (user_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM watch_points WHERE user_id = ? AND symbol = ?
                    ORDER BY created_at DESC
                    """,
                    (user_id, symbol),
                ).fetchall()
        return [_to_watch_point(row) for row in rows]

    def open_watch_points(self) -> list[WatchPoint]:
        """Every untriggered point across all readers — what a cycle has to evaluate.

        Bounded by the index on ``triggered_on``: a triggered point is never re-examined,
        so the work per cycle shrinks as points fire rather than growing forever.
        """
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM watch_points WHERE triggered_on IS NULL"
            ).fetchall()
        return [_to_watch_point(row) for row in rows]

    def mark_triggered(self, point_id: str, on: date, close: float) -> bool:
        """Record the session that satisfied a point.

        ``triggered_on IS NULL`` in the WHERE clause is what makes this announce once: a
        second cycle reading the same bars updates nothing, so an unattended schedule can
        run as often as it likes without repeating itself.
        """
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE watch_points SET triggered_on = ?, triggered_close = ?
                WHERE point_id = ? AND triggered_on IS NULL
                """,
                (on.isoformat(), close, point_id),
            )
            return cursor.rowcount > 0

    def acknowledge_watch_point(self, user_id: str, point_id: str) -> bool:
        """Mark a triggered point as seen, so it stops asking."""
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE watch_points SET acknowledged_at = ?
                WHERE point_id = ? AND user_id = ? AND triggered_on IS NOT NULL
                """,
                (datetime.now(UTC).isoformat(), point_id, user_id),
            )
            return cursor.rowcount > 0

    def remove_watch_point(self, user_id: str, point_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM watch_points WHERE point_id = ? AND user_id = ?",
                (point_id, user_id),
            )
            return cursor.rowcount > 0

    # --- checkpoints and issued reviews -----------------------------------

    def checkpoint(self, user_id: str) -> datetime | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT checked_at FROM checkpoints WHERE user_id = ?", (user_id,)
            ).fetchone()
        return None if row is None else datetime.fromisoformat(row["checked_at"])

    def issue_review(
        self, user_id: str, previous: datetime | None, cutoff: datetime
    ) -> IssuedReview:
        """Record the cutoff the server committed to for this review."""
        review = IssuedReview(
            review_id=secrets.token_urlsafe(18),
            user_id=user_id,
            previous_checkpoint=previous,
            review_cutoff=cutoff,
            issued_at=datetime.now(UTC),
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO issued_reviews
                    (review_id, user_id, previous_checkpoint, review_cutoff, issued_at)
                VALUES (?,?,?,?,?)
                """,
                (
                    review.review_id,
                    review.user_id,
                    None if previous is None else previous.isoformat(),
                    cutoff.isoformat(),
                    review.issued_at.isoformat(),
                ),
            )
        return review

    def issued_review(self, review_id: str, user_id: str) -> IssuedReview | None:
        """Look up an issued review, scoped to its owner.

        Scoped in SQL rather than checked afterwards: one user completing another's
        review must be impossible, not merely rejected.
        """
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM issued_reviews WHERE review_id = ? AND user_id = ?",
                (review_id, user_id),
            ).fetchone()
        if row is None:
            return None
        return IssuedReview(
            review_id=row["review_id"],
            user_id=row["user_id"],
            previous_checkpoint=(
                None
                if row["previous_checkpoint"] is None
                else datetime.fromisoformat(row["previous_checkpoint"])
            ),
            review_cutoff=datetime.fromisoformat(row["review_cutoff"]),
            issued_at=datetime.fromisoformat(row["issued_at"]),
        )

    def set_checkpoint(self, user_id: str, moment: datetime) -> None:
        """Write the checkpoint. Monotonicity is decided by the caller, enforced here.

        ``MAX`` in SQL rather than read-then-write, so two devices completing reviews
        concurrently cannot interleave into a regression.
        """
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO checkpoints (user_id, checked_at) VALUES (?,?)
                ON CONFLICT(user_id) DO UPDATE SET
                    checked_at = MAX(checkpoints.checked_at, excluded.checked_at)
                """,
                (user_id, moment.isoformat()),
            )


def _pack_tags(tags: tuple[str, ...]) -> str:
    """Tags as one comma-separated column.

    A join table would be the textbook answer; this is a short, closed vocabulary that is
    always read whole and never queried across users, so a column is the honest size of
    the problem.
    """
    return ",".join(tags)


def _to_membership(row: sqlite3.Row) -> Membership:
    raw = row["tags"] or ""
    return Membership(
        user_id=row["user_id"],
        symbol=row["symbol"],
        added_at=datetime.fromisoformat(row["added_at"]),
        reason=row["reason"] or "",
        watch_for=row["watch_for"] or "",
        tags=tuple(t for t in raw.split(",") if t),
    )


def _to_watch_point(row: sqlite3.Row) -> WatchPoint:
    return WatchPoint(
        point_id=row["point_id"],
        user_id=row["user_id"],
        symbol=row["symbol"],
        level=row["level"],
        direction=WatchDirection(row["direction"]),
        note=row["note"] or "",
        created_at=datetime.fromisoformat(row["created_at"]),
        created_close=row["created_close"],
        triggered_on=(
            None if row["triggered_on"] is None else date.fromisoformat(row["triggered_on"])
        ),
        triggered_close=row["triggered_close"],
        acknowledged_at=(
            None
            if row["acknowledged_at"] is None
            else datetime.fromisoformat(row["acknowledged_at"])
        ),
    )
