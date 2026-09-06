"""Reproducible extraction evaluation isolated from the assessment store.

The harness asks extractors for proposals, applies the same deterministic grounding gate
as production, and measures the result against human-authored case expectations. It does
not link, score, rank, persist assessments, or write any product-facing state (D31).
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import TYPE_CHECKING, Protocol
from uuid import uuid4

from ..core.contradiction import judge_dispute, propose_dispute
from ..core.extraction import Extraction, validate
from ..core.models import ContradictionState, Event, Evidence, SourceTier

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from pathlib import Path

    from ..core.extraction import ExtractedEvent
    from ..core.ports import Extractor

__all__ = ["FallbackChain", "HarnessCase", "HarnessReport", "ProviderRates", "run_harness"]

EXPECTATION_VERSION = "articles/2026-09-05"
SCHEMA_VERSION = "extracted-event/v1"


class ArticleExpectation(Protocol):
    label: str
    publisher: str
    symbol: str
    company: str
    title: str
    body: str
    should_classify: bool
    concerns_subject: bool
    must_not_invent: tuple[str, ...]


@dataclass(frozen=True)
class HarnessCase:
    evidence: Evidence
    should_classify: bool
    concerns_subject: bool
    must_not_invent: tuple[str, ...] = ()

    @classmethod
    def from_expectation(cls, article: ArticleExpectation) -> HarnessCase:
        captured = datetime(2026, 9, 5, tzinfo=UTC)
        return cls(
            evidence=Evidence(
                source="news",
                source_ref=article.label,
                tier=SourceTier.CREDIBLE_REPORTING,
                publisher=article.publisher,
                subject_company=article.company,
                retrieved_at=captured,
                published_at=captured,
                title=article.title,
                body=article.body,
                url=f"fixture://{article.label}",
                security_symbol=article.symbol,
                category="News",
            ),
            should_classify=article.should_classify,
            concerns_subject=article.concerns_subject,
            must_not_invent=article.must_not_invent,
        )


@dataclass(frozen=True)
class ProviderRates:
    input_usd_per_million: float = 0.0
    output_usd_per_million: float = 0.0


class FallbackChain:
    """A separately named production-like path; never blended with its primary model."""

    def __init__(self, primary: Extractor, fallback: Extractor) -> None:
        self.primary = primary
        self.fallback = fallback
        self.name = f"pipeline:{primary.name}+{fallback.name}"
        self.fallback_used = False

    def extract(self, evidence: Evidence) -> ExtractedEvent | None:
        self.fallback_used = False
        result = self.primary.extract(evidence)
        if result is not None:
            return result
        self.fallback_used = True
        return self.fallback.extract(evidence)

    @property
    def last_failure(self) -> str | None:
        target = self.fallback if self.fallback_used else self.primary
        failure = getattr(target, "last_failure", None) or getattr(target, "last_rejection", None)
        return failure if isinstance(failure, str) else None

    def __getattr__(self, name: str) -> object:
        return getattr(self.primary, name)


@dataclass(frozen=True)
class Trial:
    evidence_ref: str
    outcome: str
    proposal_produced: bool
    accepted: bool
    refusal: str
    fallback_used: bool
    dropped_fields: tuple[str, ...]
    subject_failure: bool
    schema_failure: bool
    unsupported_value_count: int
    latency_ms: float
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost_usd: float | None
    raw_output: str
    validated_extraction: str


@dataclass(frozen=True)
class ProviderReport:
    provider: str
    model: str
    prompt_version: str
    cases: int
    true_positive: int
    true_negative: int
    false_positive: int
    false_negative: int
    unusable: int
    fallback_uses: int
    grounding_rejections: int
    subject_failures: int
    schema_failures: int
    unsupported_field_rate: float | None
    precision: float | None
    recall: float | None
    latency_p50_ms: float
    latency_p95_ms: float
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost_usd: float | None


@dataclass(frozen=True)
class HarnessReport:
    run_id: str
    expectation_version: str
    started_at: str
    providers: tuple[ProviderReport, ...]
    contradiction_cases: int
    contradiction_passed: int

    def markdown(self) -> str:
        lines = [
            "# LLM extraction harness",
            "",
            f"Run `{self.run_id}` · expectation set `{self.expectation_version}` · {self.started_at}",
            "",
            "This is fixture performance, not live-ingestion performance. Every provider ran the same cases; results are never blended.",
            "",
            "| Provider / model | Cases | Precision | Recall | Unsupported-field rate | Subject failures | Schema failures | Unusable | Fallbacks | Grounding drops | p50 / p95 | Tokens in / out | Estimated cost |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for item in self.providers:
            precision = "n/a" if item.precision is None else f"{item.precision:.1%}"
            recall = "n/a" if item.recall is None else f"{item.recall:.1%}"
            unsupported = (
                "n/a"
                if item.unsupported_field_rate is None
                else f"{item.unsupported_field_rate:.1%}"
            )
            cost = (
                "not priced"
                if item.estimated_cost_usd is None
                else f"${item.estimated_cost_usd:.6f}"
            )
            tokens = (
                "not reported"
                if item.input_tokens is None or item.output_tokens is None
                else f"{item.input_tokens} / {item.output_tokens}"
            )
            lines.append(
                f"| {item.provider} / {item.model} | {item.cases} | {precision} | {recall} | {unsupported} | {item.subject_failures} | {item.schema_failures} | {item.unusable} | {item.fallback_uses} | {item.grounding_rejections} | {item.latency_p50_ms:.1f} / {item.latency_p95_ms:.1f} ms | {tokens} | {cost} |"
            )
        lines.extend(
            [
                "",
                f"Contradiction gates: **{self.contradiction_passed}/{self.contradiction_cases} cases passed**. These cases test the deterministic decision after a proposal; they are deliberately not credited to any model.",
                "",
                "Raw provider output and per-case grounded results are retained only in the harness database. The harness never writes to the assessment store.",
            ]
        )
        return "\n".join(lines) + "\n"


def run_harness(
    cases: Sequence[HarnessCase],
    extractors: Sequence[Extractor],
    database: Path,
    rates: dict[str, ProviderRates] | None = None,
) -> HarnessReport:
    """Run every configured extractor over the same immutable expectation set."""
    run_id = str(uuid4())
    started = datetime.now(UTC)
    reports: list[ProviderReport] = []
    contradiction_checks = _contradiction_checks()
    with _database(database) as connection:
        connection.execute(
            "INSERT INTO harness_runs(run_id, started_at, expectation_version) VALUES (?, ?, ?)",
            (run_id, started.isoformat(), EXPECTATION_VERSION),
        )
        for extractor in extractors:
            provider, model, prompt = _identity(extractor.name)
            rate_name = (
                extractor.primary.name if isinstance(extractor, FallbackChain) else extractor.name
            )
            provider_rates = (rates or {}).get(rate_name, ProviderRates())
            trials = [_trial(case, extractor, provider_rates) for case in cases]
            for trial in trials:
                connection.execute(
                    """INSERT INTO harness_trials(
                        run_id, provider, model, prompt_version, schema_version,
                        expectation_version, evidence_ref, outcome, proposal_produced,
                        accepted, refusal,
                        dropped_fields, fallback_used, subject_failure, schema_failure,
                        unsupported_value_count, latency_ms,
                        input_tokens, output_tokens, estimated_cost_usd, raw_output,
                        validated_extraction
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        run_id,
                        provider,
                        model,
                        prompt,
                        SCHEMA_VERSION,
                        EXPECTATION_VERSION,
                        trial.evidence_ref,
                        trial.outcome,
                        trial.proposal_produced,
                        trial.accepted,
                        trial.refusal,
                        json.dumps(trial.dropped_fields),
                        trial.fallback_used,
                        trial.subject_failure,
                        trial.schema_failure,
                        trial.unsupported_value_count,
                        trial.latency_ms,
                        trial.input_tokens,
                        trial.output_tokens,
                        trial.estimated_cost_usd,
                        trial.raw_output,
                        trial.validated_extraction,
                    ),
                )
            reports.append(_summarise(extractor.name, trials))
        for name, passed, detail in contradiction_checks:
            connection.execute(
                "INSERT INTO harness_checks(run_id, name, passed, detail) VALUES (?, ?, ?, ?)",
                (run_id, name, passed, detail),
            )
        connection.commit()
    return HarnessReport(
        run_id=run_id,
        expectation_version=EXPECTATION_VERSION,
        started_at=started.isoformat(),
        providers=tuple(reports),
        contradiction_cases=len(contradiction_checks),
        contradiction_passed=sum(passed for _name, passed, _detail in contradiction_checks),
    )


