# One image, one process, one origin.
#
# The frontend is built and handed to the API to serve, so a deployment is a single unit
# with no cross-origin cookie configuration to get wrong. SQLite and the in-process
# scheduler both assume exactly one running container — see README, "Scheduler".

# --- build the frontend --------------------------------------------------------
FROM oven/bun:1 AS web
WORKDIR /src
COPY package.json bun.lock ./
COPY packages/web/package.json packages/web/
COPY packages/shared/package.json packages/shared/
COPY packages/mobile/package.json packages/mobile/
RUN bun install --frozen-lockfile
COPY packages/shared packages/shared
COPY packages/web packages/web
RUN cd packages/web && bun run astro build

# --- the application -----------------------------------------------------------
FROM python:3.14-slim
ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    WEB_DIST=/app/web \
    WATCHLIST_DB=/data/watchlist.db

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app

# Dependencies first, so a source change does not reinstall the world.
COPY packages/backend/pyproject.toml packages/backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY packages/backend/src ./src
COPY packages/backend/scripts ./scripts
RUN uv sync --frozen --no-dev
COPY --from=web /src/packages/web/dist /app/web

# The database lives on a volume. Without one, a restart starts from nothing —
# migrations would re-run on an empty file and every assessment would be gone.
VOLUME ["/data"]
EXPOSE 8000

# Liveness only. It says the process is up, never that a source is healthy — that is a
# domain verdict and it lives at /v1/scheduler and in each assessment's coverage.
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2).status==200 else 1)"

CMD ["uv", "run", "uvicorn", "smart_watchlist.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
