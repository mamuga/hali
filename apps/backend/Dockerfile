# ── Stage 1: dependency builder ───────────────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /build

# System deps required to compile rasterio, asyncpg, shapely, psycopg C extensions
# libeccodes-dev is required by cfgrib/eccodes to parse GloFAS GRIB2 forecasts
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ \
    libgdal-dev libgeos-dev libproj-dev \
    libeccodes-dev \
    libpq-dev \
    curl \
  && rm -rf /var/lib/apt/lists/*

ENV POETRY_VERSION=2.4.1 \
    PYTHONUNBUFFERED=1 \
    PATH="/root/.local/bin:$PATH"

RUN pip install "poetry==$POETRY_VERSION"

# Copy lockfiles first — maximise layer cache
COPY apps/backend/pyproject.toml apps/backend/poetry.lock ./

RUN poetry config virtualenvs.create false \
  && poetry install --only main --no-interaction --no-root

# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

WORKDIR /app

# Runtime shared libraries needed by rasterio, asyncpg, psycopg
# libeccodes0 is required by cfgrib/eccodes to parse GloFAS GRIB2 forecasts
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgdal-dev \
    libgeos-c1v5 \
    libproj-dev \
    libeccodes0 \
    libpq5 \
    curl \
  && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.13/site-packages \
                    /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source
COPY apps/backend/src ./src
COPY apps/backend/alembic ./alembic
COPY apps/backend/alembic.ini ./alembic.ini

ENV PYTHONPATH=/app/src
ENV PORT=8000

EXPOSE $PORT

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:$PORT/health || exit 1

CMD uvicorn hali.main:app \
    --host 0.0.0.0 \
    --port $PORT \
    --workers 1 \
    --log-level info
