# syntax=docker/dockerfile:1.7
#
# One image definition, two targets:
#   api   — FastAPI + the built SPA; what Cloud Run serves. Base deps only, so
#           cold starts stay fast.
#   jobs  — the same code plus the optimizer / scraping / ML extras; runs the
#           migrations and the scheduled syncs as Cloud Run Jobs (and locally
#           via compose).
#
# Build:  docker build --target api  -t fantasy-api  .
#         docker build --target jobs -t fantasy-jobs .

# ---- the SPA ------------------------------------------------------------------
FROM node:22.23.2-trixie-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- shared Python base ----------------------------------------------------------
FROM python:3.13.15-slim-trixie AS python
COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uv /bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH=/app/.venv/bin:$PATH
WORKDIR /app
RUN groupadd --system app && useradd --system --gid app --home-dir /app app

FROM python AS api-deps
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY backend/src ./src
COPY backend/alembic.ini ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM python AS jobs-deps
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --extra jobs --extra ml
COPY backend/src ./src
COPY backend/alembic.ini ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra jobs --extra ml

# ---- api ---------------------------------------------------------------------
FROM python AS api
COPY --from=api-deps /app /app
COPY --from=web /web/dist /app/web
ENV FRONTEND_DIST=/app/web \
    FANTASY_CACHE_DIR=/tmp/fantasy \
    HOST=0.0.0.0 \
    PORT=8080
USER app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/health', timeout=2)"]
CMD ["fantasy", "serve"]

# ---- jobs --------------------------------------------------------------------
FROM python AS jobs
COPY --from=jobs-deps /app /app
COPY backend/samples /app/samples
ENV FANTASY_CACHE_DIR=/tmp/fantasy
USER app
ENTRYPOINT ["fantasy"]
CMD ["--help"]
