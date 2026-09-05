# Status

**Where the build is:** Step 2 complete and reviewed. News joins market data and
exchange disclosures, with structured extraction, conservative event linking and
independent-source corroboration. No user state yet.

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

- **The LLM extraction path is unexercised.** No `ANTHROPIC_API_KEY` was available, so
  the Claude adapter has only been tested against stubbed transports — malformed output,
  non-JSON, and absent credentials all degrade correctly, but no real model response has
  ever passed through it. **Extraction quality figures below describe the rule extractor
  only.**
- **Recall is modest.** On the 21-article fixture the rule extractor reaches 86% recall
  at 100% precision; across 167 live articles it classifies 48%. Misses are silent.
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

## Blocking, for a human

**No `ANTHROPIC_API_KEY` is configured.** The provider-isolated adapter is written and
its failure paths are tested, but no real extraction has run. Supplying a key and
re-running the evaluation is the single highest-value action available — it is the
difference between 48% classification and what a model can do with the same articles.

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
