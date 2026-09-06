"""The evaluator is reproducible, isolated and honest about fallback."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from smart_watchlist.core.extraction import ExtractedEvent
from smart_watchlist.core.models import Evidence, SourceTier
from smart_watchlist.evaluation import FallbackChain, HarnessCase, ProviderRates, run_harness


def evidence(ref: str = "case-1") -> Evidence:
    now = datetime(2026, 9, 5, tzinfo=UTC)
    return Evidence(
        source="news",
        source_ref=ref,
        tier=SourceTier.CREDIBLE_REPORTING,
        publisher="Reuters",
        subject_company="Reliance Industries",
        retrieved_at=now,
        published_at=now,
        title="Reliance signs supply agreement with Acme",
        body="",
        url="fixture://case-1",
        security_symbol="RELIANCE",
        category="News",
    )


class TracedExtractor:
    name = "test/model/prompt-v1"
    last_raw_output = '{"event_type":"Agreements"}'
    last_input_tokens = 100
    last_output_tokens = 20
    last_failure = None

    def extract(self, item: Evidence) -> ExtractedEvent:
        return ExtractedEvent(
            subject_company=item.subject_company,
            event_type="Agreements",
            description=item.title,
            counterparties=("Acme", "Invented Corp"),
        )


class EmptyExtractor:
    name = "empty/model/prompt-v1"
    last_failure = "quota-exhausted"

    def extract(self, _item: Evidence) -> None:
        return None


def test_harness_records_trace_grounding_latency_tokens_and_cost(tmp_path) -> None:
    database = tmp_path / "harness.db"
    report = run_harness(
        [HarnessCase(evidence(), True, True, ("Invented Corp",))],
        [TracedExtractor()],
        database,
        {"test/model/prompt-v1": ProviderRates(1.0, 2.0)},
    )

    provider = report.providers[0]
    assert provider.true_positive == 1
    assert provider.grounding_rejections == 1
    assert provider.input_tokens == 100
    assert provider.output_tokens == 20
    assert provider.estimated_cost_usd == 0.00014
    assert report.contradiction_passed == report.contradiction_cases == 4
    assert provider.unsupported_field_rate == 1.0
    assert provider.schema_failures == 0

    connection = sqlite3.connect(database)
    row = connection.execute(
        "SELECT raw_output, dropped_fields, validated_extraction FROM harness_trials"
    ).fetchone()
    connection.close()
    assert row is not None
    assert "event_type" in row[0]
    assert "counterparties" in row[1]
    assert "Invented Corp" not in row[2], "the stored validated result passed the real gate"


def test_harness_database_has_no_product_tables(tmp_path) -> None:
    database = tmp_path / "harness.db"
    run_harness([HarnessCase(evidence(), True, True)], [TracedExtractor()], database)

    connection = sqlite3.connect(database)
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    connection.close()

    assert tables >= {"harness_runs", "harness_trials", "harness_checks"}
    assert not {"assessments", "evidence", "users", "watchlist"} & tables


def test_fallback_is_named_and_counted_instead_of_borrowing_model_identity(tmp_path) -> None:
    chained = FallbackChain(EmptyExtractor(), TracedExtractor())
    report = run_harness(
        [HarnessCase(evidence(), True, True)],
        [chained],
        tmp_path / "harness.db",
    )

    provider = report.providers[0]
    assert provider.fallback_uses == 1
    assert provider.provider.startswith("pipeline:")
    assert provider.true_positive == 1


def test_no_outputs_report_precision_and_unsupported_rate_as_unmeasured(tmp_path) -> None:
    report = run_harness(
        [HarnessCase(evidence(), True, True, ("Invented Corp",))],
        [EmptyExtractor()],
        tmp_path / "harness.db",
    )

    provider = report.providers[0]
    assert provider.precision is None
    assert provider.unsupported_field_rate is None
    assert "| n/a | 0.0% | n/a |" in report.markdown()
