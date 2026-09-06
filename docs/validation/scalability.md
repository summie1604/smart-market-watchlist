# Scalability validation

Measured locally on `2026-09-06`. These numbers describe this machine and
the bounded domain/SQLite paths stated below; they are not production capacity claims.

## Target workload

- 10,000 active users, with at most 50 watched companies each.
- 50 covered securities in the next curated expansion.
- Up to 500 evidence records per ingestion cycle, every 15 minutes.
- Review assembly p95 below 300 ms at 50 companies.
- Stored chart transformation below 150 ms for one year of daily bars.

## Measured

| Path | Workload | Result | Target |
|---|---:|---:|---:|
| Review assembly | 500 sequential runs, 50 companies / 500 shared assessments | p50 0.18 ms · p95 0.19 ms | PASS (< 300 ms) |
| SQLite-backed review | 200 runs, including membership/checkpoint/assessment reads and issued-review write | p50 13.00 ms · p95 14.65 ms | PASS (< 300 ms) |
| Concurrent review assembly | 20 threads over the same shared intelligence | 4999.7 reviews/s | observation only |
| Rule extraction + grounding | 500 articles | 61990.8 articles/s | CPU floor only |
| Chart alignment + rebasing | 252 daily sessions x 3 series | 0.49 ms | PASS (< 150 ms) |

Peak resident memory for the validation process was **97.5 MiB**. This is
a process high-water mark, not memory attributable only to one operation.

## Exclusions and limits

- Source HTTP time, provider throttling and LLM latency are excluded. They dominate a live ingestion cycle, so this run does **not** prove that 500 live articles finish inside 15 minutes.
- The SQLite-backed review includes the persistence operations used by a request but not FastAPI/Pydantic serialization, a deployed HTTP server, TLS, process contention or device latency.
- The current product has nine curated companies and demonstration-scale accounts. The 50-company set here is synthetic and exercises algorithmic shape, not coverage quality.
- SQLite multi-writer contention is not exercised. D10's migration triggers remain multiple app instances, sustained concurrent writers or measured lock contention.

## Recommendation

The per-user read path is cheap enough that user count alone does not justify Postgres,
Redis or a queue. Measure one complete live 500-article cycle next. Split ingestion into
workers only if it cannot finish within the 15-minute interval; move from SQLite only
when a stated D10 trigger is observed.

## Evidence-based production path

1. Keep SQLite and the in-process scheduler for one application instance. Source-native
   evidence ids, stable event ids, upserted market bars and the single-cycle lock make
   retries idempotent at this scale.
2. Move to Postgres only after measured lock contention, sustained concurrent writers,
   multiple application instances, or a deployment that cannot use a durable local file.
   Preserve the existing uniqueness constraints and repository boundary during migration.
3. Move scheduling out of the web process when there is more than one web instance. Use
   one managed trigger or a leased job row keyed by source and time window; do not let every
   replica start the same cycle.
4. Add bounded workers or a queue only if a measured live cycle cannot finish inside 15
   minutes. Partition by company/source while retaining source-native idempotency keys.
5. Notifications do not exist today, so none can repeat. If introduced later, write a
   transactional outbox with a unique `(user, event, review window, channel)` key before
   delivery; a queue by itself does not prevent duplicate sends.
