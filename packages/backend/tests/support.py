"""Test builders.

Everything here builds evidence, never assessments. A fixture that wrote a verdict
directly would prove nothing about the pipeline it is meant to exercise (DESIGN.md D18).
"""

from __future__ import annotations

from datetime import UTC, datetime

from smart_watchlist.core.models import (
    Coverage,
    CoverageRecord,
    CoverageStatus,
    Event,
    Evidence,
    SourceTier,
)

NOW = datetime(2026, 9, 5, 8, 0, tzinfo=UTC)


def make_evidence(
    *,
    symbol: str = "TATAMOTORS",
    category: str = "Outcome of Board Meeting",
    ref: str = "106770850",
    tier: SourceTier = SourceTier.OFFICIAL_DISCLOSURE,
) -> Evidence:
    return Evidence(
        source="nse-disclosures",
        source_ref=ref,
        tier=tier,
        publisher="NSE",
        subject_company="Tata Motors Limited",
        retrieved_at=NOW,
        published_at=NOW,
        title=f"{symbol} disclosed: {category}",
        body="",
        url="https://nsearchives.nseindia.com/corporate/example.pdf",
        security_symbol=symbol,
        category=category,
    )


def make_event(evidence: Evidence) -> Event:
    return Event(
        event_id=f"evt-{evidence.source_ref}",
        security_symbol=evidence.security_symbol,
        company_name=evidence.subject_company,
        event_type=evidence.category,
        description=evidence.title,
        occurred_at=evidence.published_at,
        evidence=(evidence,),
    )


def coverage(*, market: bool = True, news: bool = True, disclosures: bool = True) -> Coverage:
    """Build a coverage state. Absent families are recorded, never omitted."""

    def record(source: str, present: bool) -> CoverageRecord:
        return CoverageRecord(
            source=source,
            status=CoverageStatus.OK if present else CoverageStatus.NOT_BUILT,
            observed_at=NOW,
            detail="",
        )

    return Coverage(
        records=(
            record("nse-disclosures", disclosures),
            record("market", market),
            record("news", news),
        )
    )
