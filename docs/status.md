# Status

**Where the build is:** the web product is demo-ready and the platform foundation has now
been validated. Scheduled ingestion, news, market data, exchange disclosures, accounts and
per-user review windows are complete; web and a thin native proof consume the same `/v1`
contract.

## Attention hierarchy on the review page

- **The answer is stated, not counted.** "While you were away" now names the developments
  that demand attention — level, symbol, company, when, headline, one why-line and a link
  into the full card — instead of reporting a bare count and leaving the reader to hunt.
  Selection reuses `demandingDevelopments()` over the grouped, server-ordered items; there
  is no second ranking (D26, D43).
- **A reader's own level keeps its own block.** Triggered watch points read as "You asked
  to be told" above operational counters, because a level the reader set is a distinct
  reason for attention and is never folded into development grouping (D37, D43).
- **Coverage is named, not numeric.** Companies that could not be evaluated are listed by
  symbol with the reason silence is ours and not the market's (D15).
- **Contrast and case:** `--faint` and `--quiet` were raised to 5.62:1 and 5.10:1 on panel;
  hero and control headings are sentence case rather than mono uppercase.
- **Counters are chrome.** Below 40rem the terminal strip scrolls as one row instead of
  wrapping to three, which moved the answer 75px up the phone viewport without dropping a
  single count.
- **Orientation and answer are separate.** A compact view-context bar names the view, the
  review window and the action that closes it; the hero below answers what changed. The
  checkpoint sentence is stated once, in the bar.

## Platform and validation foundation

- **One versioned API:** product routes are under `/v1`; Pydantic/OpenAPI is the wire source
  and a committed generated TypeScript package is shared by web and mobile (D33).
- **Thin mobile proof:** the Expo app loads the real Needs Attention review in canonical
  server order, opens company detail, shows evidence/coverage/contradiction state and
  completes the same server-owned review cutoff. Its iOS production bundle was generated
  successfully. It deliberately has no complete login, secure token storage or broader
  app navigation.
- **Measured local workload:** 50 memberships over 500 shared assessments assembled at
  0.18 ms p50 / 0.19 ms p95; the SQLite-backed path was 13.00 ms p50 / 14.65 ms p95;
  20-thread pure-domain observation was 5,000 reviews/s; 500 rule extractions plus grounding
  ran at 61,991 articles/s; 252-session three-series chart work took 0.49 ms; process peak
  RSS was 97.5 MiB. These are local bounded-path measurements, not deployed API capacity.
  Network time, full-cycle ingestion and SQLite write contention remain unmeasured.
- **Price reads are network-free:** scheduled market ingestion upserts one year of EOD bars
  by symbol and session; `/v1/prices` reads that store. A fresh database returns an honest
  empty chart until the first market run rather than fetching during the page request.
- **Reproducible LLM harness:** provider/model/prompt, raw output, validated result, fallback,
  latency, tokens, cost inputs, schema failure, unsupported fields and attribution failure
  are retained in a database isolated from product state. The 21-case rules baseline is
  100% precision and 64.3% recall under the current subject-safety gate; 4/4 deterministic
  contradiction cases pass.
- **Live model result:** Gemini 3.6 Flash returned explicit quota exhaustion on all 21 calls,
  so model quality, token use and cost were not measurable. The separately named
  Gemini-to-rules pipeline fell back on all 21 and matched the rules result. This proves the
  coverage/fallback path, not Gemini extraction quality.

- **Scheduled ingestion is complete.** The system observes unattended; nobody calls an
  endpoint for *"what changed while you were gone"* to be true.
- **News, market observations and disclosures share one assessment path** — one engine,
  one reason-code ledger, one persistence model.
- **User-specific review windows work.** Two accounts watching one company read the same
  underlying analysis and see different reviews.
- **Gemini is quota-limited** — 20 requests per model per day on the free tier, so most
  live articles are handled by the fallback.
- **The rule fallback is separately provenanced and fails closed on uncertain subjects.**
  It never borrows the model's identity, and it declines rather than guess who an article
  is about.
