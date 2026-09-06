"""Measure the current architecture against its stated local targets."""

from __future__ import annotations

import argparse
from pathlib import Path

from smart_watchlist.evaluation.load import run_load_validation


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local scalability validation.")
    parser.add_argument("--iterations", type=int, default=500)
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--report", type=Path, default=Path(".artifacts/scalability.md"))
    arguments = parser.parse_args()

    report = run_load_validation(arguments.iterations, arguments.workers).markdown()
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(report, encoding="utf-8")
    print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
