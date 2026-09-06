"""The bounded explainer (D35).

Every test here is about a limit rather than a capability. The feature is small; what
makes it safe is what it refuses to do, so that is what is pinned: no advice, no
fabrication, no unsourced sentence, no external call, and an explicit "I don't have
enough evidence" wherever the record runs out.
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from support import coverage, make_evidence

from smart_watchlist.core.contradiction import judge_dispute, propose_dispute
from smart_watchlist.core.engine import assess
from smart_watchlist.core.explainer import Intent, resolve_intent
from smart_watchlist.core.models import Event

PASSWORD = "correct horse battery staple"


@pytest.fixture
def app_module(tmp_path, monkeypatch):
    monkeypatch.setenv("WATCHLIST_DB", str(tmp_path / "explainer.db"))
    monkeypatch.setenv("DEMO_MODE", "on")
    import smart_watchlist.api.app as module

    importlib.reload(module)
    return module


@pytest.fixture
def client(app_module):
    return TestClient(app_module.app)


def store_event(
    app_module,
    *,
    ref: str,
    symbol: str = "RELIANCE",
    category: str = "Outcome of Board Meeting",
    when: datetime | None = None,
    source: str = "nse-disclosures",
    title: str | None = None,
) -> None:
    from dataclasses import replace

    moment = when or datetime.now(UTC)
    evidence = replace(
        make_evidence(symbol=symbol, category=category, ref=ref),
        source=source,
        title=title or f"{symbol}: {category}",
        published_at=moment,
    )
    app_module._store().save(
        assess(
            Event(
                event_id=ref,
                security_symbol=symbol,
                company_name=symbol,
                event_type=category,
                description=title or f"{symbol}: {category}",
                occurred_at=moment,
                evidence=(evidence,),
            ),
            coverage(),
        )
    )


def ask(client, question: str, symbol: str = "RELIANCE"):
    return client.post(f"/v1/companies/{symbol}/explain", json={"question": question})


# --- intent resolution ----------------------------------------------------------


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("What changed recently?", Intent.WHAT_CHANGED),
        ("why does this need my attention", Intent.WHY_ATTENTION),
        ("what could you not see?", Intent.COVERAGE),
        ("how many independent sources reported this", Intent.CORROBORATION),
        ("what did the share price do", Intent.PRICE_CONTEXT),
        ("has anything been disputed", Intent.CONTRADICTION),
        ("who is the chief executive", Intent.UNSUPPORTED),
        ("", Intent.UNSUPPORTED),
    ],
)
def test_questions_resolve_to_the_bounded_set(question, expected) -> None:
    assert resolve_intent(question) is expected


@pytest.mark.parametrize(
    "question",
    [
        "should i buy this",
        "is it worth holding?",
        "what is the price target",
        "will the price go up",
        "can you recommend an entry",
        "predict next quarter",
    ],
)
def test_advice_is_refused_however_it_is_phrased(question) -> None:
    assert resolve_intent(question) is Intent.OUT_OF_SCOPE_ADVICE


def test_advice_wins_over_a_question_it_is_wrapped_in() -> None:
    """ "Should I buy given the results?" mentions results. Answering the second half
    would be answering the wrong half of the sentence."""
    assert resolve_intent("should I buy given the latest results?") is Intent.OUT_OF_SCOPE_ADVICE


# --- failure states -------------------------------------------------------------


def test_an_unsupported_security_is_refused(client) -> None:
    assert ask(client, "what changed?", symbol="NOTREAL").status_code == 404


@pytest.mark.parametrize("question", ["", "x" * 301])
def test_an_empty_or_oversized_question_is_rejected_by_the_schema(client, question) -> None:
    assert ask(client, question).status_code == 422


def test_advice_is_refused_without_looking_anything_up(client, app_module) -> None:
    store_event(app_module, ref="e1")

    body = ask(client, "should I buy Reliance?").json()

    assert body["answered"] is False
    assert body["intent"] == "out_of_scope_advice"
    assert body["insufficient_reason"] == "out-of-scope"
    assert body["evidence"] == [], "a refusal cites nothing because it claims nothing"
    assert "not investment advice" in body["disclaimer"]


def test_a_question_outside_the_set_offers_what_can_be_asked(client, app_module) -> None:
    store_event(app_module, ref="e1")

    body = ask(client, "who is the chief executive?").json()

    assert body["answered"] is False
    assert body["insufficient_reason"] == "unsupported"
    assert len(body["suggestions"]) >= 3


def test_no_stored_record_says_so_rather_than_guessing(client) -> None:
    body = ask(client, "what changed recently?").json()

    assert body["answered"] is False
    assert body["insufficient_reason"] == "no-evidence"
    assert "don't have enough evidence" in body["statements"][0]["text"]


def test_a_question_the_record_cannot_answer_declines(client, app_module) -> None:
    """Nothing disputed is a real answer, and it is not the same as no evidence."""
    store_event(app_module, ref="e1")

    body = ask(client, "has anything been disputed?").json()

    assert body["answered"] is False
    assert body["insufficient_reason"] == "no-record-of-that"


def test_a_price_question_answers_only_from_stored_observations(client, app_module) -> None:
    """A user's question must never reach a market feed."""
    store_event(app_module, ref="filing-only")

    body = ask(client, "what did the price do?").json()

    assert body["answered"] is False, "no stored market observation means no answer"
    assert body["insufficient_reason"] == "no-record-of-that"

    store_event(app_module, ref="mkt", category="Unusual price movement", source="market")
    answered = ask(client, "what did the price do?").json()

    assert answered["answered"] is True
    assert "not a live quote" in " ".join(s["text"] for s in answered["statements"])


# --- what an answer must always carry -------------------------------------------


