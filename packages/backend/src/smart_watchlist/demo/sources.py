"""Fixture providers.

These implement the same adapter protocols as `NseDisclosureSource`, `GoogleNewsSource`
and `YFinanceMarketSource`, and are the *only* thing judge mode substitutes. Everything
downstream — normalization, extraction, grounding, linking, corroboration, the engine,
persistence — is the production path, unchanged.

They also return a coverage record on every call, as the real adapters do, because a
source that reported nothing about its own health would let the fixture claim a certainty
the scenario never established.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from ..core.context import context_for
from ..core.market import Bar
from ..core.models import CoverageRecord, CoverageStatus, Evidence, SourceTier
from .scenario import INDEX_MOVES, QUIET_INDEX_MOVE, SCENARIO, SIMULATED_URL

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

__all__ = [
    "FixtureDisclosureSource",
    "FixtureMarketSource",
    "FixtureNewsSource",
]

# Publishers keep their real names so source standing resolves normally (D36). What marks
# the data as simulated is the evidence URL and the mode banner — renaming Reuters to
# "Simulated Reuters" would push every fixture article into UNRECOGNISED and quietly break
# the credibility demonstration the fixture exists to show.


class FixtureMarketSource:
    """Deterministic daily bars. Implements ``MarketSource``."""

    name = "market"

    def __init__(self, now: datetime) -> None:
        self._now = now

    def fetch(self, symbols: Sequence[str]) -> tuple[dict[str, list[Bar]], CoverageRecord]:
        by_symbol = {company.symbol: company for company in SCENARIO}
        bars: dict[str, list[Bar]] = {}
        missing: list[str] = []

        for symbol in symbols:
            if symbol.startswith("^"):
                bars[symbol] = self._index_series(symbol)
                continue
            company = by_symbol.get(symbol)
            if company is None or not company.closes:
                # Absent, not zero. The caller treats absence as missing coverage for that
                # security, which is exactly the state INFY is here to demonstrate.
                missing.append(symbol)
                continue
            bars[symbol] = self._series(company.closes)

        detail = (
            f"{len(bars)} securities retrieved."
            if not missing
            else f"No data for {len(missing)} of {len(symbols)}: {', '.join(sorted(missing))}."
        )
        return bars, CoverageRecord(
            source=self.name,
            status=CoverageStatus.OK if not missing else CoverageStatus.DEGRADED,
            observed_at=self._now,
            detail=detail,
        )

    def _series(self, closes: tuple[float, ...]) -> list[Bar]:
        """One bar per session, oldest first, ending on the most recent session."""
        return [
            Bar(
                on=(self._now - timedelta(days=len(closes) - index)).date(),
                close=close,
                adjusted_close=close,
                volume=1_000_000.0 * (2.4 if index == len(closes) - 1 else 1.0),
                split_ratio=0.0,
                dividend=0.0,
                high=round(close * 1.006, 2),
                low=round(close * 0.994, 2),
            )
            for index, close in enumerate(closes)
        ]

    def _index_series(self, symbol: str) -> list[Bar]:
        """One index. Only the sector that is meant to explain a move actually moves.

        The residual — a company's return minus its sector's — is what decides whether a
        move is company-specific (D14), so which index moves is the whole comparison.
        """
        move = INDEX_MOVES.get(symbol, QUIET_INDEX_MOVE)
        closes = [20_000.0 + index * 4.0 for index in range(130)]
        closes.append(round(closes[-1] * (1 + move / 100), 2))
        return self._series(tuple(closes))


class FixtureDisclosureSource:
    """Exchange filings. Implements ``DisclosureSource``."""

    name = "nse-disclosures"

    def __init__(self, now: datetime) -> None:
        self._now = now

    def fetch(self) -> tuple[list[Evidence], CoverageRecord]:
        evidence: list[Evidence] = []
        for company in SCENARIO:
            context = context_for(company.symbol, company.symbol)
            for index, filing in enumerate(company.disclosures):
                published = self._now - timedelta(minutes=filing.minutes_ago)
                evidence.append(
                    Evidence(
                        source=self.name,
                        source_ref=f"fixture-nse-{company.symbol}-{index}",
                        # An exchange filing, so the tier is what makes it official (D36).
                        tier=SourceTier.OFFICIAL_DISCLOSURE,
                        publisher="NSE",
                        subject_company=context.name,
                        retrieved_at=self._now,
                        published_at=published,
                        title=filing.title,
                        body=filing.title,
                        url=f"{SIMULATED_URL}/nse/{company.symbol}/{index}",
                        security_symbol=company.symbol,
                        category=filing.category,
                    )
                )
        return evidence, CoverageRecord(
            source=self.name,
            status=CoverageStatus.OK,
            observed_at=self._now,
            detail=f"{len(evidence)} disclosures retrieved.",
        )


class FixtureNewsSource:
    """Reporting. Implements ``NewsSource``."""

    name = "news"

    def __init__(self, now: datetime) -> None:
        self._now = now

    def fetch(self, companies: Sequence[tuple[str, str]]) -> tuple[list[Evidence], CoverageRecord]:
        wanted = {symbol for symbol, _ in companies}
        evidence: list[Evidence] = []
        for company in SCENARIO:
            if company.symbol not in wanted:
                continue
            context = context_for(company.symbol, company.symbol)
            for index, article in enumerate(company.articles):
                evidence.append(
                    Evidence(
                        source=self.name,
                        source_ref=f"fixture-news-{company.symbol}-{index}",
                        tier=SourceTier.CREDIBLE_REPORTING,
                        publisher=article.publisher,
                        subject_company=context.name,
                        retrieved_at=self._now,
                        published_at=self._now - timedelta(minutes=article.minutes_ago),
                        title=article.title,
                        body=article.title,
                        url=f"{SIMULATED_URL}/news/{company.symbol}/{index}",
                        security_symbol=company.symbol,
                        category="News",
                    )
                )
        return evidence, CoverageRecord(
            source=self.name,
            status=CoverageStatus.OK,
            observed_at=self._now,
            detail=f"{len(evidence)} articles retrieved.",
        )
