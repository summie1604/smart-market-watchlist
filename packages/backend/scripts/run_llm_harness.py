"""Run the extraction harness without touching production state."""

from __future__ import annotations

import argparse
import runpy
from pathlib import Path
from typing import TYPE_CHECKING

from smart_watchlist.adapters.claude_extractor import ClaudeExtractor
from smart_watchlist.adapters.gemini_extractor import GeminiExtractor
from smart_watchlist.adapters.rule_extractor import RuleExtractor
from smart_watchlist.evaluation import FallbackChain, HarnessCase, ProviderRates, run_harness

if TYPE_CHECKING:
    from smart_watchlist.core.ports import Extractor


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Compare extraction providers against one fixed, human-labelled case set."
    )
    result.add_argument(
        "--provider",
        action="append",
        default=[],
        metavar="SPEC",
        help="rules, gemini[:model], or claude[:model]. Repeat to compare providers.",
    )
    result.add_argument(
        "--with-rule-fallback",
        action="store_true",
        help="Also measure each model as a separately named production path with rule fallback.",
    )
    result.add_argument(
        "--database",
        type=Path,
        default=Path(".artifacts/llm-harness.db"),
        help="Isolated SQLite trace store (default: .artifacts/llm-harness.db).",
    )
    result.add_argument(
        "--report",
        type=Path,
        default=Path(".artifacts/llm-harness.md"),
        help="Markdown report path (default: .artifacts/llm-harness.md).",
    )
    result.add_argument(
        "--rate",
        action="append",
        default=[],
        metavar="EXTRACTOR=INPUT,OUTPUT",
        help="USD per million input/output tokens for an exact extractor name.",
    )
    return result


def extractor(specification: str) -> Extractor:
    provider, _, model = specification.partition(":")
    if provider == "rules" and not model:
        return RuleExtractor()
    if provider == "gemini":
        return GeminiExtractor(model=model or None)
    if provider == "claude":
        return ClaudeExtractor(model=model or None)
    raise ValueError(
        f"unknown provider {specification!r}; use rules, gemini[:model], or claude[:model]"
    )


def rates(values: list[str]) -> dict[str, ProviderRates]:
    parsed: dict[str, ProviderRates] = {}
    for value in values:
        name, separator, prices = value.partition("=")
        if not separator or "," not in prices:
            raise ValueError(f"invalid rate {value!r}; expected EXTRACTOR=INPUT,OUTPUT")
        input_price, output_price = prices.split(",", 1)
        parsed[name] = ProviderRates(float(input_price), float(output_price))
    return parsed


def cases() -> list[HarnessCase]:
    fixture = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "articles.py"
    namespace = runpy.run_path(str(fixture))
    articles = namespace.get("ARTICLES")
    if not isinstance(articles, tuple):
        raise RuntimeError("fixture did not expose ARTICLES")
    return [HarnessCase.from_expectation(article) for article in articles]


def main() -> int:
    arguments = parser().parse_args()
    configured = [extractor(item) for item in (arguments.provider or ["rules"])]
    if arguments.with_rule_fallback:
        configured.extend(
            FallbackChain(item, RuleExtractor())
            for item in list(configured)
            if not isinstance(item, RuleExtractor)
        )
    report = run_harness(cases(), configured, arguments.database, rates(arguments.rate))
    rendered = report.markdown()
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
