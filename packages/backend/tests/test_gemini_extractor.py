"""Gemini adapter behaviour, driven entirely by stubbed transports.

No credential is used here and no network call is made. Every failure mode resolves the
same way — no supported structure, so the reading degrades (D5) — and none of them may
surface the key.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx

from smart_watchlist.adapters.gemini_extractor import EXTRACTOR_NAME, MODEL, GeminiExtractor
from smart_watchlist.adapters.rule_extractor import EXTRACTOR_NAME as RULE_NAME
from smart_watchlist.core.models import Evidence, SourceTier

NOW = datetime(2026, 9, 5, tzinfo=UTC)
SECRET = "test-key-never-logged"


def evidence(title: str = "Tata Motors agrees Iveco acquisition") -> Evidence:
    return Evidence(
        source="news",
        source_ref="r1",
        tier=SourceTier.CREDIBLE_REPORTING,
        publisher="Reuters",
        subject_company="Tata Motors",
        retrieved_at=NOW,
        published_at=NOW,
        title=title,
        body="",
        url="https://example.invalid",
        security_symbol="TMCV",
        category="News",
    )


def extractor_returning(payload: object, status: int = 200) -> GeminiExtractor:
    def handler(request: httpx.Request) -> httpx.Response:
        if isinstance(payload, str):
            return httpx.Response(status, text=payload)
        return httpx.Response(status, json=payload)

    return GeminiExtractor(api_key=SECRET, transport=httpx.MockTransport(handler))


def reply(obj: dict[str, object]) -> dict[str, object]:
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(obj)}]}}]}


GOOD = {
    "subject_company": "Tata Motors",
    "event_type": "Acquisition",
    "description": "Tata Motors agrees to acquire Iveco.",
    "is_speculative": False,
    "concerns_subject": True,
}


# --- the happy path, so the failure cases mean something ---


def test_a_well_formed_reply_becomes_an_extracted_event() -> None:
    result = extractor_returning(reply(GOOD)).extract(evidence())

    assert result is not None
    assert result.subject_company == "Tata Motors"
    assert result.event_type == "Acquisition"


# --- provider failures ---


def test_quota_exhaustion_is_reported_not_raised() -> None:
    gemini = extractor_returning({"error": {"message": "quota"}}, status=429)

    assert gemini.extract(evidence()) is None
    assert gemini.last_failure == "rate-limited-or-quota-exhausted"


def test_a_server_error_records_only_the_status() -> None:
    """A provider error body can echo the request, and the request carries the key."""
    gemini = extractor_returning({"error": {"message": "boom"}}, status=500)

    assert gemini.extract(evidence()) is None
    assert gemini.last_failure == "http-500"
    assert SECRET not in (gemini.last_failure or "")


def test_a_transport_failure_degrades() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    gemini = GeminiExtractor(api_key=SECRET, transport=httpx.MockTransport(handler))

    assert gemini.extract(evidence()) is None
    assert gemini.last_failure == "transport-failure"


def test_a_non_json_provider_response_is_a_decode_failure() -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, text="not-json"))
    gemini = GeminiExtractor(api_key=SECRET, transport=transport)

    assert gemini.extract(evidence()) is None
    assert gemini.last_failure == "response-decode-failure"


def test_a_missing_credential_is_a_fact_not_an_error() -> None:
    gemini = GeminiExtractor(api_key="")

    assert not gemini.is_configured
    assert gemini.extract(evidence()) is None
    assert gemini.last_failure == "no-credential"


# --- malformed and partial output ---


def test_non_json_text_yields_nothing() -> None:
    gemini = extractor_returning({"candidates": [{"content": {"parts": [{"text": "sorry"}]}}]})

    assert gemini.extract(evidence()) is None
    assert gemini.last_failure == "unusable-response"


def test_a_reply_missing_required_fields_yields_nothing() -> None:
    assert (
        extractor_returning(reply({"subject_company": "Tata Motors"})).extract(evidence()) is None
    )


def test_an_empty_candidate_list_yields_nothing() -> None:
    assert extractor_returning({"candidates": []}).extract(evidence()) is None


def test_json_wrapped_in_prose_is_still_parsed() -> None:
    """Schema-constrained output should be bare, but a fence must degrade to a parse."""
    text = f"Here you go:\n```json\n{json.dumps(GOOD)}\n```"
    gemini = extractor_returning({"candidates": [{"content": {"parts": [{"text": text}]}}]})

    assert gemini.extract(evidence()) is not None


def test_a_valid_but_partial_extraction_stays_usable() -> None:
    """Incomplete is not invalid. What the source supports is kept."""
    partial = {**GOOD, "missing": ["counterparties", "contract_value"]}
    result = extractor_returning(reply(partial)).extract(evidence())

    assert result is not None
    assert result.counterparties == ()
    assert "counterparties" in result.missing


# --- provenance ---


def test_gemini_and_the_rule_extractor_have_distinct_provenance() -> None:
    """A stored assessment must always say which extractor produced it."""
    assert EXTRACTOR_NAME != RULE_NAME
    assert MODEL in EXTRACTOR_NAME
    assert EXTRACTOR_NAME.startswith("google/")
    assert RULE_NAME.startswith("rules/")


def test_the_credential_never_appears_in_the_request_url() -> None:
    """A key in a query string ends up in logs and proxy records."""
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["has_header"] = "yes" if request.headers.get("x-goog-api-key") else "no"
        return httpx.Response(200, json=reply(GOOD))

    GeminiExtractor(api_key=SECRET, transport=httpx.MockTransport(handler)).extract(evidence())

    assert SECRET not in seen["url"]
    assert seen["has_header"] == "yes"


def test_a_truncated_reply_is_reported_as_truncation_not_malformation() -> None:
    """Gemini 3.x spends output budget on reasoning; an under-sized budget cuts the JSON.

    Truncation and malformation both yield no event, but they need different fixes, so
    they must not collapse into one opaque failure string.
    """
    cut = json.dumps(GOOD)[: len(json.dumps(GOOD)) // 2]
    gemini = extractor_returning(
        {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": cut}]}}]}
    )

    assert gemini.extract(evidence()) is None
    assert gemini.last_failure == "response-truncated"


def test_a_complete_but_unparseable_reply_stays_unusable() -> None:
    gemini = extractor_returning(
        {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "{{{"}]}}]}
    )

    assert gemini.extract(evidence()) is None
    assert gemini.last_failure == "unusable-response"


def test_sentinel_strings_become_absence_not_values() -> None:
    """A model that means "nothing" sometimes says "null". That is not a value.

    Observed live: `contract_value` came back as the literal string "null". Grounding
    dropped it, but only because the word was absent from that source — "unknown" and
    "none" do appear in real articles, so the guarantee cannot rest on that accident.
    """
    noisy = {
        **GOOD,
        "contract_value": "null",
        "regulator": "N/A",
        "counterparties": ["Iveco", "unknown", "  "],
    }
    result = extractor_returning(reply(noisy)).extract(evidence())

    assert result is not None
    assert result.contract_value is None
    assert result.regulator is None
    assert result.counterparties == ("Iveco",), "real values survive; sentinels do not"


def test_a_real_value_that_merely_contains_a_sentinel_word_survives() -> None:
    """The filter matches whole values, not substrings — "Unknown Fields Ltd" is a name."""
    result = extractor_returning(
        extractor_payload := reply({**GOOD, "counterparties": ["Unknown Fields Ltd"]})
    ).extract(evidence())
    assert extractor_payload

    assert result is not None
    assert result.counterparties == ("Unknown Fields Ltd",)
