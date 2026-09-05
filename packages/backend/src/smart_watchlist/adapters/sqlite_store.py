"""SQLite persistence for shared intelligence.

SQLite is the MVP datastore, behind a repository boundary so domain logic does not
depend on it (DESIGN.md D10). The migration trigger is stated there and is about
concurrent writers, not seriousness.

Writes are idempotent on ``event_id``: re-ingesting the same disclosure replaces one
assessment rather than accumulating duplicates. Each save is a single transaction, so a
verdict is never half-visible with some of its reason codes missing.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import TYPE_CHECKING

from ..core.models import (
    Assessment,
    Attention,
    Confidence,
    Coverage,
    CoverageRecord,
    CoverageStatus,
    Event,
    Evidence,
    IngestRun,
    ReasonCode,
    SourceTier,
)

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["SqliteAssessmentStore"]

_MIGRATIONS: tuple[str, ...] = (
    """
    CREATE TABLE assessments (
        event_id         TEXT PRIMARY KEY,
        security_symbol  TEXT NOT NULL,
        company_name     TEXT NOT NULL,
        event_type       TEXT NOT NULL,
        description      TEXT NOT NULL,
        occurred_at      TEXT NOT NULL,
        attention        TEXT NOT NULL,
        confidence       TEXT NOT NULL,
        score            INTEGER NOT NULL,
        scoring_version  TEXT NOT NULL,
        assessed_at      TEXT NOT NULL,
        reasons          TEXT NOT NULL,
        coverage         TEXT NOT NULL,
        evidence         TEXT NOT NULL
    );
    CREATE INDEX idx_assessments_occurred ON assessments (occurred_at DESC);
    """,
    """
    CREATE TABLE ingest_runs (
        run_id         TEXT PRIMARY KEY,
        source         TEXT NOT NULL,
        started_at     TEXT NOT NULL,
        assessed_count INTEGER NOT NULL,
        coverage       TEXT NOT NULL
    );
    CREATE INDEX idx_runs_source_started ON ingest_runs (source, started_at DESC);
    """,
)


class SqliteAssessmentStore:
    """Implements :class:`smart_watchlist.core.ports.AssessmentStore`."""

    def __init__(self, path: Path | str = "watchlist.db") -> None:
        self._path = str(path)
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _migrate(self) -> None:
        """Apply pending migrations. Versioned, never recreated by hand."""
        with self._connect() as connection:
            applied = connection.execute("PRAGMA user_version").fetchone()[0]
            for version, statements in enumerate(_MIGRATIONS[applied:], start=applied + 1):
                connection.executescript(statements)
                connection.execute(f"PRAGMA user_version = {version}")

    def save(self, assessment: Assessment) -> None:
        """Persist one verdict, replacing any earlier one for the same event."""
        event = assessment.event
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO assessments (
                    event_id, security_symbol, company_name, event_type, description,
                    occurred_at, attention, confidence, score, scoring_version,
                    assessed_at, reasons, coverage, evidence
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(event_id) DO UPDATE SET
                    attention=excluded.attention,
                    confidence=excluded.confidence,
                    score=excluded.score,
                    scoring_version=excluded.scoring_version,
                    assessed_at=excluded.assessed_at,
                    reasons=excluded.reasons,
                    coverage=excluded.coverage,
                    evidence=excluded.evidence
                """,
                (
                    event.event_id,
                    event.security_symbol,
                    event.company_name,
                    event.event_type,
                    event.description,
                    event.occurred_at.isoformat(),
                    assessment.attention.value,
                    assessment.confidence.value,
                    assessment.score,
                    assessment.scoring_version,
                    assessment.assessed_at.isoformat(),
                    json.dumps([_reason_row(r) for r in assessment.reasons]),
                    json.dumps([_coverage_row(c) for c in assessment.coverage.records]),
                    json.dumps([_evidence_row(e) for e in event.evidence]),
                ),
            )

    def save_run(self, run: IngestRun) -> None:
        """Record one pass of the pipeline, whether or not it assessed anything."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ingest_runs (run_id, source, started_at, assessed_count, coverage)
                VALUES (?,?,?,?,?)
                ON CONFLICT(run_id) DO UPDATE SET
                    assessed_count=excluded.assessed_count,
                    coverage=excluded.coverage
                """,
                (
                    run.run_id,
                    run.source,
                    run.started_at.isoformat(),
                    run.assessed_count,
                    json.dumps([_coverage_row(c) for c in run.coverage.records]),
                ),
            )

    def latest_run(self, source: str) -> IngestRun | None:
        """Current source health is the most recent run, not the newest assessment."""
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM ingest_runs WHERE source = ? ORDER BY started_at DESC LIMIT 1",
                (source,),
            ).fetchone()
        return None if row is None else _to_run(row)

    def recent(self, limit: int = 50) -> list[Assessment]:
        """Most recently disclosed first."""
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM assessments ORDER BY occurred_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_to_assessment(row) for row in rows]


