# smart_market_watchlist

An attention system for Indian equities: what meaningfully changed on your watchlist
since you last reviewed it, why it matters, and how confident we are.

## Map

| Path | What it is |
|---|---|
| packages/backend | Python: ingestion, the Meaningful Change Engine, API |
| packages/backend/src/smart_watchlist/core | The engine — pure logic, no I/O assumptions |
| packages/backend/src/smart_watchlist/api | Thin HTTP shell over core |
| packages/backend/src/smart_watchlist/evaluation | Isolated LLM and load validation harnesses |
| packages/web | Astro frontend; React islands only where interaction demands |
| packages/mobile | Thin Expo proof over the shared API; not a complete mobile product |
| packages/shared | Generated versioned API types and shared wire vocabulary |
| VISION.md | Product north star — read before changing product behaviour |
| DESIGN.md | Architecture decisions D1–D33 — read before changing structure |
| docs/status.md | Where the build actually is |

## Rules

- `make help` lists everything. `make install && make test` from a fresh clone.
- **DESIGN.md is frozen.** Implement against D1–D33. If implementation exposes a
  genuinely missing decision, record it there as a new decision — never decide
  silently in code. D20–D22 were added that way after Step 0, D23 after Step 1, D24–D25
  at the Step 2 handoff. D26–D33 cover the implemented product/platform foundation.
- The engine is deterministic. An LLM may extract, classify and phrase; it never
  owns prices, calculations, timestamps, provenance, checkpoints or rankings (D5).
- An attention level must carry the reason codes that produced it. If it cannot be
  explained, it cannot be ranked (D4).
- `core/` never imports from `api/`. Interface layers import from core only.
- Coverage state is a domain input, not logging — "nothing changed" and "we could not
  look" are different verdicts and must stay distinguishable (D15). **Capability tier
  never licenses a claim that the available evidence and coverage do not support.**
- Prose in docs and READMEs follows `aganitha-doc-writing`.

## Deeper

- Decisions and module contracts: DESIGN.md
- Current state and TODO: docs/status.md
