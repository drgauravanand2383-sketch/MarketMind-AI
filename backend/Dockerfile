# MarketMind AI Backend — production image.
#
# Unlike the frontend, every setting here is read at *container start*
# (or per-request) from the environment — see
# docs/release/PRODUCTION_CONFIGURATION_GUIDE.md. No build-time secrets
# or URLs are baked into this image; the same image runs in any
# environment given the right env vars / `.env` file.

FROM python:3.13-slim AS build
WORKDIR /app

# Build tooling for packages with native extensions (e.g. asyncpg) —
# not needed in the final runtime image, kept only in this stage.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY app ./app

# A regular (non-editable) install into a venv — nothing in this stage
# ships in the final image except the venv's installed site-packages.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

FROM python:3.13-slim AS production
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* && \
    useradd --create-home --shell /bin/false appuser

COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts

# Pre-create the ChromaDB persistence directory so it exists (owned by
# appuser) inside the image before docker-compose.prod.yml's named volume
# is first mounted here — an empty named volume is initialized from the
# image's directory at that path, ownership included; without this the
# volume's mount point is created by the daemon as root and appuser can't
# write to it.
RUN mkdir -p /app/data/cache && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# --timeout=15s (was 5s) and --retries=5 (was 3): this is a single-worker
# uvicorn process (no --workers flag below) sharing one event loop between
# request handling and its own heavy autonomous background work (hourly
# ingestion, hourly market-data refresh, 15-min Continuous Intelligence
# cycles) — real, observed live: a busy stretch left the app unresponsive
# to new connections for up to ~1.5-2 minutes (entity-resolution/embedding
# CPU work plus an upstream Yahoo Finance retry/failure), which the
# previous 5s timeout / 3 retries (90s total tolerance) flagged unhealthy
# even though the process was never crashed or stuck — it recovered and
# kept serving requests throughout. 15s x 5 retries = up to ~2.5 minutes of
# consecutive failures tolerated (interval unchanged at 30s), enough to
# ride out that kind of transient busy period without masking a genuine
# outage (still bounded, still fails fast for something actually down).
# --start-period=40s (was 15s): matching slack for a cold container whose
# first request may race a scheduled job through the same startup window.
HEALTHCHECK --interval=30s --timeout=15s --start-period=40s --retries=5 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Migrations (`alembic upgrade head`) are a separate, explicit step —
# see docs/release/DEPLOYMENT_GUIDE.md §4 — never run automatically on
# container start, so a bad migration never silently blocks or corrupts
# a rolling deployment.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
