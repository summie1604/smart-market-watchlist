# Smart Market Watchlist

**An attention system for Indian equities — not another price dashboard.**

## The problem

Markets generate infinite information. The scarce resource is human attention. Every tool
in this space answers *"what happened?"* — and then hands you a feed, which is the same
problem in a nicer font.

## The question

> **What changed while I was away, and does it deserve me?**

Nine companies. Roughly 400 articles a cycle. On a normal day, two things deserve you.
The product's whole job is finding which two, and being able to show its working.

## Why it is different

| | |
|---|---|
| **Three independent axes** | Attention (does it matter) · Confidence (how sure) · Source standing (what kind of source). Never blended into one score. |
| **Deterministic, explainable ranking** | Every verdict carries the signed reason codes that produced it. A level that cannot explain itself cannot be ranked. |
| **Review checkpoint** | The system knows what you have already seen. "Since your last review" is a real window, not a rolling feed. |
| **Coverage honesty** | *"We looked and nothing changed"* and *"we could not look"* are different verdicts and never rendered alike. Absence of evidence is not evidence of absence. |
| **Grounded assistant** | Answers only from stored records. No model in the answer path, so there is nothing that could invent a price or a cause. |
| **Watch points** | Your own price level or percentage move, settled on stored closes, announced once. |
| **Correlation, never causation** | News beside a move is reported as *"context, not cause"*. |

## AI's actual role

Be clear about this, because it is the opposite of most submissions in this space:

- **Gemini extracts** structured claims from unstructured reporting — subject company,
  event type, counterparties, figures.
- **Gemini does not decide attention.** Significance, confidence, source standing,
  ordering, coverage and contradiction are all deterministic.
- **Every extracted value must appear in the source text** or it is dropped and the drop
  is recorded. That gate is the anti-fabrication guarantee, and it is code, not a prompt.
- **If Gemini is unavailable**, a deterministic rule extractor runs and the system keeps
  working with a plainly weaker reading. The free tier caps 20 requests per model per day,
  so this happens routinely — it is a designed path, not an error case.

> **AI extracts. Rules decide. Evidence explains.**

## Architecture

```
adapters/          NSE disclosures · Google News · yfinance · Gemini · SQLite
   ↓ evidence + a coverage record, together, including on failure
core/              deterministic, no I/O:
                   engine · scoring · linking · corroboration · standing
                   contradiction · prices · review · watchpoints · explainer
   ↓
api/               thin shell, /v1, Pydantic → OpenAPI → generated TypeScript
   ↓
packages/web       Astro + React islands        packages/mobile   Expo proof
```

`core/` imports nothing from `api/`. Forty architectural decisions are recorded in
[`DESIGN.md`](DESIGN.md); the product thesis is in [`VISION.md`](VISION.md); where the
build actually is, including what is unbuilt, is in [`docs/status.md`](docs/status.md).

## Running it

```bash
make install && make test     # 388 backend + 48 frontend/mobile
make run                      # API on :8000, web on :4321
```

Open http://localhost:4321. Demo mode is on by default, so there is no sign-up.

## Deploying

One container, one process, one origin — the API serves the built frontend, which removes
the cross-origin cookie problem rather than configuring around it.

```bash
docker build -t smart-market-watchlist .
docker run -p 8000:8000 -v swl-data:/data --env-file .env smart-market-watchlist
```

**Mode** — `SMART_WATCHLIST_MODE=live` (default) or `judge`. An unknown value fails at
startup rather than silently serving the wrong data.

**Environment** — see [`.env.example`](.env.example). Nothing is required; every value has
a development-safe default and a missing credential is reported as a coverage fact.

**Persistence** — `/data` must be a mounted volume. One SQLite file holds shared
intelligence and private user state; migrations are append-only and run at startup.
Without the volume, every restart starts from nothing.

**Scheduler** — in-process, one cycle at a time, 15-minute interval. **Run exactly one
container.** Two instances against one volume would ingest simultaneously; SQLite is the
recorded choice (D10) and the trigger for changing it is concurrent writers, which is
precisely this. Last cycle and its health are observable at `/v1/scheduler`.

**Health** — `GET /health` is liveness only. It deliberately says nothing about source
coverage, because that is a domain verdict and lives on each assessment.

## Judge demo

A deployed demo should not depend on an interesting market event happening shortly before
someone looks at it. Judge mode seeds a fixed six-company scenario and serves it with
ingestion disabled.

```bash
SMART_WATCHLIST_MODE=judge docker run -p 8000:8000 -v swl-judge:/data --env-file .env \
  smart-market-watchlist
```

**The data is simulated. The reasoning is not.** The fixtures are *sources* — they
implement the same adapter protocols as NSE, Google News and yfinance — and the ordinary
ingestion cycle runs over them. Every attention level, reason code, coverage record,
watch-point trigger and assistant answer is produced by the same deterministic code that
runs in production. A judge who opens **Why you're seeing this** sees the real ledger:

```
+1  Moved +6.4%, +35.3 times its own typical session.
+1  Volume 2.4 times its trailing median.
+3  Agreements concerning this company specifically.
+2  The shares moved unusually (+6.4%) over the same period. Reported as context, not cause.
 = 6 → HIGH at medium confidence
```

The scenario demonstrates, in one review:

| Company | State |
|---|---|
| RELIANCE | **HIGH** — exchange filing, unusual company-specific move, independent established reporting, sector does not explain it |
| TCS | **MEDIUM** — corroborated reporting, no unusual move. Attention is not a price alert |
| HDFCBANK | **Watch point triggered** — a level set two days earlier, crossed and settled by the ordinary evaluator |
| TMPV | **Sector-explained** — the shares moved and the sector moved with them |
| INFY | **No market data** — price unavailable, `NO_MARKET_OBSERVATION` in the ledger |
| ITC | **Could not evaluate reliably** — nothing new *and* a degraded source. Not called quiet |

A banner states *"Judge demo · simulated market scenario"* on every screen, and **Reset
demo** restores the scenario for the next run. Judge state lives in its own database file;
seeding and reset both refuse any database that holds records and is not a marked fixture.

Judge mode reaches no external provider — verified by making all four adapters raise
during seeding.

## Testing

```
388 backend (pytest)      48 frontend + mobile (bun)
lint + typecheck clean across backend, shared, web, mobile
```

Extraction is separately evaluated against 21 hand-labelled articles
(`make llm-harness`): the rule extractor reaches **100% precision, 64.3% recall**, and
Gemini reached 100%/100% across three sibling flash models. Those are *fixture* figures
and the report says so.

## Limitations

Stated rather than discovered:

- **No predictions, no investment advice, no invented causation.**
- **The attention engine is not yet quantitatively evaluated.** Passing tests prove the
  implementation matches its specification, not that the ranking is useful. A labelled
  evaluation set is scaffolded in `packages/backend/evaluation/` and deliberately empty.
- **Nine curated companies**, not fifty. Depth over breadth; everything else is `LIMITED`
  and says so.
- **End-of-day data only.** No intraday. A level crossed and recovered inside one session
  is never seen.
- **`yfinance` and Google News are unofficial**, and two NSE sector indices stopped
  updating in July 2026 — they are excluded from comparisons and named.
- **Contradiction recall is low by construction.** Four gates must all pass.
- Demo mode shares one account with every anonymous visitor. Turn it off for real users.
