# Status

**Where the build is:** Step 4 complete and reviewed. Accounts, watchlists and review
checkpoints exist, so the product now answers *"what changed since **you** last checked"*
rather than *"what does the system know"*. Ingestion is still manual and lifecycle is not
built.

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
- **Ingestion is still manual.** `POST /ingest` — the system observes only when asked, so
  "while you were gone" depends on someone having run it.

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

**Live throughput is unmeasured.** The evaluation is 21 articles. A full ingest across the
curated universe produces ~160 articles per run, far beyond the daily free-tier budget, so
production runs currently fall back to the rule extractor for most articles. The fallback
is real and separately provenanced, but the model's live contribution is small.

## Next — step 4, user state

Auth, watchlists, review checkpoints, the frozen review window (D7, D8). This is what
turns a list of assessments into *"what changed since you last looked"*, which is the
product's actual claim.

Then: lifecycle and summaries (E, F) → frontend. Scenario letters refer to the demo matrix in `DESIGN.md`.

## Known gaps in what exists

- **Ingestion is manual** — `POST /ingest`. Step 3 puts it on a schedule; until then the
  system cannot answer "what changed while I was gone" (D3).
- **The curated universe is 8 companies**, not 50. Everything else is `LIMITED` and says
  so. Depth over breadth (D19).
- **`save_run` is called after the assessment loop**, so a mid-loop persistence failure
  would leave assessments without a run record. Accepted for now; it belongs with the
  scheduled ingestion in step 3, where a crash mid-run becomes likely.
- **The UI is deliberately ugly** and stays that way through step 5.

## Risks, reordered

1. ~~No authoritative disclosure source works.~~ **Closed** by Step 0 — with the caveat
   that one session is not a reliability guarantee. The same caveat now applies to
   `yfinance`: it worked across 11 symbols in one session. That is not reliability.
2. **LLM extraction quality on real news** — the next unproven thing, and it fails
   quietly rather than loudly. Validate on real articles in step 2 before building on it.
3. **Event linking tuning** — too conservative and scenario D shows duplicates, which is
   the aggregator behaviour the product claims to fix.
4. **No convincing RESOLVED example** may occur in the live window; seeded fixtures
   (D18) are the mitigation and must be built from step 2, not at the end.
5. **Frontend time** — J2 and J4 are non-negotiable, J8 search drops first. Less acute
   than it was: Step 0 shipped a working, if ugly, interface rather than deferring all
   of it to step 6.
