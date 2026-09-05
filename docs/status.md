# Status

**Where the build is:** Step 0 complete and reviewed. The spine runs end to end against
the live exchange feed. No market data, no news, no LLM in the loop, no user state.

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

## Next — step 1, skeleton and truth

Market adapter, deterministic observations, corporate-action adjustment ordered before
baseline comparison (D14). Demoable: scenarios A and G. This also removes the
`NO_MARKET_OBSERVATION` coverage gap that currently pushes most verdicts to *unable to
evaluate*.

Then: evidence and events (D) → the engine (B, C, H) → user state → lifecycle and
summaries (E, F) → frontend. Scenario letters refer to the demo matrix in `DESIGN.md`.

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
   above that one session is not a reliability guarantee.
2. **LLM extraction quality on real news** — the next unproven thing, and it fails
   quietly rather than loudly. Validate on real articles in step 2 before building on it.
3. **Event linking tuning** — too conservative and scenario D shows duplicates, which is
   the aggregator behaviour the product claims to fix.
4. **No convincing RESOLVED example** may occur in the live window; seeded fixtures
   (D18) are the mitigation and must be built from step 2, not at the end.
5. **Frontend time** — J2 and J4 are non-negotiable, J8 search drops first. Less acute
   than it was: Step 0 shipped a working, if ugly, interface rather than deferring all
   of it to step 6.
