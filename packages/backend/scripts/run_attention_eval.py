"""Run the attention evaluation against the stored assessments.

Reads the same database the application reads and writes a markdown report beside the
extraction harness's. It never writes to the assessment store.
"""

from __future__ import annotations

import os
from pathlib import Path

from smart_watchlist.adapters.sqlite_store import SqliteAssessmentStore
from smart_watchlist.core.scoring import SCORING_VERSION
from smart_watchlist.evaluation.attention import evaluate_attention, render_report
from smart_watchlist.evaluation.labelled import LABELLED


def main() -> int:
    store = SqliteAssessmentStore(os.environ.get("WATCHLIST_DB", "watchlist.db"))
    report = evaluate_attention(LABELLED, store.recent(2000))
    out = Path(".artifacts/attention-eval.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_report(report, SCORING_VERSION), encoding="utf-8")
    print(f"wrote {out} ({report.cases} labelled cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