- **Lifecycle and generated summaries remain unbuilt.**
- **The interface opens on the Watchlist.** Each followed company has a compact card with its
  latest stored EOD price, daily adjusted movement and short trace alongside the latest
  relevant development; it links to a dedicated company page. The attention view remains the
  server-ranked answer for what is new since the last completed review (D26). Company detail
  keeps the full aligned price comparison and event evidence, with news and market events
  ordered by attention then recency and expandable only into source-backed explanation.
- **A watchlist entry can say what it is for.** Adding a company asks why you follow it,
  what you want to watch for, and which focus areas apply — all optional. Only the focus
  tags do anything, and only as a filter and an annotation. **A HIGH is never hidden by a
  focus filter**; it is shown marked *outside your focus — we think it matters anyway*, and
  the count of what the focus did narrow away is stated rather than silently applied (D27).
  The focus chips appear only on *Needs attention*, because focus narrows developments and
  the watchlist lists companies — on the watchlist the control did nothing at all.
- **Price context lives inside a company's detail.** Daily corporate-action-adjusted closes
  for the company, its sector index and the broad market, restricted to the sessions all
  three share and rebased to 100 — computed in the backend, drawn by the client (D28). A
  benchmark that has stopped updating is excluded and named rather than silently truncating
  the company's own range. Nothing is interpolated.
- **A contradicted report is marked and linked, never deleted.** Both records stay
  readable, the phrase the dispute rests on is quoted, and the note says plainly that a
  dispute lowers how sure we are rather than how much something matters (D29).
- **The board adapts to the width it has, not to a guessed device.** Watchlist cards use
  `auto-fill` with a comfortable minimum, so a phone, a split screen and a half-width
  window all reach a single stacked column on their own; two columns arrive around 900px
  and three only past ~1300px. The previous fixed breakpoint put three cramped columns on
  anything wider than 832px.
- **Cards show the session in full**: last close, the move in rupees *and* percent under
  one sign, the day's high–low range and volume — all from the same stored bar, all
  omitted rather than substituted where the provider gave nothing.
- **The watchlist sorts locally** by gainers, losers, largest move, A–Z or recently added
  (D38). No request is made to sort, and it never touches the canonical ordering of
  developments. A company with no stored close sorts last, never as a flat move.
- **Company detail carries a timeline and an alert history.** The timeline re-reads the
  assessments already loaded, newest first, and says plainly that adjacency in time is not
  causation. The alert list is the watch-point records themselves — no second copy, and no
  severity field, because a level the reader chose has none we could honestly assign.
- **Watch points can be a percentage move** measured from the price frozen when the point
  was set (D39) — *"down 5% from ₹1,322"*. A baseline that followed the price would make a
  slow decline unreachable.
- **The whole watchlist card is one link.** A click anywhere in the box that is not
  another control opens that company, and because it is a real `<a>` rather than a click
  handler, middle-click, ctrl-click and "open in new tab" all work and the destination
  shows on hover. The trace, the expander, the expanded text and remove sit above the
  stretched overlay and keep their own behaviour.
- **Cards answer "is this worth opening?" in place.** *Why this is here* expands the full
  headline, the engine's reason codes and the publishers behind it without leaving the
  board, and the end-of-day trace is readable rather than decorative: pointing at it — or
  arrowing along it with the keyboard — names the stored session and its close. The
  position maps to the nearest **stored** session, never to a value between two of them.
- **A reader can mark "watch out for this" on a company** (D37): a price level and a note.
  The scheduled cycle settles it against stored end-of-day closes and a crossing appears at
  the top of the board on the next visit — pull-based, never pushed, and worded as
  *"closed ₹1,405 on 2026-09-08"* rather than "hit ₹1,400". A level already reached is
  refused rather than fired instantly; a triggered level announces once and stays on the
  record after it is acknowledged.
- **Responsive and keyboard-navigable.** One column on a phone, three on a wide screen; the
  detail is a labelled dialog that takes focus on open, closes on Escape and returns focus
  where it came from. No meaning is carried by colour alone — every attention level is
  spelled out in words beside its badge.
