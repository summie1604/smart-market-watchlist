"""FastAPI application.

Every ownership check lives at this boundary or deeper — never in the frontend
(DESIGN.md, *State*).
"""

from fastapi import FastAPI

app = FastAPI(title="Smart Market Watchlist", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check. Says nothing about source coverage — that is a domain verdict."""
    return {"status": "ok"}
