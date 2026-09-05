"""Adapter behaviour through its public contract, with a stubbed transport.

The point of these is not that the NSE responds — it is that whatever the NSE does,
the adapter returns evidence and a truthful coverage record, and never raises into the
pipeline. An adapter that failed silently would let blindness read as quiet.
"""

from __future__ import annotations

import json
from datetime import UTC

import httpx

from smart_watchlist.adapters.nse_disclosures import NseDisclosureSource
from smart_watchlist.core.models import CoverageStatus, SourceTier

ROW = {
    "symbol": "TMCV",
    "seq_id": "106770850",
    "an_dt": "05-Sep-2026 01:32:23",
    "sm_name": "Tata Motors Limited",
    "desc": "Press Release",
    "attchmntText": "Tata Motors Limited has informed the Exchange regarding a press release.",
    "attchmntFile": "https://nsearchives.nseindia.com/corporate/example.pdf",
}


def _source_returning(payload: object, status: int = 200) -> NseDisclosureSource:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status, content=json.dumps(payload), headers={"content-type": "application/json"}
        )

    return NseDisclosureSource(transport=httpx.MockTransport(handler))


def test_a_disclosure_becomes_official_tier_evidence() -> None:
    evidence, coverage = _source_returning([ROW]).fetch()

    assert coverage.status is CoverageStatus.OK
    item = evidence[0]
    assert item.tier is SourceTier.OFFICIAL_DISCLOSURE
    assert item.source_ref == "106770850"
    assert item.category == "Press Release"
    assert item.security_symbol == "TMCV"
    assert item.url.startswith("https://")


def test_exchange_local_timestamps_become_aware_utc() -> None:
    evidence, _ = _source_returning([ROW]).fetch()

    published = evidence[0].published_at
    assert published.tzinfo is not None
    # 01:32 IST is the previous evening in UTC — the offset must be applied, not assumed.
    assert published.astimezone(UTC).hour == 20


def test_an_unreadable_row_is_dropped_and_the_gap_is_reported() -> None:
    evidence, coverage = _source_returning([ROW, {**ROW, "symbol": ""}]).fetch()

    assert len(evidence) == 1
    assert coverage.status is CoverageStatus.DEGRADED
    assert "unparseable" in coverage.detail


def test_a_blocked_endpoint_is_reported_as_unavailable_not_raised() -> None:
    evidence, coverage = _source_returning({}, status=403).fetch()

    assert evidence == []
    assert coverage.status is CoverageStatus.UNAVAILABLE


def test_an_unexpected_payload_shape_is_unavailable_not_a_crash() -> None:
    evidence, coverage = _source_returning({"unexpected": "object"}).fetch()

    assert evidence == []
    assert coverage.status is CoverageStatus.UNAVAILABLE