- **The assistant drawer closes on every surface.** On a phone the sheet covers the
  floating button and there is no Escape key, so the panel carries its own close control;
  closing returns focus to the button that opened it, and the transcript is a live region
  so answers are announced rather than only drawn.
- **An assistant drawer answers questions on both surfaces** (D40) — the watchlist ("what
  needs my attention", "biggest movers", "which alerts triggered", "any new disclosures")
  and one company, using the company in view as context so "why did this fall?" needs no
  ticker. It composes from records the engine already produced: **no model, no fetch, no
  second engine**, and every statement about the world names the records behind it. The
  company path runs the same code `/explain` runs.
- **Company detail answers a bounded question about the company** (D35). Not a chat box:
  a fixed set of questions — what changed, why it was surfaced, what we could not see, who
  reported it, what the market did, what has been disputed — answered by composing stored
  assessments, reason codes, coverage records and cited evidence. **No model is in the
  answer path**, a question never triggers ingestion or an external fetch, every statement
  about the company names the events it came from, and advice or prediction is refused
  before anything is looked up. "I don't have enough evidence" is a normal outcome with a
  stated reason, not an error.
- **Every development shows what kind of source it came from** (D36) — exchange filing,
  established outlet, press release, unrecognised publisher, or our own measurement — as a
  third badge beside attention and confidence. It is descriptive, not a rating:
  "unrecognised" means absent from a curated list of 60-odd publishers, never
  untrustworthy. A story carried only by unrecognised publishers scores one point lower;
  a single recognised publisher, or independent corroboration, clears it.
- **News with no observed market reaction is nudged down by one point**, and only where the
  market was actually consulted. Worded as an observation about the market rather than a
  judgement about the report, and weak by design: price is often the slowest signal, so a
  quiet market must never be able to bury a development on its own.
- **A company's record is grouped by kind, then by type.** Exchange disclosures, market
  observations and news are different kinds of thing, and news splits again by the engine's
  own event types (Expansion, Financial Result Updates, Legal, and so on). A long record
  read as one undifferentiated stream is unreadable; a filing and a rumour should not look
  alike.
- The frontend filters and formats; ranking, confidence, coverage, the rebasing behind the
  chart and every contradiction decision are the backend's, copied verbatim.
- **The demo opens without a login.** Anonymous callers resolve to one persistent
  server-owned account (`DEMO_MODE`, on by default), so the dashboard is immediately
  usable while watchlists and checkpoints stay real. Authentication is bypassed, not
  removed: a real session still wins, and `DEMO_MODE=off` restores the wall exactly.
  **Any deployment reachable by other people must set it off** — in demo mode every
  visitor shares one account's state.

## What Step 0 established

Proven, by running it — not by design intent:

- **The authoritative disclosure adapter works.** NSE corporate announcements ingest
  without a cookie handshake; `seq_id` gives idempotency and `desc` gives a disclosure
  category, so Step 0 needed no LLM at all.
- **The full path runs:** evidence → normalization → event candidate → provenance →
  the Meaningful Change Engine → persisted assessment → rendered UI. Verified on a live
  run: 20 real disclosures, 4 earning MEDIUM, 16 reported as *unable to evaluate
  reliably*.
- **Provenance survives the round trip.** Source tier, publisher, subject company,
  exchange timestamp and the filing URL are intact after persistence. That was the
  actual acceptance criterion — not that an endpoint responded.
- **Coverage survives zero-evidence and failed runs**, persisted at run level
  independently of assessments (D20). A failed ingest can no longer leave an earlier
  run's healthy coverage standing as current.
- **Publisher and subject company are separate fields** (D21). Company identity resolves
  from the subject, never from the publisher.
- **Canonical ranking is backend-owned** (D22); the frontend renders the received order
  unchanged.
- **The frontend API base is configurable** via `PUBLIC_API_BASE`, so a demo does not
  require a source edit.
- **The failure path is explicitly tested**, not assumed: a source outage keeps earlier
  verdicts visible while reporting current source health as failed, and the page says
  so in words.
- **Live rendering verified** in a browser, including the failure banner.
- **Curated status does not override missing coverage.** HINDALCO is in the curated
  universe and still reads *unable to evaluate reliably*, because market and news are
  absent. The verdict tracks coverage, not curation.

The Step 0 review gate was completed only after a blocking coverage defect was found
and corrected — see the CHANGELOG entry.

## What scheduled ingestion established

- **Ingestion runs without anyone calling an endpoint.** An in-process asyncio scheduler
  in the application's lifespan, one cycle at a time, explicit interval. Demonstrated
  live: a user completed a review, went away, a scheduled cycle ingested 218 assessments,
  and on return their review showed **16 assessed changes** — checkpoint untouched.
- **One ingestion path.** `POST /ingest` and the scheduled tick both call `run_cycle`, so
  the operator affordance exercises exactly the unattended code. A manual trigger during
  an active cycle returns **409 busy** rather than queueing.
- **A run is recorded before anything it produces.** Each pipeline writes its run as
  `RUNNING` with its own source marked unavailable, then replaces it with the outcome. A
  process killed mid-cycle leaves a record that says so, and startup reaps anything still
  `RUNNING` as `INTERRUPTED` — nothing but a crash can leave that state.
- **A run that failed or was interrupted is never healthy**, whatever partial coverage it
  recorded. Old healthy coverage cannot survive a failed newer attempt.
- **Families fail independently.** A news outage is a fact about news; market and
  disclosures still update. Verified for each of the three.
- **Model exhaustion is not source failure.** Gemini returning nothing degrades to the
  separately-provenanced rule extractor and the cycle still reports `succeeded`.
- **Nothing external happens on page render.** The UI reads persisted intelligence only.

## Fallback subject safety

The rule, in one sentence: **a company must be named in the headline, inside the leading
clause, in a subject position** — otherwise the fallback makes no claim.

- Aliases are curated per company (canonical name, ticker, explicit short forms). Never
  inferred from text.
- Matching is on token boundaries, so "Relianceable Systems" is not Reliance.
- Everything after the first `:`, `;`, `|` or spaced dash is commentary, so list and
  roundup headlines cannot name a subject.
- A name preceded by a counterparty preposition, or by a relationship word (supplier,
  rival, peer, backed, unit), is the other party rather than the subject.
- Body-only mentions are refused. A bounded rule cannot judge what a paragraph is about,
  and declining is the honest response. Gemini handles those when it is available.
- Refusals persist the evidence and the reason, so "no event" is auditable rather than
  indistinguishable from never having looked.

Measured live with the model unavailable: 119 events accepted, 411 articles refused —
`subject-not-named-in-headline` 146, `no-recognisable-event-type` 150,
`subject-named-outside-leading-clause` 42, `subject-named-as-counterparty` 36,
`market-roundup` 36, `subject-named-as-a-relationship` 1.

**Accepted residual risk:** short aliases such as "Reliance" are curated deliberately.
Other listed companies share that word, so a headline about one of them could pass. The
subject-position rules remove the common cases; the remainder is why short aliases are
curated one at a time rather than generated.

**Known limits:** correction reads the most recent 1000 assessments, so larger stores would
need paging. Events resting partly on a filing or a market observation are never re-judged
by a headline rule — they stand on evidence that was not attributed by headline.

## What scheduled ingestion did *not* establish

- ~~**The rule fallback misattributes other companies' articles.**~~ **Closed** — the
  fallback now grounds the subject deterministically in the headline. Retrieval context is
  a hint, never proof (D21). Correcting the existing data withdrew **68 of 148**
  rule-derived news assessments as unsupported attributions, which is the size the defect
  had reached.
- **No retry or backoff.** A failed family simply fails and waits for the next interval.
- **Single process only.** The overlap guard is an in-process flag, which is correct for
  this deployment and insufficient for two.

## What Step 4 established

- **Two accounts, one analysis, two reviews.** Alice and Bob watching the same company
  read the same underlying assessment records; only the window differs. Verified live and
  in tests: after Alice completes a review she sees only what arrived since, while Bob —
  who has never reviewed — sees everything.
- **The review window is `(previous_checkpoint, review_cutoff]`**, with the cutoff issued
  and stored by the server. Completion resolves the review by **id**, so a client cannot
  submit a cutoff it was never issued.
- **An event arriving mid-review stays new.** Completion advances to the issued cutoff,
  never to the click.
- **Nothing else advances the checkpoint** — not rendering, not refreshing, not dwelling.
- **Advancement is monotonic and idempotent.** A stale tab submitting an older cutoff
  reports `stale-cutoff-ignored` and changes nothing; completing twice reports
  `already-at-this-cutoff`. Monotonicity is enforced in SQL (`MAX`), not read-then-write.
- **Ownership is enforced by scoping, not checking.** Every private query filters on the
  session's user, so a substituted id reaches a query that finds nothing. Bob completing
  Alice's review returns 404 and leaves her checkpoint untouched.
- **Coverage still outranks capability.** A newly added FULL-coverage company read
  *"could not evaluate reliably: news, nse-disclosures"* rather than *quiet*, because
  those sources had not been consulted.
- **A newly added company has no manufactured history.** Its window starts when the user
  added it, and the review says so.

## What Step 4 did *not* establish

- **Sessions are not cleaned up.** Expired rows remain until something deletes them.
- **`Secure` is not set on the session cookie**, because local development is plain HTTP
  and a Secure cookie would silently never be sent. A TLS deployment must set it.
- **No password reset, email verification, or account deletion.** Deliberately out of
  scope (D8); an account is currently unrecoverable if its password is lost.
- **Ingestion was still manual** at the end of Step 4. *(Closed by scheduled ingestion —
  kept here because it is what Step 4 itself did not establish.)*

## What Step 2 established

- **News travels the whole path**: Google News RSS → Evidence → extraction → grounding
  validation → subject resolution → event linking → corroboration → the engine →
  persistence → API → UI.
- **Case D, live**: the Tata Motors/Iveco tender offer became **one event with 8
  evidence records from 8 independent publishers**. Article count and event count are
  different numbers.
- **D13, live**: HDFC Bank coverage showed *4 articles · 3 independent sources* where
  one publisher repeated, and *4 articles · 1 independent source* where a single outlet
  posted four times — the latter scored LOW, not HIGH. Repetition did not manufacture
  confidence.
- **Grounding is deterministic, not prompted.** Any counterparty, product, geography,
  regulator or monetary figure must appear in the source text or it is dropped and the
  drop is recorded. A fabricated `contract_value` was caught this way during evaluation.
- **Attention stayed scarce**: 14 HIGH out of 158 stored events (9%).
- **The LLM is optional by construction.** With no credential the rule extractor runs and
  the system keeps working with a plainly weaker reading (D5).

## What Step 2 did *not* establish

- **The model-backed path runs and the full 21-article evaluation is complete.** All 21
  fixture cases have genuine Gemini outcomes: **14 true positives, 7 true negatives, 0
  false positives, 0 false negatives** — 100% precision and recall, no unusable
  responses. Three grounding rejections removed fields the sources did not support.
- **The 21 outcomes span three sibling flash models**, not one: 17 on
  `gemini-3-flash-preview`, 2 on `gemini-flash-latest`, 2 on `gemini-3.1-flash-lite`. The
  free tier caps requests at 20 per model per day, so no single model can complete a
  21-call run in one day. D25 treats the model revision as deployment configuration
  rather than a domain contract, which is what makes the split acceptable — but it means
  these are Gemini-family figures, not one model's figures.
- **The fixture is a designed test set, not a random sample.** 21 hand-picked articles
  weighted toward hard cases. 100% on it means the known failure modes are covered, not
  that extraction is solved.
- **Gemini reaches 100% recall and precision on the fixture; the rule extractor reaches
  86% / 100%.** The difference is in the rejections. Gemini refused the incidental
  mention, the sector-wide story, the analyst-scenario piece and the broker rating by
  understanding what each article was about; the rule extractor gets some of those right
  only because no keyword matches. Gemini also separated the two same-day Tata Motors
  events by extracting different counterparties — Iveco and Vertelo — which is what gives
  event linking something conflicting to separate on.
- **Syndication detection is incomplete** and always will be. Unknown syndication
  inflates the independent-source count; nothing detects it.
- **Event linking is lexical.** Two articles describing one story in very different
  language will produce two events — the safe direction, but still wrong.

## What Step 1 established

- **The D14 chain runs in the frozen order**, enforced structurally rather than by
  comment: adjustment → normalized observation → own-security trailing baseline →
  sector/index residual → unusualness → reason-code contribution.
- **Unusualness is measured against each security's own trailing distribution**
  (126 sessions live), never a fixed percentage.
- **Scenario G proven**: a two-for-one split reads as `-50%` unadjusted and ~0% adjusted.
  It produces a corporate-action note at `NO_MEANINGFUL_CHANGE` with HIGH confidence —
  never an unusual-movement event.
- **Scenario A proven**: an unusual move with no disclosure behind it is surfaced with a
  `NO_COMPANY_EVENT_DETECTED` reason code. The system reports the gap rather than
  manufacturing a cause.
- **Market context reaches disclosures too** — the disclosure pipeline consults market
  data, and when it is not consulted it says so rather than omitting it.
- **A self-explaining finding is exempt from the blind→unable promotion.** A corporate
  action fully accounts for the move it caused, so reporting it as *unable to evaluate*
  would misrepresent something understood exactly. The exemption is deliberately narrow.
- **`TATAMOTORS` was removed from the curated universe** — it demerged into TMPV and TMCV
  and no longer resolves. Carrying a dead symbol would have produced a permanent,
  unexplained coverage gap for a company claimed as fully covered.

## What Step 1 did *not* establish

- **Calibration is not validated.** A 12-sigma unexplained move currently lands at LOW,
  because `NO_COMPANY_EVENT_DETECTED` nearly cancels `UNUSUAL_PRICE_MOVE`. Whether an
  unexplained move should be *demoted* or *promoted* is an open product question —
  see the note below.
- **Intraday behaviour does not exist.** Daily bars only.
- **Sector mapping is hand-curated** for nine securities. Anything outside it is judged
  without a sector reference, and says so.
- **Corporate-action detection depends on the provider** marking the split or dividend
  on the session. An unmarked action would not be caught.

## What Step 0 did *not* establish

Stated explicitly, because the list above is easy to over-read:

- **NSE reliability is not proven.** One endpoint responded over one session. It remains
  undocumented and defensive, and it is isolated behind an adapter for that reason.
- **The Meaningful Change Engine is not complete.** Relevance, corroboration and
  market-relative significance do not exist yet; scoring currently reads provenance,
  disclosure category, curated-universe membership and coverage.
- **There is no news ingestion.**
- **LLM extraction is unvalidated** — nothing in the running system calls a model.
- **Event identity is not solved.** One event per disclosure; no linking, no
  `AMBIGUOUS` outcome yet (D12).
- **Lifecycle is not implemented.** No state transitions, no resolution, no decay.
- **There is no user state** — no accounts, watchlists or checkpoints. Everything served
  is shared intelligence, identical for every reader.

## Open product question, for a human

**Should an unexplained move be demoted or promoted?** Today `NO_COMPANY_EVENT_DETECTED`
scores −2, so a 12-sigma move with three times normal volume lands at LOW. The argument
for demotion: we cannot corroborate it, and news is not built. The argument for
promotion: a large move nobody can explain is *more* concerning than an explained one,
and VISION.md §5 treats it as an honest finding rather than a weak one. This is a
calibration decision (D4) and belongs to a person with the fixture set, not to a silent
weight change.

## Known limits, not blockers

**The free-tier quota caps requests at 20 per model per day.** A single-model 21-call run
is therefore impossible in one day, which is why the evaluation spans three sibling flash
models. A paid tier would collapse this to one model and make the figures directly
comparable across runs.

**End-to-end live throughput is unmeasured.** The evaluation is 21 articles. A full ingest across the
curated universe produces ~160 articles per run, far beyond the daily free-tier budget, so
production runs currently fall back to the rule extractor for most articles. The fallback
is real and separately provenanced, but the model's live contribution is small.

## Recommended next

Do **not** introduce Postgres, Redis, queues or separate workers yet. First measure one full
500-evidence live cycle including provider waits and SQLite writes, then exercise concurrent
writers. The present measurements show no infrastructure bottleneck on the read/domain path.

The native proof justifies validating the flow on a physical phone, but not building the
complete mobile product yet. Secure token storage and rotation plus a compact mobile review
projection come first. Retry one model through all 21 cases when quota is available; until
then the extraction fallback, not model quality, remains the product limit.

Lifecycle (D16) and generated summaries (D6) remain unbuilt product work.

## Known gaps in what exists

- ~~**Ingestion is manual.**~~ **Closed** — the scheduler runs unattended.
- **The curated universe is 8 companies**, not 50. Everything else is `LIMITED` and says
  so. Depth over breadth (D19).
- ~~**`save_run` is called after the assessment loop.**~~ **Closed** — each pipeline now
  records its run before anything it produces can persist, so an assessment cannot exist
  without the run that explains its coverage.
- **Watch points are end-of-day only.** A level crossed and recovered inside one session
  is never seen, and only price levels are supported — a note saying "watch out for a
  regulatory ruling" is a reminder to its author, not something the system checks.
- **The publisher registry is curated and incomplete.** An outlet we have not catalogued
  is labelled unrecognised, which is accurate about us and unfair to them. Corroboration is
  the route by which a real story from an uncatalogued outlet still reaches the reader.
- **The explainer's intent vocabulary is curated**, so an unusual phrasing lands on
  "I can only answer from what we have already assessed" with suggestions rather than
  being understood. Widening it is curation work, not model work.
- **Interest tags are a fixed curated vocabulary.** Free text is captured and kept for the
  reader, but only the curated tags can be explained, so only they filter.
- **Contradiction recall is low by construction.** Four gates must all pass, so quiet
  corrections and disputes phrased in different words are missed. The false-negative rate
  is unmeasured.
- **Sector index membership is hand-curated** and drifts. Two of the NSE sector indices the
  price feed serves stopped updating in July 2026; they are excluded from the comparison
  and named, which is visible in the demo.

## What is measured, and what is not

**Extraction is measured.** 21 hand-labelled articles, `make llm-harness`: the rule
extractor reaches 100% precision and 64.3% recall; Gemini reached 100%/100% across three
sibling flash models. Fixture performance, and the report says so.

**The attention engine is not.** 393 passing tests prove the implementation matches its
specification — not that the ranking is *useful*. The harness that would measure it exists
and is tested (`make attention-eval`, `evaluation/attention.py`); its labelled set is
deliberately empty, because inventing labels produces a number that looks like evidence
and is not. Filling it in requires reading real assessments and recording what a careful
reader would have wanted.

## Risks, reordered

1. ~~No authoritative disclosure source works.~~ **Closed** by Step 0 — with the caveat
   that one session is not a reliability guarantee. The same caveat now applies to
   `yfinance`: it worked across 11 symbols in one session. That is not reliability.
2. **Model extraction at live volume** remains constrained by quota. Provider failure is
   now loud and measured, but most live volume still takes the lower-recall rule fallback.
3. **End-to-end ingestion capacity and SQLite contention** have not been measured at the
   stated 500-evidence workload; the fast pure-domain measurements do not answer either.
4. **No convincing RESOLVED example** may occur in the live window; seeded fixtures
   (D18) are the mitigation and must be built from step 2, not at the end.
5. **Frontend time** — J2 and J4 are non-negotiable, J8 search drops first. Less acute
   than it was: Step 0 shipped a working, if ugly, interface rather than deferring all
   of it to step 6.
