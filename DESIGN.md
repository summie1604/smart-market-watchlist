# Design — Smart Market Watchlist

## Purpose

This document records the architectural decisions behind the Smart Market Watchlist, the options rejected, and what each choice costs. It is written for whoever implements, reviews or judges the system, and it supports one decision: **is this the right shape to build in the time available, and are the trade-offs the right ones?**

It is not an implementation spec. Nothing here should be recoverable by reading the code; everything here should be hard to recover from the code alone.

**Status: frozen, with D20–D25 appended as earlier implementation exposed missing boundaries and D26–D33 added for the product and platform foundation.** The initial design was frozen before implementation. Every later entry records a boundary that could not safely be left as a silent code choice.

The freeze means implementation must not silently redefine architecture. It does not mean a missing boundary must remain missing once discovered. D1–D19 are unchanged and unrenumbered.

**D26–D33 are now implemented as foundations.** D26–D29 cover the attention experience, interests, price context and contradiction. D30–D33 cover a second client surface, the extraction harness, measured scale and the versioned generated API contract. The mobile work is intentionally a thin proof, not a complete application, and the scale results remain measurements of the paths actually exercised rather than a production-capacity claim.

Every decision below is judged against [`VISION.md`](VISION.md). Where a decision is driven by a specific vision section, it says so.

**The binding constraint is time: two to three days.** That is not a footnote — it is the reason for roughly half the decisions in this document, and it is stated at each one it touches. The governing rule for that budget:

> **Build narrowly. Design broadly.**
>
> A system reasoning correctly across price, authoritative disclosure and news beats a system touching eight sources superficially. Every additional source is another way to be wrong.

---

## Shape

Four external sources feed one ingestion path. Evidence is normalized into events, events are deduplicated and given identity, and the **Meaningful Change Engine** evaluates each event against a company's curated context to produce an attention assessment made of explicit reason codes. Summaries are generated from those reason codes and persisted. All of that is **shared intelligence** — computed once, regardless of how many users watch the company. Only the final step is per-user: a diff of that shared intelligence against the individual's review checkpoint.

```
External sources
      ↓
Source adapters ──→ Coverage ledger
      ↓
Ingestion (evidence)
      ↓
Normalization (LLM-assisted extraction, deterministically validated)
      ↓
Event identity & deduplication
      ↓
Meaningful Change Engine ←── Company context
      ↓                        (relevance · corroboration · significance · attention)
Lifecycle
      ↓
Summary generation (LLM, from reason codes only)
      ↓
──────────── SHARED INTELLIGENCE ends here ────────────
      ↓
Review assembly ←── User state (watchlist · checkpoint)
      ↓
API
      ↓
Astro (static/server-rendered) + React islands
```

### Modules

- **`sources`** — adapters that fetch from one external provider each and return raw evidence plus a coverage record.
  - exposes: `fetch(scope, window) -> (Evidence[], CoverageRecord)`; one adapter per provider — market, news, disclosure. A social adapter is a planned member of this set and is not built (see *Not doing*).
  - hands off: `Evidence` records to `ingest` — the raw payload, source identity, publisher, retrieval timestamp, and a source-native id for idempotency. Never an interpretation.

- **`ingest`** — persists evidence, enforces idempotency, and writes the coverage ledger.
  - exposes: `run(source, scope)`; `coverage(scope, window) -> CoverageState`
  - hands off: persisted `Evidence` to `normalize`; `CoverageState` to `evaluate` and to review assembly. **Coverage is a first-class output, not logging** — it is what separates "nothing happened" from "we could not look" (VISION §14).

- **`normalize`** — turns heterogeneous evidence into comparable `EventCandidate` records.
  - exposes: `to_candidates(Evidence) -> EventCandidate[]`
  - hands off: `EventCandidate` — companies, event type, description, occurrence time, geographies, industries, possible relationships, evidence refs, extraction provenance — to `identity`. An `EventCandidate` is a *claim derived from evidence*, never a fact. Structured throughout; no module downstream re-parses prose.

- **`identity`** — decides when two candidates describe the same occurrence.
  - exposes: `resolve(EventCandidate) -> LINK | CREATE_NEW | AMBIGUOUS`
  - hands off: `Event` with its accumulated evidence set to `evaluate`. This module is why fifteen articles about one announcement do not read as fifteen confirmations — and why two same-day contracts do not read as one (D12).

- **`context`** — the curated store of what each company is exposed to: sector, competitors, commodities, currencies, geographies, regulatory bodies, index membership, coverage tier.
  - exposes: `profile(security) -> CompanyContext`, carrying per-attribute provenance and an explicit *unknown* state.
  - hands off: `CompanyContext` to `evaluate`. Read-only at runtime; curated offline.

- **`evaluate`** — the Meaningful Change Engine. Relevance, corroboration, significance and attention, as explicit reason codes.
  - exposes: `assess(Event, CompanyContext, MarketObservation, CoverageState) -> Assessment`
  - hands off: `Assessment` — attention level, confidence level, and the **ordered list of signed reason codes that produced them** — to `lifecycle` and `summarize`. The reason codes *are* the decision, not a commentary on it (VISION §15).

- **`market`** — deterministic price, volume and baseline calculations, and corporate-action adjustment.
  - exposes: `observe(security, window) -> MarketObservation` — return, sector-relative residual, volume ratio, position against the security's own trailing baseline, adjustment flags.
  - hands off: `MarketObservation` to `evaluate`. **No LLM touches this path.**

- **`lifecycle`** — maintains each event's world state across time.
  - exposes: `advance(Event, new evidence) -> LifecycleState`
  - hands off: state transitions to `summarize` and review assembly. Owns the refusal to promote silence to RESOLVED.

- **`summarize`** — generates human-readable text from reason codes and validated facts.
  - exposes: `explain(Assessment) -> Summary` with model, prompt version, schema version, source event ids, generation time, and validity state.
  - hands off: persisted `Summary` to review assembly. **Consumes reason codes; may not add, drop or strengthen a claim.**

- **`llm`** — provider-isolated interface with one active model adapter, initially Gemini (D25).
  - exposes: `extract(text, schema)`, `classify(...)`, `phrase(...)` — all returning validated structured output or a failure.
  - hands off: structured candidates to `normalize`, text to `summarize`. Nothing else in the system imports a provider SDK.

- **`userstate`** — accounts, watchlists, review checkpoints.
  - exposes: `watchlist(user)`, `checkpoint(user)`, `complete_review(user, review_cutoff)`
  - hands off: checkpoint and membership to review assembly. The only module that writes private data.

- **`review`** — assembles one user's answer to "what changed since I last checked."
  - exposes: `assemble(user) -> ReviewPage` including the issued `review_cutoff`
  - hands off: a fully-resolved view model to `api`. Contains no scoring logic — it filters and orders shared assessments by the user's window.

- **`api`** — HTTP boundary: authentication, authorization, session handling, view-model delivery.
  - exposes: authenticated endpoints for watchlist management, review assembly and review completion.
  - hands off: JSON view models to the frontend. **Every ownership check lives here or deeper — never in the frontend.**

- **`web`** — Astro shell, statically or server-rendered, with React islands only where interaction demands them.
  - exposes: the user-facing surfaces described under *Journeys*.
  - hands off: user actions back to `api`. **Reproduces no engine logic.** It renders attention levels; it never computes one.

The three-layer separation VISION §19 requires maps onto this directly: `sources`/`market` are source of truth, `evaluate`/`lifecycle` are interpretation, `summarize`/`web` are presentation. Facts never originate downstream of where they were observed.

---

## State

### Shared intelligence — one copy, regardless of user count

Securities, company context, evidence, normalized events, event-to-company relationships, market observations, assessments, lifecycle state, generated summaries, and the coverage ledger.

If ten thousand users watch Reliance, there is one Reliance analysis. This is the difference between a system that scales by adding machines and one that scales by not doing redundant work, and it is why the expensive path (ingest → normalize → identity → evaluate → summarize) is per-company and the cheap path (window filter, ordering) is per-user.

### Private user state — owned, isolated, server-authoritative

Accounts and password hashes, sessions, watchlists and their memberships, review checkpoints, preferences.

Every user-owned row carries an explicit owner. Authorization is enforced at the domain boundary: **changing an id in a request must never reach another user's state.** Hiding a frontend control is not access control.

`localStorage` is permitted only for non-authoritative display preferences — table-versus-card, a collapsed section. It is never authoritative for watchlists, identity, checkpoints or review history, because cross-device persistence is a claim this product makes and localStorage would make it a lie.

### The review window — the correctness invariant

A review answers for the half-open interval `(previous_checkpoint, review_cutoff]`.

`review_cutoff` is issued by the server when the review page is assembled. Events arriving after it belong to the *next* review, even if the user is still reading. On completion the checkpoint advances to the cutoff — **not to the time of the click**:

```
previous checkpoint
        │
        ▼
10:00 ──────────── 11:00 ──── 11:03 ──── 11:05
                  cutoff    new event    "complete"
                     │
                     ▼
          checkpoint becomes 11:00
```

The 11:03 event stays new. Advancing to 11:05 would silently mark as seen something that was never on the page — the exact failure VISION §7 forbids.

Two further rules follow from the same account being open on two devices:

- **Monotonic.** Advancement is `max(current, submitted_cutoff)`. A stale tab submitting an older cutoff is a no-op, never a regression.
- **Idempotent.** Completing the same review twice changes nothing.

### Durability and integrity rules

- Evidence and its event relationships commit together; a partial event is never visible.
- A regenerated summary replaces its predecessor only once complete and valid — a failed generation leaves the previous summary standing, marked by its own age.
- Uniqueness constraints on source-native ids make re-fetching an article, re-ingesting a filing, or retrying a job idempotent by construction rather than by hope.
- Schema changes ship as versioned migrations. The database is never recreated by hand.
- External calls never happen inside a write transaction. Fetch and analyse, then commit briefly.

---

## Journeys

Navigation is an output of these, not an input. No page or menu is decided before the journey that needs it.

Persona throughout: **retail investor**. One role, deliberately (see *Decisions*).

### J1 — First-time user adds a company and says why

Starts with an empty watchlist, wanting to follow companies they already care about. They
search, and each result states its coverage tier before they commit, so they learn the
system's honesty before they learn its verdicts.

**Adding asks three things**, all optional and skippable in one click: *why are you
following this company*, *what developments do you want to watch for*, and a set of tags —
earnings, management, regulation, competitors, contracts, commodities, dividends, unusual
price movement. The first two are free text kept for the user's own reference. Only the tags
drive behaviour, and only as a filter and an annotation (D27).

*Success:* the company is on the watchlist and the user has said, in their own words, what
they are watching for. *Empty:* an empty watchlist explains what the product will do rather
than showing an empty table. *Failure:* an unsupported symbol is refused with the reason.
*Recovery:* search suggests near matches inside the supported universe.

**Baseline problem.** A new membership has no prior checkpoint, so the first review reports
*"we started watching now"* rather than back-filling history as though it had been missed.

### J2 — Returning user opens straight into what needs them

The core journey, and **the default surface**. Arriving after an absence, the user lands on
*Needs attention*: only what is new since their last completed review, ordered by severity
and then by recency (D26).

Each item states the company, what happened, how sure we are, how many independent
publishers back it, and — where the user recorded tags — whether it matches what they said
they were watching for (D27). A focus filter narrows LOW and MEDIUM; it never hides a HIGH,
which appears with a note that it falls outside the stated focus and matters anyway. A
company filter narrows to one name without changing anything else about the order.

Then one deliberate action: **Mark review complete**.

