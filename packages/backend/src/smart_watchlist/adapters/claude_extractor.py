"""Structured extraction via Claude.

Provider isolation, per D5: this is the only module that knows a provider exists. The
domain sees an ``Extractor``, and swapping the provider means writing another adapter,
not touching the engine.

The model proposes; :mod:`smart_watchlist.core.extraction` decides. Nothing here is
trusted — malformed JSON, a missing field, an invented counterparty all resolve the same
way, by producing less rather than producing fiction. The prompt asks for grounding, but
the guarantee comes from the deterministic gate downstream, not from the asking.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

import httpx

from ..core.extraction import ExtractedEvent

if TYPE_CHECKING:
    from ..core.models import Evidence

__all__ = ["EXTRACTOR_NAME", "PROMPT_VERSION", "ClaudeExtractor"]

PROMPT_VERSION = "extract-event/v1"
_MODEL = "claude-sonnet-5"
EXTRACTOR_NAME = f"anthropic/{_MODEL}/{PROMPT_VERSION}"

_ENDPOINT = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "subject_company": {"type": "string"},
        "event_type": {"type": "string"},
        "description": {"type": "string"},
        "counterparties": {"type": "array", "items": {"type": "string"}},
        "geographies": {"type": "array", "items": {"type": "string"}},
        "products": {"type": "array", "items": {"type": "string"}},
        "industries": {"type": "array", "items": {"type": "string"}},
        "regulator": {"type": ["string", "null"]},
        "contract_value": {"type": ["string", "null"]},
        "is_speculative": {"type": "boolean"},
        "concerns_subject": {"type": "boolean"},
        "missing": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["subject_company", "event_type", "description", "concerns_subject"],
}

_INSTRUCTIONS = """You extract structured facts from financial news. You do not interpret,
predict, or attribute cause.

Rules:
- Every value you emit for counterparties, geographies, products, regulator or
  contract_value MUST appear in the article text. If it is not there, omit it and name
  the field in "missing". Never infer a plausible value.
- concerns_subject is false when the company is mentioned only incidentally, or the
  article is about a sector, an index, or a market summary rather than this company.
- is_speculative is true for rumours, reported talks, unconfirmed plans, or anything
  attributed to unnamed sources.
- description is one factual sentence about what happened. Never state why a share price
  moved. Never assert causation.
- event_type is a short noun phrase, e.g. "Agreements", "Acquisition", "Contract Win",
  "Regulatory Action", "Financial Result Updates".

Return only JSON matching the schema."""


class ClaudeExtractor:
    """Implements ``Extractor``. Returns ``None`` on any failure; never raises."""

    name = EXTRACTOR_NAME

    def __init__(
        self,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._transport = transport
        self._timeout = timeout

    @property
    def is_configured(self) -> bool:
        """Whether a credential is present. Absence is a coverage fact, not an error."""
        return bool(self._api_key)

    def extract(self, evidence: Evidence) -> ExtractedEvent | None:
        if not self._api_key:
            return None

        payload = {
            "model": _MODEL,
            "max_tokens": 1024,
            "system": _INSTRUCTIONS,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"Company under consideration: {evidence.subject_company}\n"
                        f"Publisher: {evidence.publisher}\n"
                        f"Headline: {evidence.title}\n"
                        f"Body: {evidence.body[:4000]}\n\n"
                        f"Extract one event as JSON matching: {json.dumps(_SCHEMA)}"
                    ),
                }
            ],
        }
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.post(
                    _ENDPOINT,
                    headers={
                        "x-api-key": self._api_key,
                        "anthropic-version": _API_VERSION,
                        "content-type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
        except (httpx.HTTPError, ValueError):
            return None

        return _to_event(body, evidence)


def _to_event(body: object, evidence: Evidence) -> ExtractedEvent | None:
    """Parse the model's reply. Any deviation from the expected shape yields ``None``."""
    if not isinstance(body, dict):
        return None
    blocks = body.get("content")
    if not isinstance(blocks, list) or not blocks:
        return None
    text = next(
        (b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"), ""
    )
    raw = _first_json_object(text)
    if raw is None:
        return None

    subject = raw.get("subject_company")
    event_type = raw.get("event_type")
    description = raw.get("description")
    if not isinstance(subject, str) or not isinstance(event_type, str):
        return None
    if not isinstance(description, str):
        return None

    return ExtractedEvent(
        subject_company=subject,
        event_type=event_type,
        description=description,
        occurred_at=evidence.published_at,
        counterparties=_strings(raw.get("counterparties")),
        geographies=_strings(raw.get("geographies")),
        products=_strings(raw.get("products")),
        industries=_strings(raw.get("industries")),
        regulator=raw.get("regulator") if isinstance(raw.get("regulator"), str) else None,
        contract_value=(
            raw.get("contract_value") if isinstance(raw.get("contract_value"), str) else None
        ),
        is_speculative=bool(raw.get("is_speculative", False)),
        concerns_subject=bool(raw.get("concerns_subject", True)),
        missing=_strings(raw.get("missing")),
    )


def _first_json_object(text: str) -> dict[str, Any] | None:
    """Models sometimes wrap JSON in prose or a fence. Take the first object, or nothing."""
    start = text.find("{")
    while start != -1:
        depth = 0
        for index in range(start, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(text[start : index + 1])
                    except json.JSONDecodeError:
                        break
                    return parsed if isinstance(parsed, dict) else None
        start = text.find("{", start + 1)
    return None


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(v.strip() for v in value if isinstance(v, str) and v.strip())
