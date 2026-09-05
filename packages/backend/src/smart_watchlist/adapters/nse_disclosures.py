"""NSE corporate announcements — the authoritative disclosure source.

Exchange filings are the highest evidence tier the system can obtain (VISION.md §12):
the company told the exchange, rather than someone reported that they did.

The endpoint is undocumented and defensive, which is why it was spiked first
(DESIGN.md, Step 0). Nothing here leaks upward: the adapter returns the same
``(evidence, coverage)`` pair whether the fetch succeeded or failed, so an outage
becomes stated missing coverage rather than a silent absence of events.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import httpx

from ..core.models import CoverageRecord, CoverageStatus, Evidence, SourceTier

__all__ = ["SOURCE_NAME", "NseDisclosureSource"]

SOURCE_NAME = "nse-disclosures"

_ENDPOINT = "https://www.nseindia.com/api/corporate-announcements?index=equities"
_REFERER = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

PUBLISHER = "NSE"
"""The exchange publishes the filing; the company is its subject, not its publisher."""

_MONTHS: dict[str, int] = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
"""Month abbreviations, mapped explicitly.

``strptime``'s ``%b`` resolves against ``LC_TIME``, so on a host with a non-English
locale every disclosure would fail to parse and be dropped — silently, and completely.
The feed is always English; the parser should not depend on the process locale.
"""

IST = timezone(timedelta(hours=5, minutes=30))
"""Disclosure timestamps are exchange-local and carry no offset. We attach IST here,
at the boundary, so nothing downstream has to guess what a naive timestamp meant."""


class NseDisclosureSource:
    """Fetches recent corporate announcements from the NSE.

    Implements :class:`smart_watchlist.core.ports.DisclosureSource`.
    """

    name = SOURCE_NAME

    def __init__(self, timeout: float = 20.0, transport: httpx.BaseTransport | None = None) -> None:
        self._timeout = timeout
        self._transport = transport
        """Injectable so the adapter's own error handling can be tested without a network.
        Production passes nothing and gets a real client."""

    def fetch(self) -> tuple[list[Evidence], CoverageRecord]:
        """Retrieve announcements. Never raises — failure is reported as coverage."""
        observed_at = datetime.now(UTC)
        try:
            payload = self._get()
        except (httpx.HTTPError, ValueError) as exc:
            return [], CoverageRecord(
                source=SOURCE_NAME,
                status=CoverageStatus.UNAVAILABLE,
                observed_at=observed_at,
                detail=f"Fetch failed: {type(exc).__name__}",
            )

        evidence, skipped = self._to_evidence(payload, observed_at)
        if skipped:
            return evidence, CoverageRecord(
                source=SOURCE_NAME,
                status=CoverageStatus.DEGRADED,
                observed_at=observed_at,
                detail=f"{skipped} of {len(payload)} announcements were unparseable.",
            )
        return evidence, CoverageRecord(
            source=SOURCE_NAME,
            status=CoverageStatus.OK,
            observed_at=observed_at,
            detail=f"{len(evidence)} announcements retrieved.",
        )

    def _get(self) -> list[dict[str, Any]]:
        headers = {
            "User-Agent": _USER_AGENT,
            "Accept": "application/json",
            "Referer": _REFERER,
        }
        with httpx.Client(
            timeout=self._timeout, follow_redirects=True, transport=self._transport
        ) as client:
            response = client.get(_ENDPOINT, headers=headers)
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("Expected a list of announcements")
        return payload

    def _to_evidence(
        self, payload: list[dict[str, Any]], observed_at: datetime
    ) -> tuple[list[Evidence], int]:
        evidence: list[Evidence] = []
        skipped = 0
        for row in payload:
            item = self._one(row, observed_at)
            if item is None:
                skipped += 1
                continue
            evidence.append(item)
        return evidence, skipped

    def _one(self, row: dict[str, Any], observed_at: datetime) -> Evidence | None:
        """One announcement, or ``None`` when required fields are absent.

        A row we cannot read is dropped and counted, never guessed at — a fabricated
        symbol or timestamp would be a market fact the system invented.
        """
        symbol = (row.get("symbol") or "").strip()
        source_ref = (row.get("seq_id") or "").strip()
        published_at = _parse_ist(row.get("an_dt"))
        if not symbol or not source_ref or published_at is None:
            return None

        title = (row.get("attchmntText") or row.get("desc") or "").strip()
        return Evidence(
            source=SOURCE_NAME,
            source_ref=source_ref,
            tier=SourceTier.OFFICIAL_DISCLOSURE,
            publisher=PUBLISHER,
            subject_company=(row.get("sm_name") or symbol).strip(),
            retrieved_at=observed_at,
            published_at=published_at,
            title=title,
            body=(row.get("attchmntText") or "").strip(),
            url=(row.get("attchmntFile") or "").strip(),
            security_symbol=symbol,
            category=(row.get("desc") or "").strip(),
        )


def _parse_ist(value: object) -> datetime | None:
    """``"05-Sep-2026 01:33:50"`` in exchange-local time, as an aware UTC datetime.

    Parsed without ``%b`` so the result does not depend on the process locale.
    """
    if not isinstance(value, str):
        return None
    parts = value.strip().split()
    if len(parts) != 2:
        return None
    date_part, time_part = parts

    date_fields = date_part.split("-")
    time_fields = time_part.split(":")
    if len(date_fields) != 3 or len(time_fields) != 3:
        return None

    day_text, month_text, year_text = date_fields
    month = _MONTHS.get(month_text.strip().lower()[:3])
    if month is None:
        return None

    try:
        hour, minute, second = (int(f) for f in time_fields)
        naive = datetime(int(year_text), month, int(day_text), hour, minute, second)
    except ValueError:
        return None
    return naive.replace(tzinfo=IST).astimezone(UTC)