*Success:* the checkpoint advances to the issued cutoff and the next visit starts there.
*Empty — and this is the common case:* nothing new is a real answer, so the screen says so
and points at the watchlist, which still carries the latest known development for every
company followed. An empty *Needs attention* is never an empty product.
*Failure:* sources unavailable produce *unable to fully evaluate*, visually distinct from
quiet, naming what was missing. *Recovery:* the checkpoint does not advance past what could
not be assessed.

### J3 — User opens a HIGH-attention company

From the review, into one company. The page opens with its takeaway — *"two company-specific developments deserve attention; price movement remains within its normal range"* — before any detail. Below: the ranked developments, then market context, then evidence.
*Success:* they understand the situation without opening a single source. *Empty:* a quiet company says so and shows its baseline. *Failure:* partial coverage is stated per signal class, not hidden. *Recovery:* every claim links to its evidence.

### J4 — User investigates why an event was surfaced

The trust journey, and the one that makes the product defensible. From an attention level to the reason codes that produced it — **including the negative ones** — to the supporting signals, to the source evidence. Without leaving the flow.
*Success:* they can restate why the system ranked it, and disagree specifically if they disagree. *Failure:* if reason codes are missing, the item cannot have been ranked HIGH — the engine cannot produce a ranking it cannot explain.

### J5 — User checks provenance

From a claim to its sources: which publishers, whether independent or syndicated, whether officially confirmed, when retrieved, and what the confidence level is built from.
*Success:* the user can tell a filing from a rumour at a glance and in detail. *Failure:* conflicting reports are shown as conflicting, with both sides, not silently resolved.

### J6 — User returns while a source is down

The journey that decides whether silence can be trusted. The review renders with what is available and states what is not — *"news coverage unavailable since 06:40; price data current"* — and marks affected companies **unable to fully evaluate** rather than quiet.
*Success:* the user knows the shape of the gap. *Recovery:* on the source's return, backfilled events are new *to the user* regardless of their wall-clock age, because the review window is defined by the user's checkpoint, not by ingestion time.

### J7 — User removes a stock

Removes a company they no longer follow.
*Success:* it leaves the watchlist; shared intelligence about it is untouched, because it belongs to the world, not to this user. *Recovery:* re-adding restores the user's prior information state — their knowledge did not disappear when the row did — rather than replaying history as new.

### J8 — User searches watchlist intelligence

Looks for a company, an event, a commodity or a theme across what the system knows. Shared intelligence is searchable; private state is not in the shared index.
*Success:* they reach the company or event page. *Empty:* no match distinguishes "nothing indexed" from "nothing happened." *Failure:* search never leaks another user's watchlist, checkpoint or review history.

### J9 — User compares a company against its benchmarks

Inside a company's detail, wanting to know whether a move was the company or the market.
They pick a range and see the company, its sector index and the broad index over the **same
trading sessions**, rebased so the comparison is about relative movement rather than price
levels (D28).

*Success:* they can see whether the company diverged from its sector. *Partial:* where the
three series do not share the full range — a holiday, a suspension, a shorter index history
— the chart shows the span actually covered and says so. *Failure:* no bars for the window
shows an empty chart with the reason, never an interpolated line.
*Boundary:* the chart lives inside the detail. It never appears on the board, because a
price chart on the main surface makes price the subject.

### J10 — User sees an earlier story disputed

They read a development days ago; newer, at-least-as-authoritative evidence now contradicts
it. The record shows the original marked **disputed** and linked to the record disputing it,
with both readable and neither deleted (D29).

*Success:* they understand that what they were told has been contested, and by what.
*Partial:* where the gates do not pass, the two are shown as *possibly related, relationship
not confirmed* — never as a contradiction. *Confidence, not attention:* a disputed report may
still be the most significant thing about the company; what changed is how sure we are.

### Presentation rules these journeys impose

- **Summary before detail, everywhere.** Every dense surface leads with its takeaway: summary → important items → supporting data → raw evidence.
- **Data state is always visible.** Fresh, stale, delayed, partial, unavailable, conflicting, developing, unverified, no-meaningful-change and unable-to-evaluate are ten distinct states, and *no meaningful change* and *unable to evaluate* must never share a visual treatment.
- **Collections are one data contract, two renderings.** Table and card views of the same records, switchable, with no separate logic behind either.
- **Filter and sort are capabilities by default, controls only when useful.** Available on every meaningful collection; not rendered for four rows.
- **Timelines where the question is temporal.** Lifecycle progression is a timeline, not a table — and never decoration.
- **Responsive structure, not shrunken tables.** Mobile gets summary → cards → drill-down, which is a different information structure, not the same one at a smaller size.
- **Explainability is navigation.** J4's path is a first-class route, not a debug panel.

---

## Scenarios

### S1 — A large move that deserves low attention

Infosys falls 3.1%. `market` computes the return, the sector residual against the IT index, and the position against the security's own trailing 60-session distribution; the residual is small. `ingest` reports full coverage for the window. No candidate events clear relevance for Infosys. `evaluate` produces reason codes: *movement outside the security's normal range* (positive, small), *substantially explained by sector movement* (negative), *no company-specific event detected under full coverage* (negative). Attention LOW, confidence HIGH — high because the *absence* is well-evidenced, not because the move is understood.

`summarize` renders it as context, never cause: the sector fell similarly, and no company-specific development was found. The user sees a downgraded 3% move with the reason it was downgraded — the inverse of what a conventional watchlist would do.

### S2 — A resolution retires a concern

Monday: a wire report describes a strike at a Tata Motors supplier. `normalize` extracts a supply-chain disruption candidate; `identity` mints an event; `context` confirms the supplier relationship is a curated attribute, so relevance carries the *stated relationship* provenance rather than an inferred one. Attention MEDIUM, confidence MEDIUM — single-source, uncorroborated. Lifecycle NEW.

Wednesday: a second, independent publisher reports the strike ended. `identity` merges it into the existing event rather than creating a second one. `lifecycle` advances to RESOLVED **because there is positive evidence of resolution** — not because reporting stopped. The next review reports the resolution and retires the concern.

Had no further evidence arrived, the event would decay to STALE, and the user would be told it went quiet — not that it ended. That distinction is the whole point (VISION §11).

### S3 — A corporate action that is not a movement

A stock opens down sharply following a bonus issue. `market` sees the corporate action from the disclosure adapter and adjusts before computing anything. The observation reports an adjusted return near zero and flags the mechanical cause. No unusual-movement reason code fires. The user is told a corporate action occurred, not that their holding deteriorated.

Without adjustment ordering, this is a confidently wrong alert — the cheapest possible way to lose a user's trust.

### S4 — Two users, one company, different answers

Reliance has three assessed developments since Monday. User A last completed a review Monday 10:00; user B, Wednesday 18:00. The shared intelligence is computed once. `review` filters it by each user's window: A sees three, B sees one. Neither triggers re-evaluation; only the diff differs.

### S5 — Extending the system with a new signal family

A developer adds the deferred social signal. They implement one adapter in `sources` returning `Evidence` and a `CoverageRecord`, register it, add its publisher tier so provenance ranks it below reporting, and add reason codes with weights to the versioned scoring configuration.

**Unchanged:** normalization, identity, the engine, lifecycle, summaries, user state, API, frontend. The engine consumes `Event` and `CompanyContext`; it has no knowledge of where evidence came from beyond its source tier. That is the test the seam has to pass, and it is the reason social was safe to defer rather than dangerous.

### Demo scenarios to protect

Eight behaviours the build must be able to show. They are listed here because they double as the acceptance criteria for the engine — each one fails loudly if a specific piece of the design is missing.

| | Scenario | Proves | Depends on |
|---|---|---|---|
| **A** | Price moves; evidence insufficient | The system refuses to manufacture a causal narrative | D14, VISION §13 |
| **B** | Relevant news + abnormal movement | Independent signals combine into stronger attention | D4, D14 |
| **C** | Authoritative disclosure vs speculation | Provenance tiers are real, not decorative | D13, disclosure adapter |
| **D** | Several articles, one evolving situation | Linking updates one event instead of emitting duplicate alerts | D12 |
| **E** | Positive resolution: NEW → DEVELOPING → CONFIRMED → RESOLVED | Resolution is detected from evidence and retires the concern | D16 |
| **F** | Silence: NEW → DEVELOPING → STALE | **Silence is not resolution** | D16 |
| **G** | Split or bonus issue | Mechanical movement is adjusted before anomaly evaluation, not reported as deterioration | D14 ordering |
| **H** | Required sources unavailable | "Unable to evaluate reliably" instead of "no meaningful change" | D15 |

E and F are the pair that matters most: together they show the system distinguishing *evidence of resolution* from *absence of evidence*, which is the single hardest claim in `VISION.md` §11 and the one no comparable product makes.

---

## Decisions

### D1 — Python backend, Astro + React islands frontend

- **Options:** **A** — Python backend, Astro/TypeScript frontend with React islands. **B (simplest)** — TypeScript end-to-end: one language, one toolchain, no context switching. **C** — Python end-to-end with server-rendered templates: least code of all.
- **Chose:** A. The hard half of this system is a data and analysis pipeline — baselines, corporate-action adjustment, dedup, scoring, LLM-assisted extraction — where Python's ecosystem is decisive. The visible half has genuine interaction state (watchlist management, filtering, sorting, table/card switching, timelines, review completion) that C makes awkward. B would force the analysis work into the weaker ecosystem to save a language.
- **Consequences:** Two languages, two toolchains, two sets of conventions — accepted deliberately because the halves solve substantially different problems. A typed contract at the API boundary becomes load-bearing, since the compiler cannot span it. No further frontend or backend framework enters without a demonstrated requirement.

### D2 — Static by default, dynamic by necessity

- **Options:** **A** — Astro shell, static/server-rendered, React islands only where interaction demands. **B** — React SPA: one mental model, natural for stateful UI, ships a large client bundle and hydrates everything. **C (simplest)** — fully static: fastest, cannot express per-user state at all.
- **Chose:** A. Most of what the product shows is precomputed shared intelligence and stable between reviews; C cannot express authentication or per-user windows, and B pays SPA costs on pages that are largely read-only.
- **Consequences:** Islands must be chosen deliberately — the rule is that one interactive component does not hydrate its page. The boundary is architectural, not stylistic: **the frontend renders attention levels and never computes one.** Any engine logic appearing in the frontend is a defect regardless of how well it works.

### D3 — Background ingestion, pull-based experience

- **Options:** **A** — scheduled background ingestion; the UI reads precomputed intelligence. **B (simplest)** — fetch and evaluate on page load: no scheduler, no worker, nothing running between visits.
- **Chose:** A. B cannot answer the product's central question. "What changed while I was gone" requires having been watching while they were gone; a system that only looks when the user arrives can compare two snapshots but cannot observe a development, track a lifecycle, or know that a source was down at 06:40. B also puts multi-second fetches and LLM calls in the page-load path.
- **Consequences:** A worker process must be running for the product to be what it claims — a real deployment dependency and a demo risk to be rehearsed. In exchange, page loads read persisted data, latency is decoupled from source and model latency, and coverage history exists to be reported.

### D4 — Attention as additive reason codes over a versioned weight set

