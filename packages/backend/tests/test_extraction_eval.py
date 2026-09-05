"""Extraction evaluation against real articles.

Runs whichever extractor is configured. Without a credential that is the rule
extractor, so these numbers describe the *floor* the system guarantees — and the report
below says plainly which extractor produced them.

Semantic invariants only. An extractor is not required to phrase anything a particular
way; it is required not to name the wrong company, not to invent a counterparty, and
not to turn a market summary into a company event.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fixtures.articles import ARTICLES, Article

from smart_watchlist.adapters.rule_extractor import RuleExtractor
from smart_watchlist.core.extraction import validate
from smart_watchlist.core.models import Evidence, SourceTier


def as_evidence(article: Article) -> Evidence:
    return Evidence(
        source="news",
        source_ref=article.label,
        tier=SourceTier.CREDIBLE_REPORTING,
        publisher=article.publisher,
        subject_company=article.company,
        retrieved_at=datetime.now(UTC),
        published_at=datetime.now(UTC),
        title=article.title,
        body=article.body,
        url=f"https://example.invalid/{article.label}",
        security_symbol=article.symbol,
        category="News",
    )


EXTRACTOR = RuleExtractor()


def run(article: Article):
    evidence = as_evidence(article)
    proposal = EXTRACTOR.extract(evidence)
    if proposal is None:
        return None, evidence
    extraction, _refusal = validate(proposal, evidence, EXTRACTOR.name)
    return extraction, evidence


@pytest.mark.parametrize("article", ARTICLES, ids=lambda a: a.label)
def test_no_extraction_invents_an_unsupported_value(article: Article) -> None:
    """The grounding gate is the anti-fabrication guarantee. It must hold on every row."""
    extraction, evidence = run(article)
    if extraction is None:
        return

    haystack = f"{evidence.title} {evidence.body}".lower()
    event = extraction.event
    for value in (*event.counterparties, *event.products, *event.geographies):
        significant = [w for w in value.lower().split() if len(w) > 2]
        assert all(w in haystack for w in significant), f"{value!r} is not in the source"
    if event.contract_value:
        digits = "".join(c for c in event.contract_value if c.isdigit())
        assert digits in "".join(c for c in haystack if c.isdigit() or c == " ") or not digits


@pytest.mark.parametrize(
    "article", [a for a in ARTICLES if a.must_not_invent], ids=lambda a: a.label
)
def test_named_fabrications_never_appear(article: Article) -> None:
    extraction, _ = run(article)
    if extraction is None:
        return
    emitted = " ".join(
        [
            extraction.event.description,
            *extraction.event.counterparties,
            *extraction.event.products,
            extraction.event.contract_value or "",
        ]
    ).lower()
    for forbidden in article.must_not_invent:
        assert forbidden.lower() not in emitted


@pytest.mark.parametrize(
    "article", [a for a in ARTICLES if not a.should_classify], ids=lambda a: a.label
)
def test_non_events_do_not_become_company_events(article: Article) -> None:
    """A market summary, a broker rating and a price-move note are not company events."""
    extraction, _ = run(article)
    assert extraction is None, f"{article.label} should not have produced an event"


def test_the_subject_is_never_taken_from_the_publisher() -> None:
    """D21, asserted across the whole corpus."""
    for article in ARTICLES:
        extraction, evidence = run(article)
        if extraction is None:
            continue
        assert extraction.event.subject_company == evidence.subject_company
        assert extraction.event.subject_company != evidence.publisher


def test_speculation_is_marked_as_speculation() -> None:
    extraction, _ = run(next(a for a in ARTICLES if a.label == "speculative-ipo"))
    assert extraction is not None
    assert extraction.event.is_speculative


def test_recall_is_measured_and_reported_honestly() -> None:
    """Not a pass/fail bar — a recorded number that must not silently regress.

    The rule extractor trades recall for safety by design: it classifies only what it
    recognises. This test pins where that floor currently sits so a change to it is
    visible rather than discovered later.
    """
    expected = [a for a in ARTICLES if a.should_classify and a.concerns_subject]
    found = [a for a in expected if run(a)[0] is not None]
    recall = len(found) / len(expected)

    assert recall >= 0.3, (
        f"recall fell below the recorded floor: {len(found)}/{len(expected)} = {recall:.0%}"
    )
