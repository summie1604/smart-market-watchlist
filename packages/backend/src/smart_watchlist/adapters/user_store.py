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
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from ..core.userstate import IssuedReview, Membership, Session, User

if TYPE_CHECKING:
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
)


class SqliteUserStore:
    """Accounts, sessions, watchlists and checkpoints."""

    def __init__(self, path: Path | str = "watchlist.db") -> None:
        self._path = str(path)
        self._hasher = PasswordHasher()
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.row_factory = sqlite3.Row
        return connection

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

    def add_membership(self, user_id: str, symbol: str) -> Membership:
        """Add a company. Idempotent — re-adding keeps the original observation boundary.

        Keeping ``added_at`` on conflict matters: bumping it would silently discard the
        history the user has already been shown.
        """
        membership = Membership(user_id=user_id, symbol=symbol, added_at=datetime.now(UTC))
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO memberships (user_id, symbol, added_at) VALUES (?,?,?)
                ON CONFLICT(user_id, symbol) DO NOTHING
                """,
                (membership.user_id, membership.symbol, membership.added_at.isoformat()),
            )
            row = connection.execute(
                "SELECT added_at FROM memberships WHERE user_id = ? AND symbol = ?",
                (user_id, symbol),
            ).fetchone()
        return Membership(
            user_id=user_id, symbol=symbol, added_at=datetime.fromisoformat(row["added_at"])
        )

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
        return [
            Membership(
                user_id=r["user_id"],
                symbol=r["symbol"],
                added_at=datetime.fromisoformat(r["added_at"]),
            )
            for r in rows
        ]

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