- **Options:** **A** — signed reason-code contributions summed against thresholds, weights in versioned configuration. **B** — a decision tree of explicit rules. **C** — a trained classifier. **D** — ask the LLM to rank.
- **Chose:** A. VISION §15 requires the explanation to *be* the decision record. A produces the ledger — positives, negatives, and their weights — as a by-product of scoring. B can explain the branch taken but not the factors that argued the other way, which loses the negative contributions the vision explicitly displays. C has no labelled data, no explanation, and nothing to tune against. D is the architecture the vision exists to reject.
- **The ledger is the arithmetic.** A HIGH attention result carries the codes that produced it and their signs — for example `AUTHORITATIVE_DISCLOSURE +`, `ABNORMAL_PRICE_MOVE +`, `INDEPENDENT_CORROBORATION +`, `SECTOR_WIDE_MOVE −`, `LOW_SOURCE_COVERAGE −`. The particular numbers are not the point and live in configuration, not scattered through application code. The property that matters is that **"why did this receive HIGH attention?" is answered with the same information that produced the decision** — never with a ranking computed one way and an explanation invented afterwards by a model.
- **Mechanism and calibration are separate concerns, and only the mechanism is claimed to be right.** The defensible position is not *"HIGH means a score at or above 72 because 72 is correct"* — no such number exists without historical evaluation and user-outcome data neither we nor anyone at this stage has. It is: *the architecture separates scoring from calibration; thresholds are versioned configuration, calibrated against explicit scenarios; production calibration would require data we do not have.*
- **Calibration is regression-tested, not asserted.** A fixture set of roughly 20–30 labelled situations beyond the eight demo scenarios — each with an expected verdict (`SUPPRESS` / `LOW` / `MEDIUM` / `HIGH`), the reason codes expected to fire, and the expected relationship between attention and confidence. A threshold or weight change runs against the set, and what moved is visible. This is what makes "hand-tuned" a defensible engineering position rather than a flimsy one: the numbers are judgement, but a change to them cannot silently break twenty other cases.
- **Consequences:** Thresholds need hand-tuning and will be argued about — a real, accepted cost (VISION §18). Scoring configuration is versioned so a historical decision can be interpreted against the rules in force when it was made, rather than against today's weights. The fixture set must be maintained alongside the reason-code vocabulary. The LLM may phrase the ledger for humans; it may not alter a reason code or a score. The engine is fully testable without any UI, model or network.

### D5 — LLM behind a provider-neutral seam, in a bounded role

- **Options:** **A** — a small internal interface with one Claude adapter. **B (simplest)** — call the provider SDK directly wherever needed. **C** — a general multi-provider abstraction layer.
- **Chose:** A. B scatters a volatile dependency through the domain; C builds a framework for vendors we do not have. The abstraction exists for **dependency isolation, not vendor neutrality** — that distinction keeps it one interface rather than a plugin system.
- **Bounded role.** The LLM may extract structured events from text, resolve entities where matching fails, classify events, propose company relationships, and phrase explanations from reason codes. It may **not** own prices, calculations, timestamps, freshness, provenance, checkpoints, lifecycle persistence, access control, data integrity, or any causal claim. Every extraction retains evidence ids, extraction time, model, prompt version, schema version and validation state. **The system never creates a market fact because a model produced one.**
- **Failure behaviour:** unavailable, rate-limited, slow or malformed output degrades rather than corrupts. Existing valid summaries continue to display with their own freshness. New evidence that cannot be safely interpreted is marked **pending evaluation** — never fabricated, never silently dropped. Basic watchlist and market function survive a total LLM outage.
- **Consequences:** an interface to maintain, and a validation layer between model output and the domain. Structured extraction must be schema-validated before it is allowed in, which is where malformed output is caught rather than propagated.

*D25 supersedes D5's initial choice of Claude as the sole adapter. It does not change
the seam or the model's bounded role.*

### D6 — Summaries precomputed and persisted, never generated per page view

- **Options:** **A** — generate at evaluation time, persist with provenance, serve to all readers. **B (simplest)** — generate on request.
- **Chose:** A. B multiplies cost by readers, puts model latency in the page load, makes two users see differently-worded accounts of the same event, and makes an outage a page failure instead of a staleness note.
- **Consequences:** summaries need invalidation when their underlying events change — persisted with source event ids, generation time, model and prompt version, and validity state precisely so they can be regenerated deliberately. User-specific phrasing, where the checkpoint materially changes the content, is derived separately and kept small.

### D7 — Explicit "Mark review complete", with a snapshotted review boundary

- **Options:** **A** — explicit completion. **B** — dwell-based auto-advance. **C** — hybrid with an override.
- **Chose:** A, resolving the question VISION §7 left to design. Dwell infers understanding from time on page, which is false for a user who opened a tab and walked away, lost connectivity, or refreshed. Any threshold is arbitrary and would have to be defended. Explicit completion is deterministic, testable, accessible and cross-device safe.
- **Session-level, not event-level.** No per-event "mark as read". The checkpoint means *"I finished reviewing what was available"*, not *"I read every item."* The product is not an inbox, and the UI language stays "Mark review complete", never "Mark all as read".
- **Consequences:** one deliberate click per review — accepted, in exchange for precise semantics and no inference about whether information was seen. It also makes the review boundary (see *State*) necessary: without a snapshotted cutoff, events arriving mid-read would be silently acknowledged.

### D8 — Email and password with server-side sessions

- **Options:** **A** — email/password, hashed with an established algorithm, server-side sessions, secure cookies. **B (simplest)** — an opaque watchlist code, no password. **C** — no auth; single demo user.
- **Chose:** A. Cross-device persistence is explicitly judged, and C makes the most important property of the system — per-user information state — untestable with two people. B works but reads as avoiding the requirement. No OAuth, social login, MFA, passwordless or federation: **authentication is infrastructure supporting the product, not the product.**
- **Consequences:** passwords are never stored in plaintext and no cryptography is hand-rolled; session identifiers are unpredictable and validated server-side. Authorization is enforced at the backend boundary, never by hiding frontend elements. The originality budget goes to the engine, not to identity.

### D9 — One role, with authorization at the domain boundary

- **Options:** **A** — a single retail-investor role, ownership checks in the domain layer. **B** — a general RBAC framework now.
- **Chose:** A. There is exactly one genuine user role. Inventing admin or analyst roles to demonstrate RBAC would be building for a journey nobody has.
- **Consequences:** enforcing authorization at the domain boundary rather than per-endpoint means a second role can be introduced where a real journey requires it, without relocating checks. No role tables, no permission matrices, no policy engine until then.

### D10 — SQLite, with a stated migration trigger

- **Options:** **A** — SQLite behind a repository boundary. **B** — Postgres in a container now.
- **Chose:** A. Fifty curated companies, a small user count, limited ingestion concurrency, read-dominated access, zero setup, and a demo that reproduces from a file. B adds a moving part and gains no capability at this scale.
- **Consequences — stated rather than wished away.** SQLite's write concurrency is limited, so: few concurrent writers, short transactions, no transaction held open across an external or model call, expensive work done before the commit, WAL mode, and background writes serialized where needed. **No Redis, queue broker or distributed lock is introduced to solve a scale problem we do not have.** Domain logic sits behind repository interfaces — a normal query layer with clean boundaries, not a portability framework.
- **Migration trigger, explicitly:** sustained concurrent writes from multiple ingestion workers; multiple application instances sharing a datastore; measurable lock contention; throughput beyond SQLite's comfort; an operational requirement for a networked database; or a deployment topology where a local file is unsuitable. **"The project got more serious" is not a trigger.**

### D11 — Curated ~50 with full coverage, plus an honest limited-coverage tail

- **Options:** **A** — curated NIFTY 50 with full context, other supported NSE securities in limited-coverage mode. **B (simplest)** — curated set only; refuse everything else. **C** — any ticker, context generated by a model.
- **Chose:** A. Relevance is only as good as company context (VISION §8), and curated context for fifty names is a day's work that makes every relevance judgement defensible. C produces unverifiable context at exactly the point the vision demands provenance. B is cleaner but tells users their holdings are unsupported rather than telling them what it can and cannot see.
- **Consequences:** two coverage tiers to build, display and explain — the cost of A over B. Full coverage gets market behaviour, news, filings, competitor and sector context, selected global exposure, commodity and currency exposure, and lifecycle. Limited coverage gets price, volume and matched company news, and **says so on the company, in the review, and in every verdict about it.** A limited-coverage quiet company is a weaker claim than a full-coverage quiet one, and the UI must not present them identically.

### D12 — Event identity by bucketed candidate generation and conservative linking

- **Options:** **A** — a deterministic key *as identity*: same company, event type and date is the same event. **B (simplest)** — source-native ids only; every publisher's article is its own event. **C** — bucket on (company, event type, temporal window) to *generate candidates*, then decide by structured-attribute comparison and bounded lexical similarity, with three possible outcomes. **D** — embedding-based semantic clustering.
- **Chose:** C. B is the aggregator failure mode the vision names explicitly — repetition masquerading as corroboration. D is a better answer to a problem this size does not have, and it makes merges unexplainable; a merge the system cannot justify is as bad as a ranking it cannot justify. **A was the earlier choice in this document and is wrong**: it makes the bucket the identity, so two Tata Motors contracts announced on the same day become one event by construction, with no evidence that they are related.
- **The key generates candidates; it does not confer identity.** `(company, event_type, temporal_window)` narrows the search. The decision then compares structured attributes — counterparty, geography, product or project, regulator, facility, contract value, commodity, affected business unit, and whatever else the event type carries — before falling back to bounded lexical similarity on the description.
- **Three outcomes, not two.** `LINK` to an existing event, `CREATE_NEW`, or **`AMBIGUOUS`**.
- **`AMBIGUOUS` holds the merge, not the event.** Both events stay separate and both stay visible; what is withheld is the *claim that they are the same story*, recorded as a possible relationship between them:

  ```
  Event A ─┐
           ├── possible_relationship (AMBIGUOUS)
  Event B ─┘
  ```

  Surfaced to the user as *"possibly related to an earlier event; relationship not yet confirmed."* This is the conservative principle applied correctly: **uncertainty reduces what the system claims, it does not suppress evidence.** Withholding an event until identity resolves would hide potentially important information for an internal bookkeeping reason — the opposite of what the vision asks for. Should later evidence resolve the relationship, the pair can be linked then; the possible-relationship record is what makes that reconciliation possible rather than lost.
- **The governing principle:** **false merges are more damaging than temporary duplicates.** A duplicate can be reconciled later, and its cost is a slightly noisier review. A false merge corrupts lifecycle state, evidence provenance, corroboration counts, attention scoring, resolution detection and the user's understanding of what actually happened — and it does so invisibly, because the merged event looks perfectly coherent. Linking therefore prefers `CREATE_NEW` or `AMBIGUOUS` whenever the structured evidence is insufficient.
- **Consequences:** the system will show occasional duplicates — accepted, deliberately, as the cheaper error. One supply-chain disruption reported by several publishers over several days still converges into one evolving event, because those reports share counterparty, facility and geography; two same-day contracts with different counterparties stay separate, because they do not. Conservative linking also means resolution evidence occasionally fails to attach to the event it resolves, which surfaces as STALE rather than a false RESOLVED (D16) — the honest failure again. The LLM may propose that two candidates match; it never decides. Identity stays deterministic and inspectable. Embedding-based clustering remains a possible future improvement, not an MVP dependency.
- **Stated plainly: event identity across messy real-world reporting is inherently imperfect.** No threshold makes it correct. The design chooses which direction to be wrong in and makes both directions visible in the evidence list.

### D13 — Corroboration by publisher independence, not article count

- **Options:** **A** — assess independence at publisher level, collapsing known wire syndication to a single source. **B (simplest)** — count articles.
- **Chose:** A. Ten outlets running one agency's copy is one source. B would let syndication manufacture confidence, which corrupts the confidence axis the entire trust story rests on (VISION §12).
- **The distinction that matters:** `article_count` and `independent_source_count` are different quantities, and only the second one is evidence. The system tracks both and scores on the second.
- **Consequences:** a bounded syndication and source-family mapping — small, maintained by hand, and honest about being a heuristic. **Syndication detection will be incomplete**, so an unlisted wire relationship will occasionally inflate the independent count. Corroboration is therefore *evidence about independent reporting*, not a measurement of truth, and the design says so rather than implying precision it does not have. No general media-provenance graph is built for this. Confidence is computed from the highest source tier present plus independent corroboration count, and is reported **separately from attention**, because "possibly significant, uncertain" and "modest, certain" are different answers that a single number would destroy.