def test_every_answer_states_its_window_and_coverage(client, app_module) -> None:
    """Including refusals: a reader must never infer how far back an answer looked."""
    store_event(app_module, ref="e1")

    for question in ("what changed?", "should I buy?", "who is the CEO?"):
        body = ask(client, question).json()
        assert body["window"]["to"], question
        assert body["window"]["basis"], question
        assert "records" in body["coverage"], question


def test_every_statement_about_the_company_cites_its_events(client, app_module) -> None:
    """A sentence that cannot name its evidence is not emitted (D4, applied to prose)."""
    store_event(app_module, ref="e1")
    store_event(app_module, ref="e2", category="Agreements")

    body = ask(client, "what changed recently?").json()

    assert body["answered"] is True
    assert all(s["event_ids"] for s in body["statements"])
    assert body["evidence"], "cited events travel with their evidence"


def test_citations_resolve_to_evidence_in_the_same_response(client, app_module) -> None:
    """A citation the reader cannot follow is not a citation."""
    store_event(app_module, ref="e1")

    body = ask(client, "why does this need my attention?").json()
    cited = {i for s in body["statements"] for i in s["event_ids"]}

    assert cited
    assert body["evidence"], "every cited event contributes its sources"


def test_a_coverage_gap_is_stated_even_when_not_asked_about(client, app_module) -> None:
    store_event(app_module, ref="e1")

    body = ask(client, "what changed recently?").json()

    assert "complete" in body["coverage"]
    assert isinstance(body["coverage"]["records"], list)


def test_the_answer_names_the_path_that_produced_it(client, app_module) -> None:
    store_event(app_module, ref="e1")

    assert ask(client, "what changed?").json()["generated_by"] == "deterministic/explainer/v1"


# --- it explains the record, it does not re-judge it -----------------------------


def test_why_attention_repeats_the_engines_reason_codes(client, app_module) -> None:
    store_event(app_module, ref="e1")
    stored = app_module._store().for_symbol("RELIANCE", 10)[0]

    body = ask(client, "why does this matter?").json()
    text = " ".join(s["text"] for s in body["statements"])

    for reason in stored.reasons:
        assert reason.detail in text, "the ledger is the answer, not a paraphrase of it"
    assert stored.attention.value.replace("_", " ").lower() in text
    assert stored.confidence.value.lower() in text


def test_the_window_is_the_readers_own(client, app_module) -> None:
    """Two readers of one company get the same records and different windows."""
    old = datetime.now(UTC) - timedelta(days=3)
    store_event(app_module, ref="old", when=old)
    client.post("/v1/watchlist", json={"symbol": "RELIANCE"})

    body = ask(client, "what changed recently?").json()

    assert body["window"]["basis"] == "since you started watching it"
    assert body["answered"] is True


def test_a_company_not_on_the_watchlist_claims_no_personal_window(client, app_module) -> None:
    store_event(app_module, ref="e1")

    body = ask(client, "what changed recently?").json()

    assert "not on your watchlist" in body["window"]["basis"]


def test_a_disputed_record_is_explained_as_confidence_not_severity(client, app_module) -> None:

    when = datetime.now(UTC)
    store_event(
        app_module,
        ref="claim",
        category="Agreements",
        when=when - timedelta(days=1),
        source="news",
        title="Reliance signs supply agreement with Vertelo",
    )
    store_event(
        app_module,
        ref="denial",
        category="Agreements",
        when=when,
        source="news",
        title="Reliance denies it signed any supply agreement with Vertelo",
    )

    store = app_module._store()
    claim = store.get("claim")
    denial = store.get("denial")
    assert claim is not None and denial is not None
    judged = judge_dispute(claim.event, denial.event, propose_dispute(denial.event.evidence))
    assert judged is not None and judged.confirmed
    store.set_contradiction("claim", judged.state, judged.disputed_by, judged.detail)

    body = ask(client, "has anything been disputed?").json()
    text = " ".join(s["text"] for s in body["statements"])

    assert body["answered"] is True
    assert "disputed" in text.lower()
    assert "how sure we are, not how much it matters" in text


def test_asking_never_triggers_ingestion_or_an_external_call(
    client, app_module, monkeypatch
) -> None:
    """The strongest claim this feature makes, so it is tested rather than asserted."""
    from smart_watchlist.adapters.gemini_extractor import GeminiExtractor
    from smart_watchlist.adapters.google_news import GoogleNewsSource
    from smart_watchlist.adapters.nse_disclosures import NseDisclosureSource
    from smart_watchlist.adapters.yfinance_market import YFinanceMarketSource

    def explode(*args, **kwargs):
        raise AssertionError("a user question reached an external source")

    # Every way out of this process, closed. Patching httpx itself would also break the
    # test client, which speaks httpx to the app.
    monkeypatch.setattr(YFinanceMarketSource, "fetch", explode)
    monkeypatch.setattr(GoogleNewsSource, "fetch", explode)
    monkeypatch.setattr(NseDisclosureSource, "fetch", explode)
    monkeypatch.setattr(GeminiExtractor, "extract", explode)
    store_event(app_module, ref="e1")

    before = app_module._store().recent(100)
    for question in ("what changed?", "what did the price do?", "what could you not see?"):
        assert ask(client, question).status_code == 200

    assert len(app_module._store().recent(100)) == len(before), "no ingestion happened"


def test_the_explainer_reads_a_bounded_slice_of_one_company(client, app_module) -> None:
    """An unbounded per-company read is an unbounded response."""
    for index in range(60):
        store_event(app_module, ref=f"e{index}", when=datetime.now(UTC) - timedelta(hours=index))

    assert len(app_module._store().for_symbol("RELIANCE", 50)) == 50
    assert ask(client, "what changed recently?").status_code == 200
