"""Structured extraction via Gemini 2.5 Flash.

Provider isolation, per D5: this and the Claude adapter are the only modules that know a
provider exists. The domain sees an ``Extractor``.

The model proposes; :mod:`smart_watchlist.core.extraction` decides. Schema-constrained
output narrows what the model can return, but the guarantee lives downstream in the
deterministic grounding gate, not in the request — a model can satisfy a schema and
still invent a counterparty, and only checking the source text catches that.

Provenance is distinct from the rule fallback's by construction: the extractor name
carries the provider, model and prompt version, so a stored assessment always says which
one produced it.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

import httpx

from ..core.extraction import ExtractedEvent
from .credentials import load_credential

if TYPE_CHECKING:
    from ..core.models import Evidence

__all__ = ["EXTRACTOR_NAME", "MODEL", "PROMPT_VERSION", "GeminiExtractor"]

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
"""Configurable because the free tier caps requests *per model per day* (20), so an
evaluation run can exhaust the production model's budget. Overriding lets a run complete
against a sibling model — and the extractor name below records which one produced any
given result, so metrics never describe a model other than the one that ran."""
"""Gemini 2.5 Flash was the intended model and is not usable: it still appears in the
model listing but ``generateContent`` returns 404 with "no longer available to new
users", naming this model as the replacement. Recorded here because the substitution was
forced by the provider, not chosen."""
PROMPT_VERSION = "extract-event/v1"
EXTRACTOR_NAME = f"google/{MODEL}/{PROMPT_VERSION}"

_ENDPOINT_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "subject_company": {"type": "string"},
        "event_type": {"type": "string"},
        "description": {"type": "string"},
        "counterparties": {"type": "array", "items": {"type": "string"}},
        "geographies": {"type": "array", "items": {"type": "string"}},
        "products": {"type": "array", "items": {"type": "string"}},
        "industries": {"type": "array", "items": {"type": "string"}},
        "regulator": {"type": "string"},
        "contract_value": {"type": "string"},
        "is_speculative": {"type": "boolean"},
        "concerns_subject": {"type": "boolean"},
        "missing": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "subject_company",
        "event_type",
        "description",
        "is_speculative",
        "concerns_subject",
    ],
}

_INSTRUCTIONS = """You extract structured facts from financial news headlines about Indian
listed companies. You do not interpret, predict, or attribute cause.

Rules, in order of importance:

1. Every value you emit for counterparties, geographies, products, regulator or
   contract_value MUST appear verbatim in the article text. If it is not there, omit the
   field and name it in "missing". Never infer a plausible value. Unknown stays unknown.
2. concerns_subject is false when the company is mentioned only incidentally (the story
   is about someone else), or when the article is about a sector, an index, a market
   summary, a broker rating, a price movement, or a list of stocks to watch.
3. is_speculative is true for rumours, reported talks, unconfirmed plans, analyst
   scenarios, or anything attributed to unnamed sources.
4. description is ONE factual sentence about what happened. Never state why a share price
   moved. Never assert causation.