def _trial(case: HarnessCase, extractor: Extractor, rates: ProviderRates) -> Trial:
    started = perf_counter()
    proposal = extractor.extract(case.evidence)
    latency = (perf_counter() - started) * 1000
    extraction: Extraction | None = None
    refusal = _failure(extractor)
    if proposal is not None:
        extraction, validation_refusal = validate(proposal, case.evidence, extractor.name)
        refusal = validation_refusal or ""

    expected = case.should_classify and case.concerns_subject
    accepted = extraction is not None
    outcome = (
        "true-positive"
        if expected and accepted
        else "true-negative"
        if not expected and not accepted
        else "false-positive"
        if accepted
        else "false-negative"
    )
    unsupported = _unsupported_values(proposal, case.must_not_invent)
    schema_failure = refusal in {
        "response-truncated",
        "response-decode-failure",
        "unusable-response",
    }
    input_tokens = _integer_attr(extractor, "last_input_tokens")
    output_tokens = _integer_attr(extractor, "last_output_tokens")
    cost = _cost(input_tokens, output_tokens, rates)
    return Trial(
        evidence_ref=case.evidence.source_ref,
        outcome=outcome,
        proposal_produced=proposal is not None,
        accepted=accepted,
        refusal=refusal,
        fallback_used=bool(getattr(extractor, "fallback_used", False)),
        dropped_fields=() if extraction is None else extraction.dropped,
        subject_failure=(not case.concerns_subject and accepted)
        or refusal == "not-about-subject"
        or "subject" in refusal,
        schema_failure=schema_failure,
        unsupported_value_count=unsupported,
        latency_ms=latency,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=cost,
        raw_output=_string_attr(extractor, "last_raw_output"),
        validated_extraction=_serialise_extraction(extraction),
    )


