"""Publisher and subject are different facts and must stay that way.

They coincide only for exchange filings. The news adapter in step 2 will publish as
Reuters about Tata Motors, and company identity taken from the publisher would attribute
every news event to the wrong entity.
"""

from __future__ import annotations

import json
import locale

import httpx
from support import make_evidence

from smart_watchlist.adapters.nse_disclosures import NseDisclosureSource
from smart_watchlist.core.normalize import to_candidate

ROW = {
    "symbol": "HINDALCO",
    "seq_id": "106770846",
    "an_dt": "05-Sep-2026 01:09:35",
    "sm_name": "Hindalco Industries Limited",
    "desc": "Agreements",
    "attchmntText": "Hindalco Industries Limited has informed the Exchange about an agreement.",
    "attchmntFile": "https://nsearchives.nseindia.com/corporate/example.pdf",
}


def _source() -> NseDisclosureSource:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=json.dumps([ROW]), headers={"content-type": "application/json"}
        )

    return NseDisclosureSource(transport=httpx.MockTransport(handler))


def test_the_exchange_publishes_and_the_company_is_the_subject() -> None:
    evidence, _ = _source().fetch()

    item = evidence[0]
    assert item.publisher == "NSE"
    assert item.subject_company == "Hindalco Industries Limited"
    assert item.publisher != item.subject_company


def test_company_identity_comes_from_the_subject_not_the_publisher() -> None:
    evidence = make_evidence()
    assert evidence.publisher == "NSE"

    candidate = to_candidate(evidence, event_type=evidence.category)

    assert candidate.company_name == evidence.subject_company
    assert candidate.company_name != evidence.publisher


def test_disclosure_dates_parse_under_a_non_english_locale() -> None:
    """``%b`` resolves against LC_TIME; the feed is always English, so the parser must be too."""
    original = locale.setlocale(locale.LC_TIME)
    parsed_under = {}
    try:
        for name in ("C", "fr_FR.UTF-8", "de_DE.UTF-8"):
            try:
                locale.setlocale(locale.LC_TIME, name)
            except locale.Error:
                continue  # locale not generated on this host
            evidence, coverage = _source().fetch()
            parsed_under[name] = (len(evidence), coverage.status)
    finally:
        locale.setlocale(locale.LC_TIME, original)

    assert parsed_under, "no locales available to test against"
    assert all(count == 1 for count, _ in parsed_under.values()), parsed_under
