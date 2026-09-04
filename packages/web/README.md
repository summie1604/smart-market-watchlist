# @smart-market-watchlist/web

The frontend. Astro shell, statically or server-rendered; React islands only where
interaction genuinely demands them (DESIGN.md D2).

## Developing it

```bash
make install
make test
make run     # http://localhost:4321
```

## The boundary that matters

**This package reproduces no engine logic.** It renders attention levels, coverage
states and reason codes; it never computes one. Anything that decides what deserves
attention belongs in `packages/backend`.