def _summarise(name: str, trials: list[Trial]) -> ProviderReport:
    provider, model, prompt = _identity(name)
    counts = {
        outcome: sum(t.outcome == outcome for t in trials)
        for outcome in ("true-positive", "true-negative", "false-positive", "false-negative")
    }
    tp, fp, fn = counts["true-positive"], counts["false-positive"], counts["false-negative"]
    latencies = sorted(t.latency_ms for t in trials)
    inputs = [t.input_tokens for t in trials if t.input_tokens is not None]
    outputs = [t.output_tokens for t in trials if t.output_tokens is not None]
    costs = [t.estimated_cost_usd for t in trials if t.estimated_cost_usd is not None]
    proposals = sum(t.proposal_produced for t in trials)
    return ProviderReport(
        provider=provider,
        model=model,
        prompt_version=prompt,
        cases=len(trials),
        true_positive=tp,
        true_negative=counts["true-negative"],
        false_positive=fp,
        false_negative=fn,
        unusable=sum(not t.accepted for t in trials),
        fallback_uses=sum(t.fallback_used for t in trials),
        grounding_rejections=sum(len(t.dropped_fields) for t in trials),
        subject_failures=sum(t.subject_failure for t in trials),
        schema_failures=sum(t.schema_failure for t in trials),
        unsupported_field_rate=(
            sum(t.unsupported_value_count > 0 for t in trials) / proposals if proposals else None
        ),
        precision=tp / (tp + fp) if tp + fp else None,
        recall=tp / (tp + fn) if tp + fn else None,
        latency_p50_ms=_percentile(latencies, 0.50),
        latency_p95_ms=_percentile(latencies, 0.95),
        input_tokens=sum(inputs) if len(inputs) == len(trials) else None,
        output_tokens=sum(outputs) if len(outputs) == len(trials) else None,
        estimated_cost_usd=sum(costs) if len(costs) == len(trials) else None,
    )


