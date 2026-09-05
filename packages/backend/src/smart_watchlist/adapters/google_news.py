"""News via Google News RSS.

The smallest reliable news source available without a key. Chosen for the MVP because
it aggregates many publishers and names each one in the item's ``<source>`` element,
which is what makes independent-source counting possible at all (D13).

Two things this adapter is careful about:

*Publisher is not subject* (D21). The publisher is whoever ran the story; the subject is
the company whose feed the item came from. They are recorded separately, and company
identity is never inferred from the publisher.

*Retrieval context is not relevance.* An article surfacing in a company's feed is a
candidate, not a confirmed statement about that company. Whether it genuinely concerns
the company is decided downstream by extraction, not here.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING
from urllib.parse import quote_plus

import httpx

from ..core.models import CoverageRecord, CoverageStatus, Evidence, SourceTier

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["SOURCE_NAME", "GoogleNewsSource"]

SOURCE_NAME = "news"

_ENDPOINT = "https://news.google.com/rss/search"
_USER_AGENT = "Mozilla/5.0 (compatible; smart-market-watchlist/0.1)"

_QUOTE_PAGE = re.compile(
    r"\b(share price|stock price|stock analysis|price target|live nse|share price target)\b",
    re.IGNORECASE,
)
"""Aggregators surface broker quote pages alongside news. They carry no event and would
otherwise become evidence for an event that never happened. Filtered here, deliberately
narrow, and counted so the exclusion is visible rather than silent."""


class GoogleNewsSource:
    """Fetches recent articles per company. Implements ``NewsSource``."""

    name = SOURCE_NAME

    def __init__(self, window_days: int = 3, transport: httpx.BaseTransport | None = None) -> None:
        self._window_days = window_days
        self._transport = transport

    def fetch(self, companies: Sequence[tuple[str, str]]) -> tuple[list[Evidence], CoverageRecord]:
        """Articles for ``(symbol, company name)`` pairs.

        Never raises. A provider failure becomes an ``UNAVAILABLE`` coverage record with
        no evidence, so a news outage can never read as a quiet news day.
        """
        observed_at = datetime.now(UTC)
        evidence: list[Evidence] = []
        failed: list[str] = []
        skipped = 0

        with httpx.Client(timeout=20.0, follow_redirects=True, transport=self._transport) as client:
            for symbol, company in companies:
                try:
                    body = self._get(client, company)
                except (httpx.HTTPError, ValueError):
                    failed.append(symbol)
                    continue
                items, dropped = self._parse(body, symbol, company, observed_at)
                evidence.extend(items)
                skipped += dropped

        return evidence, _coverage(observed_at, len(companies), failed, skipped, len(evidence))

    def _get(self, client: httpx.Client, company: str) -> str:
        query = quote_plus(f"{company} when:{self._window_days}d")
        url = f"{_ENDPOINT}?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
        response = client.get(url, headers={"User-Agent": _USER_AGENT})
        response.raise_for_status()
        return response.text

    def _parse(
        self, body: str, symbol: str, company: str, observed_at: datetime
    ) -> tuple[list[Evidence], int]:
        try:
            root = ET.fromstring(body)
        except ET.ParseError:
            return [], 0

        evidence: list[Evidence] = []
        skipped = 0
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            guid = (item.findtext("guid") or link).strip()
            if not title or not guid:
                skipped += 1
                continue
            if _QUOTE_PAGE.search(title):
                skipped += 1  # a broker quote page, not a report of an event
                continue

            published = _parse_rfc822(item.findtext("pubDate"))
            if published is None:
                skipped += 1
                continue

            evidence.append(
                Evidence(
                    source=SOURCE_NAME,
                    source_ref=guid,
                    tier=SourceTier.CREDIBLE_REPORTING,
                    publisher=_publisher(item, title),
                    subject_company=company,
                    retrieved_at=observed_at,
                    published_at=published,
                    title=_strip_publisher_suffix(title),
                    body=(item.findtext("description") or "").strip(),
                    url=link,
                    security_symbol=symbol,
                    category="News",
                )
            )
        return evidence, skipped


def _publisher(item: ET.Element, title: str) -> str:
    """Who ran the story. Never the company it is about (D21)."""
    for candidate in item.iter():
        text = (candidate.text or "").strip()
        if candidate.tag.endswith("source") and text:
            return text
    # Google appends " - Publisher" when the element is absent.
    _, separator, tail = title.rpartition(" - ")
    return tail.strip() if separator and tail.strip() else "unknown"


def _strip_publisher_suffix(title: str) -> str:
    head, separator, tail = title.rpartition(" - ")
    return head.strip() if separator and len(tail) < 40 else title


def _parse_rfc822(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _coverage(
    observed_at: datetime, requested: int, failed: list[str], skipped: int, kept: int
) -> CoverageRecord:
    if failed and len(failed) == requested:
        return CoverageRecord(
            source=SOURCE_NAME,
            status=CoverageStatus.UNAVAILABLE,
            observed_at=observed_at,
            detail=f"News unavailable for all {requested} companies.",
        )
    if failed:
        return CoverageRecord(
            source=SOURCE_NAME,
            status=CoverageStatus.DEGRADED,
            observed_at=observed_at,
            detail=f"News unavailable for {len(failed)} of {requested}: {', '.join(sorted(failed)[:5])}.",
        )
    return CoverageRecord(
        source=SOURCE_NAME,
        status=CoverageStatus.OK,
        observed_at=observed_at,
        detail=f"{kept} articles across {requested} companies ({skipped} non-article items skipped).",
    )