### D14 — Unusual measured against the security's own baseline

- **Options:** **A** — trailing per-security distribution of returns and volume, plus sector-relative residual. **B (simplest)** — fixed percentage thresholds.
- **Chose:** A. A 3% move is routine for one security and extraordinary for another; B encodes exactly the magnitude-equals-meaning error VISION §5 rejects.
- **Ordering is part of the decision, not an implementation detail.** Corporate-action adjustment → normalized market observation → security baseline comparison → sector/index residual → meaningfulness contribution. Adjustment must precede anomaly evaluation; an unadjusted bonus issue evaluated against a baseline reads as a collapse (S3), and no downstream cleverness recovers from that.
- **Consequences:** a warm-up period before a newly added security has a baseline, during which movement claims are weaker and must say so. Sector residuals mean broad market movement is not silently attributed to the company — reported as context, never as cause (VISION §13).

### D15 — Coverage as first-class output

- **Options:** **A** — every ingestion run writes a coverage record; verdicts read the coverage of the sources they depend on. **B (simplest)** — log failures and evaluate whatever arrived.
- **Chose:** A. Under B the system cannot distinguish "nothing happened" from "we could not look," which is the failure VISION §14 identifies as fatal to the whole proposition — if silence might mean blindness, the user must check manually anyway and the product has no value.
- **Coverage is a domain-level input and output of evaluation, not observability.** It is passed into `assess` and it constrains what `assess` is permitted to conclude. Logging records what the system did; coverage changes what the system is allowed to say.
- **The two verdicts are structurally different.** All source families healthy → `NO_MEANINGFUL_CHANGE` is defensible. Price healthy, news stale, disclosure unavailable → the honest verdict is `UNABLE_TO_EVALUATE_RELIABLY`, per company, naming what was missing.
- **Three states, three sentences.** The wording is part of the product model, not copy, and is fixed here:

  | State | What the user is told |
  |---|---|
  | Full coverage, quiet | *"No meaningful change detected since your last review."* |
  | Limited coverage, quiet | *"No meaningful change detected in the sources currently available to us. Coverage for this company is limited."* |
  | Insufficient coverage | *"We don't currently have enough reliable coverage to determine whether anything meaningful changed."* |

  The first is a conclusion. The second is a conclusion with a stated boundary. The third is an admission. Rendering any two of them alike would collapse the distinction the entire trust proposition rests on.
- **Consequences:** coverage is assessed across source availability, freshness, ingestion success or failure, which source families were expected for that company's tier, degraded adapters, and absence of authoritative evidence. **Confidence is never manufactured from missing data** — an absent source lowers what can be claimed rather than leaving the claim unchanged. Freshness is tracked per source, not per page, because prices can be current while news is six hours stale.

### D16 — Lifecycle kept, with bounded linking and a default to STALE

- **Options:** **A** — full state set, bounded heuristic linking, decay to STALE without positive resolution evidence. **B** — detection only; no lifecycle. **C** — general semantic event-resolution.
- **Chose:** A. Lifecycle is the most original thing in the vision and the hardest correctness problem in the build; B removes the differentiator, C is not a two-day problem.
- **Decay policy belongs to event semantics, not to a global constant.** A rumour, a contract, a supply disruption, a regulatory action and an acquisition have completely different natural lifetimes; one timeout applied to all of them is wrong for nearly all of them. `stale_after` is therefore a per-event-type value in versioned configuration — short for rumours, medium for contracts and supply disruptions, long for regulatory actions and M&A. **The durations are not worth agonising over during the build; the architectural decision is that they are event-type-scoped and configurable rather than a magic number in code.**
- **A timeout produces `STALE`. It never produces `RESOLVED`.** No elapsed duration, for any event type, is evidence that a situation concluded.
- **Consequences:** linking is heuristic and will miss resolutions — accepted, because the honest failure (STALE) is acceptable and the dishonest one (RESOLVED without evidence) is not. Optimising for a few convincing, correct lifecycle examples beats broad, unreliable coverage.

### D17 — Build-time search index over shared intelligence only

- **Options:** **A** — generate a static index at build time from shared intelligence; private state excluded by construction. **B (simplest)** — client-side filtering of loaded data. **C** — a search service.
- **Chose:** A. B does not span companies and events the user has not loaded; C is infrastructure for a corpus of this size. Building the index only from shared intelligence makes the privacy property structural rather than a filter someone must remember to apply.
- **Indexed:** companies, normalized events, public evidence metadata, company context, persisted shared summaries, shared event timelines. **Never indexed:** accounts, watchlists, review checkpoints, acknowledgement state, private preferences, session information.
- **Consequences:** the index is as fresh as the last build, which must be stated where it matters. Privacy is structural — the index is built from the shared store, so there is no runtime filter a developer can forget. If private search is ever needed it is a separate authenticated mechanism, never a relaxation of this one.

### D18 — Live pipeline and seeded fixtures through one domain model

- **Options:** **A** — background ingestion is real, and a deterministic seeded fixture set enters through the same normalization, evaluation and persistence path. **B (simplest)** — live only: whatever the sources give us on the day. **C** — a demo mode with hardcoded verdicts in the UI.
- **Chose:** A. B makes the demonstration depend on Wi-Fi, NSE availability, news feeds, model availability, rate limits and provider latency — six things that can fail while someone is watching. C is worse than a failed demo: a UI with hardcoded verdicts demonstrates nothing about the system and misrepresents it.
- **The constraint that makes A honest:** seeded evidence enters at the *evidence* boundary and travels the same normalization → identity → evaluation → lifecycle → summary → persistence path as live data. **No fixture writes an assessment directly.** If a seeded scenario produces the wrong attention level, that is a real engine bug and must be fixed in the engine.
- **Consequences:** fixtures must be maintained as the evidence model changes — a real cost, and the reason they are evidence-shaped rather than verdict-shaped. In exchange the demo is deterministic and reproducible, the seeded path is a genuine integration test of the whole pipeline, and a known-good database snapshot can be restored between runs. Background ingestion still genuinely exists (D3); the fixtures are insurance, not a substitute.

### D19 — Depth over breadth in what the demo exercises

- **Options:** **A** — a small set of companies exercising every capability end to end. **B** — all fifty curated companies at whatever depth time allows.
- **Chose:** A. The architecture supports the curated universe (D11), but the demonstration does not need every company to exercise every capability. Five to ten companies with genuine event identity, provenance, lifecycle, scoring, coverage states and "since last review" behaviour is a stronger showing than fifty companies of price-and-headline cards — which is the obvious watchlist the brief explicitly asks us not to build.
- **Consequences:** curation effort concentrates where it is visible. Companies outside the demo set still work; they simply may not have a scenario that exercises lifecycle or resolution. This is a demo-scope decision, not an architectural limit, and the distinction should be stated when presenting rather than glossed.

---

*D20–D23 were appended after their respective implementation steps exposed boundaries
the original design left unresolved. D24–D25 were appended from the Step 2 handoff.
Only D25 supersedes an earlier implementation choice: the provider named in D5.*

### D20 — Run-level coverage is independent of assessments

- **Decision:** Coverage and fetch health are persisted for an ingestion run independently of whether that run produced any evidence, events or assessments. An empty or failed source run is itself meaningful system state.
- **Why:** This is what preserves the distinction between `NO_MEANINGFUL_CHANGE` and `UNABLE_TO_EVALUATE_RELIABLY` (D15, VISION.md §14). A previous successful assessment must never make a later failed ingestion appear healthy. Coverage belongs to the evaluation context, not to individual assessment rows.
- **Options:**
  - **A** — store coverage only on assessments. **Rejected:** a zero-evidence run produces no assessment on which to record the current source state, so the failure leaves no trace at all.
  - **B** — infer source health from the most recent assessment. **Rejected:** an old successful assessment outlives a newer failed ingestion, so stale coverage reads as current — the precise failure this decision exists to prevent.
  - **C** — treat ingestion failure as an operational or logging concern only. **Rejected:** source availability directly changes what product conclusion the system is *allowed* to reach. Logging records what happened; coverage constrains what may be said.
  - **D (chosen)** — persist a run record unconditionally, and derive current source health from the latest run.
- **Consequences:** the API exposes source health as a top-level field rather than something reachable through an assessment, because the case that matters most is the one with no assessments. Absence of a failure record is not evidence of success: a run carrying no coverage record for its own source is treated as unhealthy, not healthy.
- **Found by:** the Step 0 review gate, before Step 0 was accepted.

### D21 — Evidence publisher and subject are distinct

- **Decision:** Evidence explicitly distinguishes the organisation that published it from the company or security it concerns — `publisher = NSE`, `subject_company = Hindalco`; `publisher = Reuters`, `subject_company = Tata Motors`. Normalization and event identity resolve company identity from the subject reference, never from the publisher.
- **Why:** For exchange filings the two coincide, which makes the conflation invisible until a second source type arrives. It is not invisible in consequence: with a news adapter, every event would be attributed to the outlet rather than the company. Disclosure metadata that makes publisher-like fields resemble company identity must not leak into the domain model.
- **Options:**
  - **A** — continue using publisher as company identity. **Rejected:** correct only by accident of the current adapter, and wrong immediately for news and every other source type.
  - **B** — pass company identity separately inside each adapter without representing it in `Evidence`. **Rejected:** the subject is part of evidence semantics and must stay traceable through normalization and provenance, not be reconstructed per adapter.
  - **C (chosen)** — one explicit field on `Evidence`, no more generic than the MVP needs.
- **Consequences:** the distinction exists before the news adapter lands, which is when D12's linking work starts depending on it. No entity-resolution layer is introduced — the field is a name, not a graph.

### D22 — Canonical attention ranking is backend-owned

- **Decision:** The Meaningful Change Engine owns the canonical ordering of assessments. The API returns them in that order and the frontend renders it unchanged by default. Reader-selected presentation sorts — by company, recency, confidence, attention — are a separate concern and belong to the frontend.
- **Why:** Canonical ranking is a product decision about what deserves attention first, and it must be consistent across every client. A view sort is a request from one reader about one screen. Collapsing the two puts a product answer in a place where it can diverge.
- **Options:**
  - **A** — reproduce attention ranking in TypeScript. **Rejected:** two implementations of one piece of product logic, free to drift.
  - **B** — move all ranking to the frontend. **Rejected:** ranking belongs with the engine that produced the assessments and the reason codes behind them; a second client would answer the same question differently.
  - **C (chosen)** — canonical ranking in the backend, view sorts in the frontend, with the boundary stated.
- **Consequences:** sharpens D2's rule that the frontend renders verdicts and never computes one — ordering by verdict is now explicitly part of the verdict. A client that applies no sort must return the received order untouched.

### D23 — A market observation can itself be evidence

- **Decision:** An unusual price move, and a corporate action, each become an `Event` whose evidence is the observation the system computed — `SourceTier.COMPUTED`, the tier the model already declared for "derived by us from primary data". The engine assesses them exactly as it assesses a disclosure.
- **Why:** The original Shape passed `MarketObservation` into `assess` as context *for an event*, which silently assumed every event originates outside the system. Scenario A has no external event by construction — the price moved and nothing was disclosed — so under the original shape it could not be surfaced at all. Making the observation evidence keeps one assessment path, one reason-code ledger and one persistence model rather than a second parallel one.
- **Options:**
  - **A** — a per-security assessment unit alongside the per-event one. **Rejected:** two units of assessment, two review paths, and it pre-empts the per-company review page that step 4 owes the user anyway.
  - **B** — surface unusual moves only when a disclosure exists to attach them to. **Rejected:** that is precisely scenario A, discarded. An unexplained move is a finding, and refusing to report it is the opposite of the intended behaviour.
  - **C (chosen)** — computed evidence, existing event and assessment path.