@contextmanager
def _database(path: Path) -> Iterator[sqlite3.Connection]:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS harness_runs (
            run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, expectation_version TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS harness_trials (
            id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
            provider TEXT NOT NULL, model TEXT NOT NULL, prompt_version TEXT NOT NULL,
            schema_version TEXT NOT NULL, expectation_version TEXT NOT NULL,
            evidence_ref TEXT NOT NULL, outcome TEXT NOT NULL,
            proposal_produced INTEGER NOT NULL DEFAULT 0, accepted INTEGER NOT NULL,
            refusal TEXT NOT NULL, dropped_fields TEXT NOT NULL, fallback_used INTEGER NOT NULL,
            subject_failure INTEGER NOT NULL, schema_failure INTEGER NOT NULL DEFAULT 0,
            unsupported_value_count INTEGER NOT NULL, latency_ms REAL NOT NULL,
            input_tokens INTEGER, output_tokens INTEGER, estimated_cost_usd REAL,
            raw_output TEXT NOT NULL, validated_extraction TEXT NOT NULL,
            UNIQUE(run_id, provider, model, evidence_ref)
        );
        CREATE TABLE IF NOT EXISTS harness_checks (
            run_id TEXT NOT NULL, name TEXT NOT NULL, passed INTEGER NOT NULL,
            detail TEXT NOT NULL, PRIMARY KEY (run_id, name)
        );
        """
    )
    columns = {row[1] for row in connection.execute("PRAGMA table_info(harness_trials)")}
    if "schema_failure" not in columns:
        connection.execute(
            "ALTER TABLE harness_trials ADD COLUMN schema_failure INTEGER NOT NULL DEFAULT 0"
        )
    if "proposal_produced" not in columns:
        connection.execute(
            "ALTER TABLE harness_trials ADD COLUMN proposal_produced INTEGER NOT NULL DEFAULT 0"
        )
    try:
        yield connection
    finally:
        connection.close()


def _identity(name: str) -> tuple[str, str, str]:
    parts = name.split("/", 2)
    if len(parts) == 3:
        return parts[0], parts[1], parts[2]
    if len(parts) == 2:
        return parts[0], parts[1], "not-applicable"
    return name, "not-applicable", "not-applicable"


def _serialise_extraction(extraction: Extraction | None) -> str:
    if extraction is None:
        return ""
    payload = asdict(extraction.event)
    occurred = payload.get("occurred_at")
    if isinstance(occurred, datetime):
        payload["occurred_at"] = occurred.isoformat()
    payload["dropped"] = list(extraction.dropped)
    return json.dumps(payload, sort_keys=True)


def _unsupported_values(proposal: ExtractedEvent | None, forbidden: tuple[str, ...]) -> int:
    if proposal is None:
        return 0
    emitted = json.dumps(asdict(proposal), default=str, sort_keys=True).lower()
    return sum(value.lower() in emitted for value in forbidden)


def _cost(
    input_tokens: int | None, output_tokens: int | None, rates: ProviderRates
) -> float | None:
    if input_tokens is None or output_tokens is None:
        return None
    return (
        input_tokens * rates.input_usd_per_million + output_tokens * rates.output_usd_per_million
    ) / 1_000_000


def _failure(extractor: Extractor) -> str:
    return _string_attr(extractor, "last_failure") or _string_attr(extractor, "last_rejection")


def _string_attr(value: object, name: str) -> str:
    found = getattr(value, name, "")
    return found if isinstance(found, str) else ""


def _integer_attr(value: object, name: str) -> int | None:
    found = getattr(value, name, None)
    return found if isinstance(found, int) else None


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    return values[min(len(values) - 1, round((len(values) - 1) * fraction))]


def _contradiction_checks() -> list[tuple[str, bool, str]]:
    earlier = _dispute_event(
        "earlier", "RELIANCE", SourceTier.CREDIBLE_REPORTING, 0, "Reliance signs agreement"
    )
    later = _dispute_event(
        "later",
        "RELIANCE",
        SourceTier.CREDIBLE_REPORTING,
        1,
        "Reliance denies it signed the agreement",
    )
    proposal = propose_dispute(later.evidence)
    accepted = judge_dispute(earlier, later, proposal)

    lower = _dispute_event(
        "lower",
        "RELIANCE",
        SourceTier.SOCIAL_DISCUSSION,
        1,
        "Reliance denies it signed the agreement",
    )
    lower_result = judge_dispute(earlier, lower, propose_dispute(lower.evidence))

    other = _dispute_event(
        "other",
        "INFY",
        SourceTier.CREDIBLE_REPORTING,
        1,
        "Infosys denies it signed the agreement",
    )
    other_result = judge_dispute(earlier, other, propose_dispute(other.evidence))

    older = _dispute_event(
        "older",
        "RELIANCE",
        SourceTier.CREDIBLE_REPORTING,
        -1,
        "Reliance denies it signed the agreement",
    )
    older_result = judge_dispute(earlier, older, propose_dispute(older.evidence))
    return [
        (
            "grounded-later-equal-authority",
            accepted is not None
            and accepted.confirmed
            and accepted.state is ContradictionState.DISPUTED,
            "A grounded later denial from an equal-tier source is accepted.",
        ),
        (
            "lower-authority-refused",
            lower_result is not None and not lower_result.confirmed,
            "A social post cannot contradict credible reporting.",
        ),
        (
            "different-company-refused",
            other_result is not None and not other_result.confirmed,
            "A denial about another company cannot attach.",
        ),
        (
            "older-denial-refused",
            older_result is not None and not older_result.confirmed,
            "A denial published earlier cannot contradict a later report.",
        ),
    ]


def _dispute_event(
    event_id: str, symbol: str, tier: SourceTier, day_offset: int, title: str
) -> Event:
    published = datetime(2026, 9, 5, tzinfo=UTC) + timedelta(days=day_offset)
    evidence = Evidence(
        source="news",
        source_ref=event_id,
        tier=tier,
        publisher="Harness fixture",
        subject_company=symbol,
        retrieved_at=published,
        published_at=published,
        title=title,
        body="",
        url=f"fixture://{event_id}",
        security_symbol=symbol,
        category="News",
    )
    return Event(
        event_id=event_id,
        security_symbol=symbol,
        company_name=symbol,
        event_type="Agreements",
        description=title,
        occurred_at=published,
        evidence=(evidence,),
    )
