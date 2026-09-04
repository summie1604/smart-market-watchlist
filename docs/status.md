# Status

**Where the build is:** scaffolded. No engine, no adapters, no UI yet.

## Done

- `VISION.md` — product vision, frozen.
- `DESIGN.md` — 19 architecture decisions, frozen.
- Repo scaffold: monorepo layout, Makefile contract, backend and web packages.

## Next — Step 0, the disclosure spike

One authoritative disclosure travelling the full path:

```
external source → adapter → evidence → normalization → event candidate
→ provenance preserved → engine → persisted assessment → rendered in the UI
```

Success is **the architecture preserving provenance**, not any particular endpoint
responding. If the NSE endpoints prove unreliable, substitute another authoritative
source behind the same adapter contract.

The Step 0 UI is deliberately ugly — company, event, attention, confidence, reason
codes, coverage, source — and stays ugly through steps 1–5.

## Then

1. Skeleton and truth — market adapter, observations, corporate-action adjustment (A, G)
2. Evidence and events — news adapter, coverage ledger, LLM extraction, event identity (D)
3. The engine — relevance, corroboration, significance, attention (B, C, H)
4. User state — auth, watchlists, checkpoints, review window
5. Lifecycle and summaries — STALE-over-RESOLVED, persisted summaries (E, F)
6. Frontend — replacing the ugly Step 0 surface

Scenario letters refer to the demo matrix in `DESIGN.md`.

## Known risks

Ordered by how early they need validating — see `DESIGN.md` open questions.

1. No authoritative disclosure source works → kills the HIGH-confidence tier.
2. LLM extraction quality on real news is poor → degrades identity and relevance quietly.
3. Event linking tuning is harder than budgeted → duplicates in scenario D.
4. No convincing RESOLVED example occurs in the live window → seeded fixtures cover it.
5. Frontend consumes the remaining time → J2 and J4 are non-negotiable, J8 search drops first.
