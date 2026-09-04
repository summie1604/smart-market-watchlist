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
