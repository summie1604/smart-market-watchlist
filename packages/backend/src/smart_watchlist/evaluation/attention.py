"""Evaluating the attention engine — the thing tests do not prove.

388 passing tests establish that the implementation matches its specification. They say
nothing about whether the specification is *useful*: whether the things the engine calls
HIGH are the things a reader would have wanted, and whether the things it calls quiet
were safely ignorable. That is a different question and it needs labelled data.

**This module deliberately ships with an empty set.** Inventing labels would produce a
number that looks like evidence and is not, which is worse than admitting the gap — and
the gap is admitted in the README and in ``docs/status.md``. What is here is the harness
that will measure it, working and tested, so adding real labels is the only remaining
step.

The measurement is deliberately blunt. Attention is a five-level ordinal scale and the
useful questions are about the top of it: when the system demands a reader, is it right,
and what did it miss? Everything else is diagnostics for *why* a case failed.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..core.models import Attention

if TYPE_CHECKING:
    from collections.abc import Iterable

    from ..core.models import Assessment

__all__ = [
    "AttentionReport",
    "LabelledCase",
    "evaluate_attention",
    "render_report",
]

DEMANDING = (Attention.HIGH, Attention.MEDIUM)
"""The levels that ask a reader for something. Precision and recall are measured here,
because a wrong LOW costs a glance and a wrong HIGH costs trust."""


@dataclass(frozen=True)
class LabelledCase:
    """One assessment with a human judgement attached.

    ``expected`` is what a careful reader, with the same evidence and the benefit of
    hindsight, thinks the level should have been. ``note`` is why — it is what makes a
    disagreement diagnosable rather than just counted.
    """

    event_id: str
    symbol: str
    description: str
    expected: Attention
    note: str = ""


@dataclass(frozen=True)
class Disagreement:
    case: LabelledCase
    produced: Attention
    reason_codes: tuple[str, ...]
    """The codes behind the produced level. A failure is only actionable if you can see
    which contribution carried it."""
    coverage_gaps: tuple[str, ...]


@dataclass(frozen=True)
class AttentionReport:
    cases: int = 0
    agreed: int = 0
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    false_positive_codes: Counter[str] = field(default_factory=Counter)
    false_negative_codes: Counter[str] = field(default_factory=Counter)
    gaps_in_failures: Counter[str] = field(default_factory=Counter)
    disagreements: tuple[Disagreement, ...] = ()

    @property
    def precision(self) -> float | None:
        demanded = self.true_positives + self.false_positives
        return None if demanded == 0 else self.true_positives / demanded

    """``None`` rather than 1.0 when nothing was demanded — a system that surfaced nothing
    has not achieved perfect precision, it has not been measured."""

    @property
    def recall(self) -> float | None:
        wanted = self.true_positives + self.false_negatives
        return None if wanted == 0 else self.true_positives / wanted

    @property
    def agreement(self) -> float | None:
        return None if self.cases == 0 else self.agreed / self.cases


def evaluate_attention(
    labelled: Iterable[LabelledCase], assessments: Iterable[Assessment]
) -> AttentionReport:
    """Compare produced levels against labelled ones.

    A labelled case with no matching assessment is skipped rather than counted as a
    failure: it means the event was never assessed at all, which is an ingestion question
    and not an attention question. Conflating the two would blame the engine for a feed.
    """
    produced = {a.event.event_id: a for a in assessments}
    cases = [case for case in labelled if case.event_id in produced]

    agreed = 0
    tp = fp = fn = 0
    fp_codes: Counter[str] = Counter()
    fn_codes: Counter[str] = Counter()
    gaps: Counter[str] = Counter()
    disagreements: list[Disagreement] = []

    for case in cases:
        assessment = produced[case.event_id]
        actual = assessment.attention
        codes = tuple(r.code for r in assessment.reasons)
        missing = tuple(sorted({r.source for r in assessment.coverage.missing}))

        if actual is case.expected:
            agreed += 1

        demanded = actual in DEMANDING
        wanted = case.expected in DEMANDING
        if demanded and wanted:
            tp += 1
        elif demanded and not wanted:
            fp += 1
            fp_codes.update(codes)
            gaps.update(missing)
        elif wanted and not demanded:
            fn += 1
            fn_codes.update(codes)
            gaps.update(missing)

        if actual is not case.expected:
            disagreements.append(
                Disagreement(case=case, produced=actual, reason_codes=codes, coverage_gaps=missing)
            )

    return AttentionReport(
        cases=len(cases),
        agreed=agreed,
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        false_positive_codes=fp_codes,
        false_negative_codes=fn_codes,
        gaps_in_failures=gaps,
        disagreements=tuple(disagreements),
    )


def render_report(report: AttentionReport, scoring_version: str) -> str:
    """Markdown, and honest about an empty set."""
    if report.cases == 0:
        return (
            "# Attention evaluation\n\n"
            "**No labelled cases.** The harness runs; the set is empty on purpose. "
            "Numbers invented here would look like evidence and would not be.\n\n"
            "Add cases to `evaluation/labelled.py` and re-run `make attention-eval`.\n"
        )

    def pct(value: float | None) -> str:
        return "not measured" if value is None else f"{value * 100:.1f}%"

    lines = [
        "# Attention evaluation",
        "",
        f"Scoring version `{scoring_version}` · {report.cases} labelled cases.",
        "",
        "Fixture performance against human labels, not a claim about live ranking.",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Demanding precision (HIGH+MEDIUM) | {pct(report.precision)} |",
        f"| Demanding recall | {pct(report.recall)} |",
        f"| Exact label agreement | {pct(report.agreement)} |",
        f"| False positives | {report.false_positives} |",
        f"| False negatives | {report.false_negatives} |",
        "",
    ]
    if report.false_positive_codes:
        lines += ["**Reason codes present in false positives**", ""]
        lines += [f"- `{code}` x {n}" for code, n in report.false_positive_codes.most_common(8)]
        lines.append("")
    if report.false_negative_codes:
        lines += ["**Reason codes present in false negatives**", ""]
        lines += [f"- `{code}` x {n}" for code, n in report.false_negative_codes.most_common(8)]
        lines.append("")
    if report.gaps_in_failures:
        lines += ["**Coverage gaps present in failures**", ""]
        lines += [f"- `{source}` x {n}" for source, n in report.gaps_in_failures.most_common()]
        lines.append("")
    return "\n".join(lines)