5. event_type is a short noun phrase such as: Agreements, Acquisition, Contract Win,
   Product Launch, Financial Result Updates, Regulatory Action, Legal, Raising of Funds,
   Divestment, Change in Directors/ Key Managerial Personnel, Credit Rating- Revision,
   Expansion."""


class GeminiExtractor:
    """Implements ``Extractor``. Returns ``None`` on any failure; never raises.

    Failure modes handled identically — unavailable, rate limited, quota exhausted,
    malformed, schema-violating — because to the domain they are the same fact: no
    supported structure was produced, so the reading degrades (D5).
    """

    name = EXTRACTOR_NAME

    def __init__(
        self,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
        model: str | None = None,
    ) -> None:
        self._model = model or MODEL
        self.name = f"google/{self._model}/{PROMPT_VERSION}"
        self._api_key = api_key if api_key is not None else load_credential("GEMINI_API_KEY")
        self._transport = transport
        self._timeout = timeout
        self.last_failure: str | None = None
        """Why the most recent call produced nothing. Never contains the credential."""

    @property
    def is_configured(self) -> bool:
        """Whether a credential is present. Absence is a coverage fact, not an error."""
        return bool(self._api_key)

    def extract(self, evidence: Evidence) -> ExtractedEvent | None:
        self.last_failure = None
        if not self._api_key:
            self.last_failure = "no-credential"
            return None

        payload = {
            "systemInstruction": {"parts": [{"text": _INSTRUCTIONS}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                f"Company under consideration: {evidence.subject_company}\n"
                                f"Publisher: {evidence.publisher}\n"
                                f"Headline: {evidence.title}\n"
                                f"Body: {evidence.body[:4000]}"
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": _RESPONSE_SCHEMA,
                "temperature": 0,
                "maxOutputTokens": 4096,
            },
        }

        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.post(
                    _ENDPOINT_TEMPLATE.format(model=self._model),
                    headers={
                        # The key travels as a header, never in the URL — a query string
                        # ends up in logs and proxy records.
                        "x-goog-api-key": self._api_key,
                        "content-type": "application/json",
                    },
                    json=payload,
                )
                if response.status_code == 429:
                    self.last_failure = "rate-limited-or-quota-exhausted"
                    return None
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPStatusError as exc:
            # Deliberately records the status only. A provider error body can echo the
            # request, and the request carries the credential.
            self.last_failure = f"http-{exc.response.status_code}"
            return None
        except (httpx.HTTPError, ValueError):
            self.last_failure = "transport-or-decode-failure"
            return None

        event = _to_event(body, evidence)
        if event is None:
            # Distinguish a truncated reply from a malformed one. Gemini 3.x spends part
            # of the output budget on reasoning, so an under-sized budget yields JSON cut
            # mid-object — which parses as garbage and looks identical to a bad model.
            self.last_failure = (
                "response-truncated" if _was_truncated(body) else "unusable-response"
            )
        return event


def _to_event(body: object, evidence: Evidence) -> ExtractedEvent | None:
    """Parse the reply. Any deviation from the expected shape yields ``None``."""
    if not isinstance(body, dict):
        return None
    candidates = body.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return None
    first = candidates[0]
    if not isinstance(first, dict):
        return None
    content = first.get("content")
    if not isinstance(content, dict):
        return None
    parts = content.get("parts")
    if not isinstance(parts, list) or not parts:
        return None
    text = next(
        (
            p.get("text", "")
            for p in parts
            if isinstance(p, dict) and isinstance(p.get("text"), str)
        ),
        "",
    )

    raw = _first_json_object(text)
    if raw is None:
        return None

    subject = raw.get("subject_company")
    event_type = raw.get("event_type")
    description = raw.get("description")
    if not all(isinstance(v, str) and v.strip() for v in (subject, event_type, description)):
        return None

    return ExtractedEvent(
        subject_company=str(subject),
        event_type=str(event_type),
        description=str(description),
        occurred_at=evidence.published_at,
        counterparties=_strings(raw.get("counterparties")),
        geographies=_strings(raw.get("geographies")),
        products=_strings(raw.get("products")),
        industries=_strings(raw.get("industries")),
        regulator=_optional(raw.get("regulator")),
        contract_value=_optional(raw.get("contract_value")),
        is_speculative=bool(raw.get("is_speculative", False)),
        concerns_subject=bool(raw.get("concerns_subject", True)),
        missing=_strings(raw.get("missing")),
    )


def _was_truncated(body: object) -> bool:
    if not isinstance(body, dict):
        return False
    candidates = body.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return False
    first = candidates[0]
    return isinstance(first, dict) and first.get("finishReason") == "MAX_TOKENS"


def _first_json_object(text: str) -> dict[str, Any] | None:
    """Take the first complete JSON object, or nothing.

    Schema-constrained output should be bare JSON, but a fence or preamble must degrade
    to a parse rather than a crash.
    """
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


def _optional(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(v.strip() for v in value if isinstance(v, str) and v.strip())
