# LLM extraction harness

Run `2e79cbc5-e60c-4585-96cc-16a664fc0ca3` · expectation set `articles/2026-09-05` · 2026-09-05T20:47:39.629094+00:00

This is fixture performance, not live-ingestion performance. Every provider ran the same cases; results are never blended.

| Provider / model | Cases | Precision | Recall | Unsupported-field rate | Subject failures | Schema failures | Unusable | Fallbacks | Grounding drops | p50 / p95 | Tokens in / out | Estimated cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| rules / headline-vocabulary | 21 | 100.0% | 64.3% | 0.0% | 6 | 0 | 12 | 0 | 0 | 0.0 / 0.1 ms | not reported | not priced |

Contradiction gates: **4/4 cases passed**. These cases test the deterministic decision after a proposal; they are deliberately not credited to any model.

Raw provider output and per-case grounded results are retained only in the harness database. The harness never writes to the assessment store.