- **Consequences:** a calm security produces no event at all, which is *not* a verdict of "no meaningful change" — that per-company statement is still owed by the review page in step 4, and the distinction is now written down so it is not mistaken for one. A corporate action produces a note rather than an alarm (scenario G), and an unexplained move produces a `NO_COMPANY_EVENT_DETECTED` reason code rather than a manufactured cause (scenario A).

### D24 — Extraction is evidence-grounded, and partiality narrows claims

- **Decision:** A model extraction is an evidence-derived claim, not an admissible fact merely because it matches a schema. Every material field used for identity, relevance, corroboration, scoring or explanation must remain traceable to the evidence record that supports it. Unsupported values remain explicitly unknown; speculation remains speculation. A valid partial extraction is retained with only its supported fields, while malformed output is rejected before domain use.
- **Why:** D5 bounded the model's role and required schema validation, but left two questions unresolved: whether schema-valid invention could enter the domain, and whether one absent field invalidates everything the article did support. Accepting the whole object trusts the model too much; rejecting the whole object discards real evidence and makes model brittleness look like source absence. VISION §§12–15 require confidence, provenance and causal restraint to survive extraction rather than be reconstructed later.
- **Options:**
  - **A (simplest)** — accept any schema-valid extraction as a complete candidate. **Rejected:** a type-correct counterparty, value, date or causal relationship can still be unsupported, and downstream deterministic logic would then make precise decisions from an invented premise.
  - **B** — reject any extraction containing an unknown or missing material field. **Rejected:** real reporting is routinely incomplete; this would erase supported facts and turn uncertainty into silence.
  - **C (chosen)** — validate structure, preserve supported partial fields and explicit unknowns, retain extraction provenance, and constrain every downstream claim to what the surviving fields support.
- **Acquisition and interpretation are distinct health dimensions.** If news was fetched but extraction is unavailable, the evidence remains stored and news acquisition is not falsely reported as failed. The affected evaluation is nevertheless degraded because the system could not safely interpret that evidence. A failed model call produces neither a fabricated event nor a crash; it produces persisted evidence plus an explicit evaluation gap.
- **Causation follows the same rule.** Temporal proximity may support co-occurrence language — *"during the same period"* or *"may be relevant"* — but never a causal assertion unless the evidence directly establishes it. The model may render this distinction; it may not promote correlation into cause.
- **Consequences:** extraction provenance includes the evidence references and the model, prompt, schema and extraction versions needed to reproduce or invalidate the result. Downstream modules must tolerate partial candidates and explicit unknowns. The system can show less when evidence is incomplete, but it cannot silently fill the gaps. Exact text-span annotation and a general claim graph are not required for this version; traceability to the supporting evidence record is the deliberately smaller contract.

### D25 — Gemini is the initial model-backed extractor

- **Decision:** Use the Gemini Developer API as the single active model-backed extractor for Step 2, with `gemini-3.6-flash` as the initial working model. The model revision is deployment configuration rather than a domain contract, because availability can change independently of the extraction boundary. The rule extractor remains the deterministic fallback and evaluation baseline. This is a provider replacement behind D5's existing seam, not multi-provider orchestration.
- **Correction after live validation:** D25 originally named Gemini 2.5 Flash. Although the provider listed that model, `generateContent` returned 404 and identified it as unavailable to new users. The provider's named replacement, Gemini 3.6 Flash, completed real extraction calls. This corrects the model selection without changing the Gemini provider decision or any downstream contract.
- **Why:** The Claude adapter could be exercised only through stubbed transports because no Anthropic credential was available, leaving the real model path unvalidated. Gemini offers a free developer tier and schema-constrained structured output, which covers the current extraction requirement without weakening D24's grounding gate or adding a paid dependency. The requirement bends to the available provider because provider identity is not core to the product; evidence-grounded extraction is.
- **Options:**
  - **A (simplest)** — use the rule extractor alone. **Rejected:** it is precise and deterministic but currently misses too much real reporting, and it does not validate the model-assisted extraction boundary the design explicitly chose.
  - **B** — keep Claude as the initial provider and wait for an Anthropic credential. **Rejected:** it leaves the only unresolved Step 2 acceptance path blocked for a provider choice the architecture intentionally made replaceable.
  - **C (chosen)** — use Gemini's free tier behind the existing interface and retain the grounding gate and rule fallback.
  - **D** — add OpenRouter, Groq or several providers with automatic routing. **Rejected:** this introduces provider-selection and failure-ordering machinery that the current product does not need; D5 deliberately chose isolation rather than a provider framework.
