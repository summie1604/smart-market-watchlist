# smart-market-watchlist (backend)

Ingestion, the Meaningful Change Engine, and the API.

## Developing it

```bash
make install
make test
make lint
```

## Running it

```bash
make run     # http://localhost:8000
```

`WATCHLIST_DB` sets the SQLite path (default `watchlist.db`); see
[Configuration](../../README.md#configuration).

## Layout

- `src/smart_watchlist/core/` — the engine. Pure logic, no I/O assumptions, no framework
  imports. Never imports from `api/`.
- `src/smart_watchlist/api/` — thin HTTP shell over core.
- `tests/` — the engine is testable without a UI, a model or a network.

Module responsibilities and their contracts are in [DESIGN.md](../../DESIGN.md) under *Shape*.
