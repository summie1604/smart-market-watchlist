# Smart Market Watchlist

A watchlist that answers *"what deserves my attention now?"* instead of *"what are my
stocks worth now?"* — it observes the information environment around the companies you
follow, decides what genuinely changed since your last review, and explains why.

Indian equities as the watchlist universe; global information as contextual evidence.

## Using it

Not yet deployed. Run it locally — see *Running it*.

## Developing it

```bash
make install    # backend (uv) + frontend (bun)
make test       # every package's tests
make help       # every target
```

The map is in [AGENTS.md](AGENTS.md). The product argument is in [VISION.md](VISION.md);
the architecture decisions, with their rejected alternatives, are in [DESIGN.md](DESIGN.md).
Read DESIGN.md before changing structure — it is frozen, and its decisions have reasons
that are not visible in the code.

## Running it

```bash
make run        # API and web dev server together
make run-api    # API only
make run-web    # web only
```

Local-first: SQLite, no external services required to start.

Ingestion is manual for now — with the API running:

```bash
curl -X POST localhost:8000/ingest
```

### Configuration

Both variables are optional. The defaults are what `make run` uses, so a fresh clone
needs no configuration at all.

| Variable | Package | Controls | Default | Override when |
|---|---|---|---|---|
| `WATCHLIST_DB` | `packages/backend` | Path to the SQLite file holding shared intelligence — assessments, evidence and ingest-run coverage | `watchlist.db` in the working directory | Running more than one instance, keeping a seeded demo database separate from a working one, or placing state outside the repo |
| `PUBLIC_API_BASE` | `packages/web` | Base URL the browser uses to reach the API | `http://localhost:8000` | Demoing from a machine other than the one serving the API, or running the API on a non-default port |

```bash
WATCHLIST_DB=./demo.db make run-api
PUBLIC_API_BASE=http://192.168.1.20:8000 make run-web
```

`PUBLIC_API_BASE` is **public frontend configuration**. Astro inlines any `PUBLIC_`
variable into the browser bundle, so its value is visible to anyone who loads the page.
It must never hold a secret, a token, or a credentialed URL.