def _reason_row(reason: ReasonCode) -> dict[str, object]:
    return {"code": reason.code, "contribution": reason.contribution, "detail": reason.detail}


def _coverage_row(record: CoverageRecord) -> dict[str, object]:
    return {
        "source": record.source,
        "status": record.status.value,
        "observed_at": record.observed_at.isoformat(),
        "detail": record.detail,
    }


def _evidence_row(evidence: Evidence) -> dict[str, object]:
    return {
        "source": evidence.source,
        "source_ref": evidence.source_ref,
        "tier": evidence.tier.name,
        "publisher": evidence.publisher,
        "subject_company": evidence.subject_company,
        "retrieved_at": evidence.retrieved_at.isoformat(),
        "published_at": evidence.published_at.isoformat(),
        "title": evidence.title,
        "body": evidence.body,
        "url": evidence.url,
        "security_symbol": evidence.security_symbol,
        "category": evidence.category,
    }


def _to_coverage(raw: str) -> Coverage:
    return Coverage(
        records=tuple(
            CoverageRecord(
                source=c["source"],
                status=CoverageStatus(c["status"]),
                observed_at=datetime.fromisoformat(c["observed_at"]),
                detail=c["detail"],
            )
            for c in json.loads(raw)
        )
    )


def _to_run(row: sqlite3.Row) -> IngestRun:
    return IngestRun(
        run_id=row["run_id"],
        source=row["source"],
        started_at=datetime.fromisoformat(row["started_at"]),
        coverage=_to_coverage(row["coverage"]),
        assessed_count=row["assessed_count"],
    )


def _to_assessment(row: sqlite3.Row) -> Assessment:
    evidence = tuple(
        Evidence(
            source=e["source"],
            source_ref=e["source_ref"],
            tier=SourceTier[e["tier"]],
            publisher=e["publisher"],
            subject_company=e["subject_company"],
            retrieved_at=datetime.fromisoformat(e["retrieved_at"]),
            published_at=datetime.fromisoformat(e["published_at"]),
            title=e["title"],
            body=e["body"],
            url=e["url"],
            security_symbol=e["security_symbol"],
            category=e["category"],
        )
        for e in json.loads(row["evidence"])
    )
    event = Event(
        event_id=row["event_id"],
        security_symbol=row["security_symbol"],
        company_name=row["company_name"],
        event_type=row["event_type"],
        description=row["description"],
        occurred_at=datetime.fromisoformat(row["occurred_at"]),
        evidence=evidence,
    )
    return Assessment(
        event=event,
        attention=Attention(row["attention"]),
        confidence=Confidence(row["confidence"]),
        reasons=tuple(
            ReasonCode(code=r["code"], contribution=r["contribution"], detail=r["detail"])
            for r in json.loads(row["reasons"])
        ),
        coverage=_to_coverage(row["coverage"]),
        scoring_version=row["scoring_version"],
        assessed_at=datetime.fromisoformat(row["assessed_at"]),
        score=row["score"],
    )
