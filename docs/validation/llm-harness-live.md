# LLM extraction harness

Run `f6941998-47f3-4b2f-afb3-acb060bf7eb4` · expectation set `articles/2026-09-05` · 2026-09-05T20:31:41.775595+00:00

This is fixture performance, not live-ingestion performance. Every provider ran the same cases; results are never blended.

| Provider / model | Cases | Precision | Recall | Unsupported-field rate | Subject failures | Schema failures | Unusable | Fallbacks | Grounding drops | p50 / p95 | Tokens in / out | Estimated cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| rules / headline-vocabulary | 21 | 100.0% | 64.3% | 0.0% | 6 | 0 | 12 | 0 | 0 | 0.0 / 0.1 ms | not reported | not priced |
| google / gemini-3.6-flash | 21 | n/a | 0.0% | n/a | 0 | 0 | 21 | 0 | 0 | 291.5 / 544.7 ms | not reported | not priced |
| pipeline:google / gemini-3.6-flash | 21 | 100.0% | 64.3% | 0.0% | 6 | 0 | 12 | 21 | 0 | 291.8 / 509.8 ms | not reported | not priced |

Contradiction gates: **4/4 cases passed**. These cases test the deterministic decision
after a proposal; they are deliberately not credited to any model.

## Live-ingestion context

This run is the fixed, designed fixture and must not be read as live accuracy. The latest
separately observed quota-exhausted ingestion accepted 119 events and refused 411 articles:
146 because the subject was not named in the headline, 150 because no event type was
recognised, 42 outside the leading clause, 36 named as a counterparty, 36 market roundups
and one relationship mention. Those counts measure operational coverage on that feed; they
do not have human labels, so precision and recall cannot honestly be calculated for them.

Raw provider output and per-case grounded results are retained only in the harness database. The harness never writes to the assessment store.