- **Data boundary:** Free-tier Gemini usage may permit prompts and responses to be used to improve Google's products. Only public news evidence and the extraction schema may cross this boundary. User state, watchlists, sessions, credentials and other private data do not. If that restriction cannot be maintained, the free tier is not an acceptable deployment choice.
- **Failure behaviour:** Quota exhaustion, rate limiting, provider errors and malformed output follow D5 and D24: evidence remains stored, the rule fallback may produce a separately-provenanced partial result, and affected evaluation health degrades visibly. Fallback output must never be represented as Gemini output.
- **Consequences:** Gemini availability and free-tier limits are operational dependencies, not correctness dependencies. Model, prompt, schema, grounding and fallback provenance remain persisted so Gemini results can be evaluated against the same article set and replaced later by changing only the adapter. The active provider decision should be revisited before handling non-public evidence or moving beyond demonstration-scale traffic. See the [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing) and [structured-output](https://ai.google.dev/gemini-api/docs/structured-output) contracts.

### D26 — Canonical order is severity, then recency

- **Decision:** Assessments are ordered by attention level first and, within a level, by when the development occurred, newest first. Score is no longer a tiebreaker and is not exposed as ordering.
- **Why:** Two HIGH items ordered by score look ranked against each other, and the product does not claim that precision — the level is the claim, the score is the mechanism that produced it (D4). Recency is a fact the reader can check, and it answers the question a board is actually asked: *of the things that matter equally, what happened most recently?*
- **Occurred, not learned.** The review *window* is measured by when the system learned something, because a late-arriving event is still new to the user. Ordering is measured by when it happened, because that is what "newer" means to a reader looking at a list. The two use different clocks deliberately, and both remain distinct fields.
- **Options:**
  - **A** — severity, then score, then symbol (the current behaviour). **Rejected:** implies a ranking between two items of the same level that the product does not stand behind.
  - **B** — severity, then when we learned it. **Rejected:** a backfilled week-old item would head the list purely because ingestion was late, which reads as wrong to anyone who checks the date.
  - **C (chosen)** — severity, then occurrence, newest first; symbol only to break exact ties.
- **Consequences:** ordering becomes explicable in one sentence to a user, which score never was. A backfilled older event sorts below today's, and is still surfaced because the *window* placed it there — surfacing and ordering stay separate questions.

### D27 — Interests filter and annotate; they never score

- **Decision:** When adding a company a user may record why they follow it, what they want to watch for, and optional tags (earnings, management, regulation, competitors, contracts, commodities, dividends, unusual price movement). These interests may **filter** what is shown and **annotate** why an item matches. They never change an attention level, a confidence level, a corroboration count or the canonical order.
- **Why:** the product's central claim is that a verdict follows from evidence. An interest is a hypothesis about what will matter; evidence is what did. If interests moved the score, two users watching one company would see different severities for the same event — shared intelligence would stop being shared (DESIGN *State*), the word "attention" would come to mean "preference", and D22's guarantee that ranking is consistent across clients would be gone.
- **When focus and severity disagree, severity wins and the disagreement is shown.** A focus filter narrows LOW and MEDIUM. **It never hides a HIGH.** A HIGH outside the user's stated focus is shown with a marker saying so — *"outside your focus; we think it matters anyway."* Hiding it would be the product failing at the one job it claims, in the name of a preference the user expressed before the evidence existed.
- **The match explanation is deterministic.** An item is marked as matching a tag when its event type maps to that tag, or when its extracted structured fields (regulator, counterparty, commodity, product) contain a term the tag covers. The mapping is curated and inspectable, like the alias sets in D21 — never inferred per-user, never model-decided. An unmatched item is not annotated rather than being annotated with a guess.
- **Options:**
  - **A** — interests contribute a reason code and shift the score. **Rejected** for the reasons above; it also makes the reason ledger (D4) partly about the reader rather than about the evidence.
  - **B** — interests reorder within a severity level. **Rejected:** it contradicts D26's stated tiebreaker and quietly makes the order per-user, which is the same problem in a smaller package.
  - **C (chosen)** — filter and annotate only, both visible and both reversible in one click.
- **Consequences:** interests live entirely in private user state and never touch the shared assessment record. The free-text answers are stored for the user's own reference and to inform later curation of the tag vocabulary; they are not parsed into behaviour. Two users with opposite interests still see the same severities, which is what lets one analysis serve both.

### D28 — Price context is end-of-day, aligned on common sessions, and rebased

- **Decision:** Company, sector-index and broad-index series are drawn from **daily, corporate-action-adjusted end-of-day bars** — the same bars the engine already observes (D14). A chart offers selectable ranges over those bars. It is labelled end-of-day and never presented as live.
- **Source:** `yfinance` for NSE equities and the NSE index family, which is what the market adapter already uses. It is unofficial and best-effort, and that is acceptable for context but not for a claim: a chart is illustrative, an assessment is not. A licensed feed (a broker API such as Kite Connect, or a commercial vendor) is what intraday or redistribution would require, and neither is in scope here.
- **Alignment is the substantive part.** All three series are restricted to the **intersection of trading sessions** present in every one of them across the requested range, then **rebased to 100 at the first common session** so they are comparable as relative return rather than as price. A session missing from any series is dropped from all of them; nothing is interpolated or forward-filled. Where the common span is shorter than the range asked for — a holiday, a suspension, an index with less history — the chart shows the span actually covered and says so.
- **Why this specifically:** comparing a company's session to an index's session of a different date is not a subtle error, it is a wrong number that looks precise. Step 1 shipped exactly that bug in the sector residual and it was caught only by testing a halted security. The rule is the same one, generalised and stated once.
- **A benchmark that has stopped is excluded and named, not intersected away.** Implementation exposed the case: two of the NSE sector indices the price feed serves stopped updating months before the securities did. Intersecting a stale benchmark would cut the company's own chart back to that benchmark's last session and present the result as the range the reader asked for. So a series missing more than a couple of the security's *most recent* sessions is dropped from the comparison with a note saying why, while the intersection continues to handle ordinary gaps. Measured at the end of the series rather than across it, because a benchmark that skipped a day in March has gaps and a benchmark whose last session is months old has stopped.
- **Every range is measured in sessions.** "1D" is the latest stored session against the one before it, not a day of intraday ticks. The range control and the basis line under the chart both say so, because a range labelled 1D without that would imply a feed this product deliberately does not have.
- **Where a chart may appear:** inside a company's detail, never on the board. A price chart on the main surface would make price the subject, and the product's whole argument is that price is one signal among several and often the slowest (VISION §5).
- **Consequences:** intraday movement, gap analysis and volume overlays are all out of reach without a different feed, and are named as such rather than approximated. The chart adds no new fabrication risk because it renders only bars already ingested.

### D29 — Contradiction is a deterministic link, and the model may only propose it

- **Decision:** An event carries a contradiction state — `STANDING`, `DISPUTED` or `WITHDRAWN` — and a `disputed_by` link to the later record that disputes it. Both records stay visible and linked; neither is deleted.
- **The state is set only when every deterministic gate passes:** the two events resolve to the same company and the same identity bucket (D12); the disputing evidence is **at least as authoritative** as the disputed, by the tier ordering in VISION §12, so a forum post can never dispute a filing; the disputing evidence is later by publication time; and the contradiction terms are grounded in the disputing source under D24's gate. `WITHDRAWN` requires the narrower signal of the source itself correcting or retracting.
- **The model's role is bounded to proposing.** An extractor may return a structured claim that B disputes A, with the evidence it relied on. It never sets the state. A proposal that fails any gate is recorded as a possible relationship — the same treatment D12 gives an `AMBIGUOUS` link — and is shown as *"possibly related; relationship not confirmed"*, never as contradicted.
- **What may propose is broader than the model; what may decide is not.** The first proposer built is a curated cue vocabulary — the language a denial or a retraction is actually written in — because it is deterministic, inspectable and needs no model call. A model proposal enters the same gates and gets no additional standing. Neither proposer decides anything.
- **A grounded denial holds the merge.** Implementation exposed this: a denial reads like the story it denies — same company, same event type, much of the same wording — so D12's linking merged it into that story and the disagreement disappeared inside the record of the claim. A proposal therefore blocks a LINK outcome, and the denial becomes its own event. This is the same trade D12 already makes: a duplicate is survivable, a false merge is not.
- **A dispute lowers confidence, not attention.** A contested report may still be the most significant thing about a company; what changed is how sure we are. Collapsing the two axes here would undo the separation the product holds everywhere else.
- **Options:**
  - **A** — let the model judge contradiction directly. **Rejected:** it makes the model the source of truth for a claim about the world, which D5 forbids, and an unexplainable contradiction is worse than none.
  - **B** — infer contradiction from sentiment or polarity. **Rejected:** unexplainable and reliably wrong on financial prose.
  - **C (chosen)** — deterministic gates over structured attributes and source tiers, with the model proposing candidates.
- **Consequences:** contradiction detection will have low recall — most corrections are quiet and many disputes are never explicit. That is the same trade the lifecycle work takes in D16, and for the same reason: a false contradiction destroys trust in every verdict beside it, while a missed one leaves the record merely incomplete. This is a narrow slice of D16 and does not implement the rest of the lifecycle.

### D30 — One API serves web and mobile; sessions are presented two ways

- **Decision:** Web and a later mobile app are two clients of the same HTTP API. Authentication, watchlists and interests, review assembly and completion, company detail, the supported universe and chart series are all shared. There is no mobile-specific backend.
- **Sessions:** the server-side session record from D8 stays the single model of identity. The web presents its identifier as an HttpOnly cookie; a mobile client presents the same identifier as a bearer token. One session table, one expiry, one revocation path, two transports. A second authentication system would be a second place for authorization to be wrong.
- **What differs is payload shape, not contract.** The review response currently embeds every assessment in full, which suits a web page and is wasteful on a phone. The honest position is that the current shape is web-shaped; a compact projection is the change mobile will need, and it is an addition rather than a fork.
- **Consequences:** every authorization rule is written once. Mobile inherits the review-window semantics (D7) exactly, including the frozen cutoff and monotonic completion, which is the part most likely to be got wrong in a second implementation.

### D31 — The LLM harness measures; it never writes to the domain

- **Decision:** A harness runs a fixed article set through one or more providers and records what happened. It writes only to its own tables and never to the assessment store. Nothing it produces reaches a user-visible verdict.
- **What it stores per run:** the evidence reference (not a copy of the article), provider, model, prompt version, schema version, the **raw model output verbatim**, the validated extraction after the grounding gate, which fields were dropped and why, latency, token counts, an estimated cost, a run identifier and timestamp, and the version of the expectation set it was scored against.
- **How outputs are compared:** against the curated expectation set by **deterministic invariants** — correct subject company, no unsupported counterparty or value, correct rejection of non-events, speculation still marked speculative — never by another model judging the first. Provider comparison runs the same set through each provider and reports precision, recall, grounding rejections, unusable responses, latency and cost **per model, never blended**: the Step 2 evaluation had to be assembled from three sibling models because of a daily cap, and reporting that as one figure would have described a model that never ran.
- **What the model still may not own** is unchanged by the harness's existence: rankings, provenance, timestamps, calculations and coverage. The harness measures the extraction boundary and nothing downstream of it.
- **Consequences:** raw output is retained, so a later change to the grounding gate can be re-scored against runs already made without paying for them again. Storage grows with runs rather than with users, and the set is small by design.

### D32 — Scale is a stated path, not a claim

- **Decision:** The design records what has been *tested*, what the shape supports, and the trigger for each next step — and refuses to describe untested capacity as a property of the system.
- **Tested today:** nine curated companies; roughly 400 articles per ingestion cycle; a single process; SQLite; a handful of accounts; twenty model calls per day on a free tier. Nothing beyond that has been run.
- **The property that makes it scale is already true:** the expensive work — ingestion, normalization, identity, corroboration, scoring — is per *company* and shared, while per-*user* work is a window filter over shared rows. Users can therefore grow without multiplying analysis. That is a structural fact about the current code, not a projection.
- **Caching** follows the same split: the ranked shared assessment list is cacheable per source-run generation and shared by every reader; per-user review results are cheap to recompute and are not cached. Caching a per-user review would create a second place for a checkpoint to be wrong.
- **Database evolution:** SQLite until one of D10's stated triggers fires — sustained concurrent writers, multiple application instances, measurable lock contention, or a deployment where a local file is unsuitable. Migrations remain append-only, with every historical version tested to head.
- **Ingestion throughput:** families run sequentially today. The next step is bounded per-company parallelism inside a family; a queue and separate workers come only when one process demonstrably cannot keep up, and that has not been demonstrated.
- **Performance targets:** 10,000 active users, at most 50 watched companies per user, 50 covered securities, up to 500 evidence records every 15 minutes, review assembly p95 below 300 ms, and stored chart transformation below 150 ms.
- **Measured boundary:** the local validation exercises 50 memberships over 500 shared assessments both in memory and through SQLite, 500 rule extractions plus grounding, and 252 aligned chart sessions. The review and chart paths pass their targets. Source HTTP time, model latency, the deployed API, SQLite write contention and a complete 500-evidence ingestion cycle are explicitly outside that result. Peak process memory is reported as a high-water mark. The reproducible numbers live in `docs/validation/scalability.md`.
- **Consequences:** the measurements do not justify Postgres, Redis or a queue. Measure a full ingestion cycle and real database contention next; introduce infrastructure only when the stated trigger is observed.

### D33 — Pydantic/OpenAPI owns the wire contract; TypeScript clients consume a generated version

- **Decision:** all product routes live under `/v1`. Pydantic response models are the source of the JSON wire shape, FastAPI's OpenAPI document is the interchange format, and a committed generated TypeScript module is consumed by both web and mobile. `/health` remains unversioned because it describes the process rather than the product contract.
- **Options:**
  - **A** — maintain TypeScript interfaces independently in each client. **Rejected:** drift is inevitable and had already occurred when the API gained `/v1`.
  - **B** — use untyped JSON at the clients. **Rejected:** it moves contract failures to runtime and makes a second surface unnecessarily risky.
  - **C (chosen)** — generate one private workspace package from OpenAPI and commit the result so builds do not require a running server.
- **Versioning:** additive compatible fields stay in `/v1`; a breaking semantic or structural change requires `/v2`. Generated types share shape and vocabulary, not presentation components or client-side ranking logic.
- **Consequences:** every response route must declare a response model, and regeneration is part of validation. Server-authoritative ranking, coverage, interests and checkpoints cross the boundary verbatim; neither client is allowed to reconstruct them.

### D34 — A watchlist card may show a compact end-of-day price status, not a chart

- **Decision:** the main watchlist may show the latest stored close, its adjusted change from the prior completed session, and a short visual trace of recent stored closes. It is labelled with its session date and unavailable state. The full aligned company-versus-benchmark chart remains only in company detail (D28).
- **Options:**
  - **A** — keep all price context off the board. **Rejected:** the watchlist requirement needs a beginner-readable current price and daily movement before a reader decides whether to open a company.
  - **B** — put the existing comparison chart on every card. **Rejected:** this overturns D28's hierarchy, competes with meaningful developments, and makes a compact board visually noisy.
  - **C (chosen)** — a small stored-data status and sparkline, with the detailed comparison after drill-down.
- **Consequences:** the price summary is an additive `/v1` contract generated from Pydantic, and reports only persisted EOD bars. It does not claim an intraday price, create an assessment, or change canonical news order. Missing or insufficient bars render an explicit unavailable state rather than a synthetic line.

### D35 — The explainer answers from the record; it is not a chat box

- **Decision:** company detail carries an *"Ask about this company"* explainer that answers a **bounded set** of questions from persisted assessments, reason codes, coverage records, stored market observations and cited evidence — the same records the API already serves. It is composed deterministically. **No model participates in the answer path**, no ingestion or external fetch is triggered by a question, and every statement about the company carries the event ids it came from.
- **Why this and not a chatbot:** VISION §17 refuses natural-language querying because *the intelligence must exist in the evaluation, not in a chat box*. That refusal is about where the analysis lives, not about whether a reader may ask a question. Explaining a verdict the engine already reached is the evaluation speaking; answering an open question about a company is a second, ungoverned analysis path — and the second one can be wrong in ways nothing downstream would catch.
- **Advice is refused before anything is looked up.** *"Should I buy"* is not a question with a weak answer; it is one this product does not answer (§6). Resolving intent first means the refusal cannot be softened by whatever the records happen to say — including in a question that wraps advice around something answerable.
- **The window is the reader's, the records are everyone's.** An answer states the evidence window it speaks for and the coverage gaps that bound it, on every response including refusals. A company the reader does not watch is answered from shared intelligence with no personal window claimed, rather than borrowing a checkpoint that was never about it.
- **Every failure state is named**, and `answered: false` is a normal outcome rather than an error: out of scope, unsupported question, nothing on file, nothing on file *about that*, and a price question with no stored observation. Each carries a reason, so a client says *why* instead of showing an empty box.
- **Options:**
  - **A (chosen)** — deterministic intent routing over a curated pattern set, answers composed from stored rows, every statement cited.
  - **B** — the same deterministic evidence packet, phrased by a model, with the D24 grounding gate dropping any sentence whose values are absent from the packet. **Rejected for now:** it puts a model in the *answer* path rather than the extraction path, adds latency to a user request, makes the output non-deterministic so tests can only assert invariants, and spends the model quota the harness already shows is the binding constraint on extraction. A plausible ungrounded sentence surviving a gate is a worse failure here than a missing answer.
  - **C** — open natural-language querying across the whole watchlist. **Rejected:** explicitly out of scope (§17), and the failure mode is an unsupported market claim stated in the product's own voice.
- **B stays cheap to reach.** The packet is already built deterministically, statements already carry citations, and `generated_by` records which path produced an answer — so a model-phrased variant is an adapter behind the same contract, evaluable through the existing harness, and never confused with this one.
- **Consequences:** the explainer cannot answer an unusual phrasing, and says so with suggestions rather than guessing. The intent vocabulary is curated and will need extending, which is the same trade D27 makes for focus tags: a match that cannot be explained is not worth having. Per-company reads are bounded (50 newest), because a company accumulates evidence without limit.
### D36 — Source standing is a third axis; market reaction nudges attention, it never decides it

- **Decision:** every assessment carries a **source standing** — `OFFICIAL`, `ESTABLISHED`, `SYNDICATED_RELEASE`, `UNRECOGNISED`, `COMPUTED` — derived deterministically from the evidence tier and a curated publisher registry, and shown as its own badge beside attention and confidence. Separately, two new reason codes let observed market behaviour and source standing move a news item's attention: `NO_MARKET_REACTION` (−1) and `UNRECOGNISED_PUBLISHER_ONLY` (−1).
- **Why a third axis at all:** attention answers *does this matter*, confidence answers *how sure are we*, and neither answers *what kind of thing said it*. A reader deciding whether to open a story wants the third one first, and today it is only recoverable by expanding the evidence list and recognising the publisher yourself. Live data made the case: 77 distinct publishers in one window, ranging from the NSE to aggregators nobody has heard of.
- **Not "verified".** We verify nothing about a publisher. `UNRECOGNISED` means *absent from a curated list*, and the reader-facing label says "unrecognised publisher" rather than "unverified" — because the second one is a claim about the outlet and the first is a claim about us. Press-release wires get their own state rather than being folded into either neighbour: a release is the company's own words carried verbatim, which is closer to a primary source than an aggregator and further from journalism than a newsroom.
- **The market-reaction code is the dangerous half, and is deliberately weak.** VISION §5 holds that magnitude is not meaningfulness and that price is often the *slowest* signal; §13 refuses causation outright. Scoring news by whether the price moved would invert both. So: the code fires only where we **actually observed** the market (a market we did not consult produces `NO_MARKET_OBSERVATION`, never an inference from silence), it is worded as an observation about the market rather than a judgement about the report, and at −1 it cannot move an item more than one level or push anything to `NO_MEANINGFUL_CHANGE` on its own.
- **Standing is expressed in the ledger exactly once.** The badge is display; `UNRECOGNISED_PUBLISHER_ONLY` is the scored expression of the same registry, and it fires only when *every* news publisher behind an event is outside the list. One independent recognised publisher clears it, and three unrecognised publishers still reach the reader through `INDEPENDENT_CORROBORATION` — the corroboration model (D13) promotes a real story broken outside our list, rather than the registry silencing it.
- **Options:**
  - **A** — score news by observed price reaction. **Rejected:** it asserts causation between a headline and a move (§13) and makes the product a price dashboard with extra steps.
  - **B** — make source standing a scoring input in proportion to tier. **Rejected:** confidence already reads tier, and a second reading of the same fact double-counts it.
  - **C (chosen)** — standing as a display axis, with a single bounded reason code for the one case the registry genuinely speaks to, plus a symmetric market-observation code.
- **Consequences:** `SCORING_VERSION` moves to `2026-09-06.a`; assessments stored under the previous version keep it, which is what the version is for. The registry is curated and certainly incomplete, so it will mislabel outlets we have not catalogued — the label is descriptive for exactly that reason. An important development that the market has not yet priced is nudged down by one point, which is a real cost accepted deliberately against the noise it removes.
### D37 — A watch point is the reader's bookmark, settled on stored closes and never pushed

- **Decision:** a reader may mark a **price level** on a company with a note in their own words. The level is settled during the scheduled ingestion cycle against **stored end-of-day closes**, and a crossing surfaces on the board and in the review the next time they look. Watch points are private user state: they never become assessments, never change an attention level, and are never visible to another reader.
- **Why this is not the notification stream §17 refuses:** it is pull-based. Nothing is pushed to a device, no digest is sent, and a reached level waits at the top of the brief rather than interrupting. The reader chose the level and chose when to look; the product does not acquire a channel into their day.
- **Why it is not advice or a forecast:** the level is the reader's claim, not ours. We do not suggest one, evaluate whether it is sensible, or say anything about what the price will do. A watch point is a bookmark that happens to be numeric.
- **Direction is inferred once and frozen.** A level above the last stored close is a rise to wait for; below it, a fall. Re-deriving that later would flip the point's meaning as the price moved — "tell me if it falls to 1,300" would silently become "tell me if it rises to 1,300" the moment it fell.
- **A level already reached is refused, not created.** An alert that fires the instant you set it teaches you to ignore it, and the reader almost certainly meant a different number. The refusal names the last stored close so they can pick again.
- **End of day, never intraday.** The trigger says *"closed at ₹1,405 on 2026-09-08"* — a session and a number we hold — rather than "hit ₹1,400", which would claim a tick we never observed. This is the same restraint D28 applies to charts.
- **It announces once.** `mark_triggered` updates only where `triggered_on IS NULL`, so re-running a cycle over the same bars changes nothing. Acknowledging is separate from deleting: the record of a level that was reached survives being dismissed.
- **Options:**
  - **A** — evaluate on read, when a page loads. **Rejected:** a reached level would then depend on someone looking, and it would put the evaluation on a request path that D3 and D35 keep free of side effects.
  - **B** — push a notification when a level is crossed. **Rejected:** §17, explicitly.
  - **C (chosen)** — settle unattended during the cycle against bars already stored, and surface the result on the next visit.
- **Consequences:** the granularity is one session — a level crossed and recovered within a day is not seen, which is the honest limit of end-of-day data. Evaluation reads only untriggered points, so the work per cycle shrinks as points fire. Non-price conditions ("watch out for a regulatory ruling") are not supported; the note carries that intent for the reader, and focus tags (D27) are the mechanism if it ever needs to be machine-checked.
### D38 — Watchlist sorting is a presentation axis; it never touches canonical order

- **Decision:** the watchlist may be sorted client-side by biggest gainers, biggest losers, largest absolute move, alphabetically or by recently added, from figures already loaded. The default is unchanged — the attention-led arrangement `buildRows` produces. No request is made to sort, and no other list on any surface is affected.
- **Why this does not contradict D22/D26:** they answer *"which development deserves the reader first"*, and that answer is the backend's alone. This answers *"which company do I want to look at right now"*, which is a question about the reader's attention rather than about evidence. Two different objects, two different questions; conflating them is what D22 forbids, not letting a reader arrange their own list.
- **Missing data sorts last, never as zero.** A company with no stored close is not a flat move, and placing it mid-list would assert that it did not move.
- **Options:**
  - **A** — sort server-side with a `?sort=` parameter. **Rejected:** it spends a request to reorder rows already in hand, and it would make the server appear to have two orderings.
  - **B** — let the sort also reorder developments inside the detail. **Rejected:** that is exactly the canonical order, and it belongs to the engine.
  - **C (chosen)** — a pure client-side sort of loaded rows, offered only on the watchlist view.
- **Consequences:** the control appears only where it does something (the watchlist), alongside the focus filter which appears only on *Needs attention*. Sorting is not persisted; it is a way of looking, not a setting.

### D39 — A percentage watch point measures from the price frozen when it was set

- **Decision:** `PERCENT_UP` and `PERCENT_DOWN` watch points compare a stored close against `created_close` — the last stored close at the moment the point was created — and that baseline is persisted once and never recomputed. `ABOVE` and `BELOW` points are untouched.
- **Why frozen:** a baseline that followed the price would make *"tell me if it falls 5%"* unreachable in a slow decline, because the bar would walk down with the price. Freezing it is also what makes evaluation deterministic: the same point over the same bars gives the same answer on every cycle, which is what the announce-once guarantee (D37) rests on.
- **Reuses the existing column.** `created_close` was already persisted as context for a price point; a percentage point gives it a second, load-bearing job. No migration, no new table, no second alert model.
- **Options:**
  - **A** — measure against the previous session's close. **Rejected:** that is a daily move, not "since I asked", and a gradual decline would never trigger.
  - **B** — recompute the baseline on each cycle. **Rejected:** non-deterministic, and it silently redefines what the reader asked for.
  - **C (chosen)** — freeze the baseline at creation and record it on the point.
- **Consequences:** the reader is shown the baseline alongside the condition (*"down 5% from ₹1,322"*), because a percentage with no anchor is not checkable. A point created when no close was stored is refused rather than created without a baseline.
### D40 — The assistant is an interface to the existing intelligence, not a second one

- **Decision:** a conversational assistant answers questions about one company or about the whole watchlist, composed entirely from records the deterministic core already produced. It extends `core/explainer.py` (D35) with a watchlist scope and four intents; it adds no engine, no store, no provider and no reasoning of its own. `POST /v1/assistant/ask` takes a question and an optional `symbol` of UI context.
- **One implementation behind both callers.** `/v1/companies/{symbol}/explain` and the assistant's company path run the same function over the same records. A second implementation would be a second place for the grounding rules to drift, and the older contract keeps its exact shape.
- **Grounding is structural, not promised.** There is no generator in the answer path, so there is nothing that *could* invent a price, a counterparty, a cause or a recommendation. Every statement about the world carries the event ids it came from; a sentence that cannot name its records is not emitted. Advice and prediction are refused before any lookup, at both scopes. The failure mode is a missing answer, never a fabricated one.
- **Nothing is fetched to answer a question.** No market call, no news call, no ingestion, no model. A watchlist answer costs one review assembly and one bounded bar read — the same work as opening the dashboard — and a company answer reads the same bounded 50-row slice `/explain` already reads.
- **Context is a hint, not a cage.** A company in view answers a company question without a ticker. A watchlist question asked from a company page is answered at *its* scope rather than narrowed to fit, and a company question asked with no company says which one it needs.
- **Source credibility is the product's one vocabulary.** Cited evidence carries the same `SourceStanding` labels used everywhere else (D36). No second taxonomy exists for chat.
- **No LLM.** D35 already weighed a model-phrased variant and rejected it: it puts a model in the *answer* path, makes output non-deterministic, and spends the quota the harness shows is the binding constraint on extraction. Because there is no model, the "assistant still works when the provider is down" requirement is satisfied structurally rather than by a fallback path. If one is ever added it goes behind the existing `ports.Extractor` boundary, names itself in `generated_by`, and phrases only — retrieval, significance, credibility and ordering stay deterministic.
- **Why not RAG, a vector store, or an agent framework:** the corpus is one user's watchlist — tens of rows behind a bounded indexed query, already normalised, already scored, already carrying provenance. Embedding it would replace an exact lookup with an approximate one, and an agent loop would hand a model the fetching and judging this design deliberately keeps deterministic. Retrieval here is a `WHERE symbol = ?`.
- **Consequences:** the transcript is session-only and held in component state — each answer is composed independently from the stored record, so there is no conversational memory to keep and persisting one would imply reasoning across turns that is not happening. The inline "Ask about this company" section is replaced by the drawer rather than sitting beside it; two ask surfaces on one page would be the duplication this decision exists to avoid.
### D41 — One container, one origin, one scheduler

- **Decision:** the deployable unit is a single image in which the API also serves the built frontend from `WEB_DIST`. `/data` is a mounted volume holding the one SQLite file. Exactly one container runs.
- **Why one origin:** the session cookie is the web transport (D30). Split across two origins it needs `SameSite=None`, `Secure`, an explicit CORS allowlist and a shared parent domain — four things to get wrong to support a separation that buys nothing here. Serving the built site from the API removes the problem rather than configuring around it. `WEB_ORIGINS` remains for a split deployment.
- **Why one container:** SQLite and the in-process scheduler both assume a single writer (D10, D32). Two replicas against one volume would ingest simultaneously — which is precisely D10's stated migration trigger, not a thing to paper over with a lock.
- **The static mount is last and conditional**, so it can never shadow an API route and the API runs alone unchanged when `WEB_DIST` is unset.
- **Consequences:** no horizontal scaling without first taking D10's migration. Losing the volume loses everything, so the volume is the deployment's single stated requirement. Health stays liveness-only: source health is a domain verdict and belongs on the assessment, not on a probe a load balancer reads.
### D42 — Judge mode seeds real domain records; it never impersonates live market data

- **Decision:** `SMART_WATCHLIST_MODE=judge` seeds a fixed six-company scenario by running the **production ingestion cycle** over fixture adapters, then serves it with the scheduler disabled. The fixtures are *sources*: they implement the same protocols as the NSE, news and market adapters, and nothing downstream — extraction, grounding, linking, corroboration, the engine, persistence, the explainer — knows the difference. The only simulated part is the market scenario.
- **Why not frontend mocks:** a hardcoded card proves nothing. A judge who opens *"Why you're seeing this"* on a mocked item finds a hardcoded string; here they find the real ledger, and the scenario is only convincing *because* the engine produced it. Mocking would also make the most inspectable part of the product the one part that was fake.
- **Why not live providers for judging:** the demo would then depend on an interesting market event happening shortly before someone looks, on NSE and Google News being up, and on a model quota. Judge mode reaches no provider at all, which was verified by making all four adapters raise during seeding.
- **Storage is isolated by derivation, not by trust.** The judge path is derived from the live one (`judge-` prefix) or set explicitly, so the two cannot collide even when only `WATCHLIST_DB` is configured. The seeded database carries a marker row; seeding and reset both **refuse any database that holds records and is not marked**, so a misconfigured path fails loudly instead of overwriting real data.
- **The mode is explicit and validated.** An unknown value raises at import. Judge mode is never inferred from a missing key or an empty database — an accidental entry would put simulated data in front of someone who believed it was real, which is the single failure this feature exists to prevent.
- **Reset restores the scenario** and exists only as a route when the process started in judge mode, so there is nothing to authorise around in live mode.
- **Fixture ordering is data, not luck.** Timestamps are offsets from seed time, so the demo never looks stale while the relationships hold: the filing precedes the move precedes the reporting, and a watch point is created two days before the session that crosses it — because `evaluate` ignores sessions on or before the creation date, and the fixture respects that rule rather than working around it.
- **A limitation the fixture exposed rather than hid:** coverage is a *per-source-family* verdict, so within one review a company with nothing new is either quiet or unable — never one of each. The scenario therefore demonstrates the coverage gap (`ITC — could not evaluate reliably`) rather than a quiet company. Changing `review.py` to make both appear simultaneously would have been changing the domain model to flatter a demo.
- **Consequences:** fixture outcomes are a consistency check on deterministic reason-code paths, never evidence of real-world model quality — they are not precision or recall and are not reported as such. Judge mode ingests nothing, so `POST /ingest` returns 409 and the scheduler reports itself disabled rather than idle.
### D43 — Related assessments may be grouped for attention presentation, never merged

- **Decision:** the attention surface groups records that describe one development onto a single card, showing the primary's verdict and reasoning with the rest one expand away. Grouping is a **display key** computed at serialisation time (`development_id`) and changes nothing about event identity, scoring, reason codes, evidence, corroboration, canonical ordering or review semantics.
- **Why it is needed:** the product's argument is that attention is scarce. Three cards saying nearly the same thing spend it badly even when all three records are individually correct — the interface would be failing the thesis the engine is upholding.
- **The relation is D12's, reused rather than reinvented:** same company, within D12's link window, and title similarity at or above D12's calibrated link threshold (0.5, tuned against real multi-publisher coverage). What it drops is the **event-type bucket**, and that is the whole point. The three RELIANCE records that prompted this were classified `Agreements`, `Acquisition` and `Outcome of Board Meeting` — three buckets, so linking could never consider them, while a reader plainly sees one announcement reported three ways.
- **Why dropping the bucket is safe here and not in D12:** D12 merges evidence and rewrites provenance, so a false merge corrupts corroboration invisibly and permanently. This asserts only that a reader would call these one story, merges nothing, and is undone by clicking expand. The consequence of being wrong is a collapsed card, not a corrupted record.
- **It cannot chain.** A candidate is compared against a group's primary, never against any member, so A grouping with B and B with C does not drag in a C unlike A.
- **The primary is the canonical first.** Presentation reuses the backend's single ranking answer (D26) rather than introducing a second one, and groups appear in their primary's position so ordering survives grouping untouched.
- **Scores are never summed.** The card shows the primary's attention, confidence and reason-code arithmetic. A related record with a different verdict is shown as development history rather than hidden, because a story that was MEDIUM yesterday and is HIGH today is information.
- **Corroboration stays D13's.** The development's independent-source count is computed over the union of its evidence by `assess_corroboration`, never by adding member counts, which would double-count shared publishers. Zero is omitted rather than printed: our own market measurement has no publisher.
- **Computed on the server** because that is where the calibrated relation lives. A TypeScript reimplementation would be a second copy of a tuned rule, and the copy nobody tested would eventually win. The client does a `groupBy` and nothing more.
- **Deliberately not applied to the company timeline.** That surface answers *"what happened, in order?"* and each update is a distinct thing that happened; the attention surface answers *"what deserves me?"*, where three near-identical cards are the problem. Different questions, different presentation.
- **Consequences:** records that a reader would call one story but whose wording diverges below the threshold stay separate — the intended failure direction. A market observation coinciding with a story stays its own item, because grouping it in would assert a cause the system does not claim.
---

## Not doing

- **Reddit and social signals.** Deferred deliberately, not dropped. Another adapter, noisy entity matching, discussion baselines, manipulation and spam, sentiment ambiguity and rate limits — disproportionate cost against a thesis better served by lifecycle, disclosure and structured news. **The seam stays:** the event and evidence model is source-neutral, and S5 shows the adapter slotting in without touching the engine. Social remains a planned signal family in the architecture and the vision.
- **Supply-chain graphs, broad geopolitical ingestion, exhaustive competitor graphs, full international-market relationships.** Represented in company context where curated and verifiable; not built as ingestion pipelines. **No empty abstractions or unused infrastructure are built in anticipation of them.**
- **Notifications, alerts, digests.** The product is deliberately pull-based; adding an interrupt stream to an attention product contradicts its premise (VISION §17).
- **Natural-language querying, and a general chatbot.** The intelligence must exist in the evaluation, not in a chat box. D35 draws the line precisely: a reader may ask a bounded question about *one* company and receive an explanation composed from records already assessed, cited and windowed. Free-form questions across the watchlist, anything a model answers in its own words, and anything that would reach a source at question time remain out.
- **Price prediction, recommendations, broker integration.** Out of scope by principle, not capacity.
- **Per-event read state.** D7 — session-level checkpoints only. Revisit only if it proves cheap and a journey demands it.
- **OAuth, social login, MFA, passwordless, federation.** D8.
- **RBAC framework, admin and analyst roles.** D9 — no journey requires them.
- **Postgres, Redis, message brokers, distributed locks, multiple workers.** D10, with the trigger stated.
- **Embedding or ML-based event clustering.** D12.
- **A trained attention model.** D4 — no labels, no explanation, and explainability is a product requirement.
- **A multi-provider LLM framework.** D5 — one interface, one adapter.
- **A React SPA.** D2.
- **Global securities as watchable instruments.** Global data is evidence; the universe is Indian equities (VISION §1).
- **Intraday quotes, tick data and live streaming.** D28 — daily adjusted EOD bars only. Intraday resolution turns an attention product into a price monitor, is the expensive half of every market feed, and answers a question the product has decided not to ask.
- **Redistribution-licensed market or news feeds.** The price context is derived from freely retrievable EOD data and shown as our own comparison; no vendor content is re-served. If a licensed feed ever becomes necessary, it is a procurement decision recorded as a new one — not something an adapter quietly adopts.
- **Model-owned contradiction.** D29 — a model may propose that two records conflict; only the deterministic gates may mark one disputed. Nothing is deleted or rewritten on a model's say-so.
- **Per-user scoring, learned relevance, or personalised attention levels.** D27 — interests filter and annotate; they never change a score. Two users looking at the same company see the same severity, and the shared intelligence stays shared.
- **A mobile-specific backend, a second API, or a BFF layer.** D30 — one API, two transports. A mobile client that needs a different response shape is a signal that the response shape is wrong for both.
- **A model leaderboard or blended quality score.** D31 — the harness measures per model against deterministic invariants and reports per model. Averaging providers into a single number destroys the only thing the measurement was for.
- **Untested scale claims.** D32 — what was run is stated as run; everything beyond it is stated as a path, with its trigger.
- **A separate `mental-model.md`.** Deliberate omission, not an oversight. `VISION.md` already owns the conceptual model — meaningful change, attention versus recommendation, world state versus user state, confidence versus attention — and this document owns architecture. A third file restating those concepts would add documentation surface without adding clarity. **Documentation artifacts exist when they resolve a distinct engineering concern, not because a template has a checkbox.**

---

## Open questions

Four resolutions that were listed here have been folded into the decisions above: `AMBIGUOUS` presentation into D12, calibration into D4, decay policy into D16, and coverage language into D15. What remains is genuinely unsettled or is an assumption the design rests on.

1. **Syndication mapping is hand-maintained and incomplete (D13).** An unlisted wire relationship inflates the independent-source count and therefore confidence. Whether incompleteness needs detection — near-identical text across publishers within minutes is a cheap signal — rather than curation is unsettled.
2. **Threshold values are deliberately empirical (D4).** Not an oversight: no defensible values exist without historical evaluation and outcome data. The mechanism is settled, the calibration is versioned and regression-tested against the fixture set, and the honest answer to "why this number" is "judgement, held stable by tests." This stays open by design.
3. **Baseline warm-up.** Newly added securities have no trailing distribution. The design says movement claims are weaker and must say so; how weak, and for how long, is undecided.
4. **Assumption: `yfinance` and RSS remain usable throughout.** Both are unofficial or best-effort. Isolation behind adapters means an outage degrades one class, but a permanent break in the market adapter has no fallback and would be a significant loss.
5. **Assumption: the NSE disclosure endpoints are workable.** They are undocumented and defensive. If integration proves unreliable, the adapter boundary preserves the capability while the source is swapped — but the HIGH-confidence tier depends on having *some* authoritative source, and losing it weakens the provenance story more than losing any other single input. This is what Step 0 exists to settle early.
7. **Interest tags are a fixed curated vocabulary (D27).** Free-text tags would match how people actually describe what they watch, but nothing deterministic could then explain *why* an event matched. Whether a small curated set stays sufficient, or needs a curated synonym layer over free text, is unsettled and should be answered by what users actually type into the free-text fields.
8. **Sector index membership is curated per company (D28).** There is no free, reliable, machine-readable NSE sector-constituent mapping; the assignment is hand-maintained and will drift. How to detect drift — rather than re-curate on a schedule — is undecided.
9. **The contradiction gates are strict by construction (D29).** Requiring same identity bucket, at-least-equal source tier, later publication and grounded text will miss real contradictions — a correction from a lower-tier outlet, or one phrased without reusing the original's terms. That is the intended failure direction, but the false-negative rate is unmeasured.
10. **The harness ground truth is small and designed.** Its 21 human-authored cases cover known hard failures; they are not a random sample of live news. A shared omission outside that vocabulary remains invisible, so fixture performance must never be presented as live accuracy.
11. **Bearer session rotation and secure device storage are not designed yet (D30).** Server-side expiry and revocation already apply to both transports. A complete mobile app still needs an operating-system-backed token store, renewal policy and compromised-device story.

6. **Both documents live at the repository root**, not `docs/`, which is where the other Aganitha skills look. Deliberate — they are the two top-level artifacts of the project — but a pointer file may be needed for `aganitha-system-health` and `aganitha-preflight` to find them.

---

## Next

Do not scale infrastructure yet. First measure one complete live 500-evidence cycle, including network waits and SQLite writes, and add a contention test that can actually exercise D10's migration triggers. Retry the single-model harness when provider quota is available; the current run proves explicit quota failure and fallback, not model quality.

The thin mobile proof validates the shared contract and review flow. Broader mobile development is justified only after secure token storage and rotation are designed and the compact review projection has been validated on a physical device. Lifecycle and persisted summaries remain separate product work and are not prerequisites for these platform decisions.
