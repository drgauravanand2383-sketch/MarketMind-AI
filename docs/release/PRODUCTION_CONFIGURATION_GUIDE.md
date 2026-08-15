# MarketMind AI — Production Configuration Guide

Every setting the **backend** reads, grouped by the `pydantic_settings.BaseSettings`
class that owns it (`app/config/models.py`). Each class reads its own
`env_prefix` (or, for a few pre-Sprint-32 fields, no prefix — noted
below) from environment variables or `.env`. See `.env.example` for a
copy-pasteable starting point with every field already listed. The
**frontend**'s 2 settings are documented separately in §Frontend below —
a fundamentally different mechanism (build-time, not runtime).

## Application

No prefix. `ENVIRONMENT` (`development`/`staging`/`production` —
advisory only, checked by `ConfigurationValidationService`'s
`supported_value:environment` warning, never blocks startup), `DEBUG`,
`APP_NAME`, `APP_VERSION`, `LOG_LEVEL`.

## API server — `API_*`

`API_HOST` (default `0.0.0.0`), `API_PORT` (default `8000`),
`API_V1_PREFIX` (default `/api/v1` — changing this is a breaking change
to every documented URL; see `docs/release/API_VERSIONING_POLICY.md`),
`ALLOWED_ORIGINS` (comma-separated, **must** be your real frontend
origin(s) in production — the development default is `localhost:3000`).

## Security headers — `SECURITY_HEADERS_*` (Sprint 60)

| Variable | Default | Notes |
|---|---|---|
| `SECURITY_HEADERS_X_CONTENT_TYPE_OPTIONS` | `nosniff` | always sent |
| `SECURITY_HEADERS_X_FRAME_OPTIONS` | `DENY` | always sent |
| `SECURITY_HEADERS_REFERRER_POLICY` | `strict-origin-when-cross-origin` | always sent |
| `SECURITY_HEADERS_PERMISSIONS_POLICY` | `geolocation=(), microphone=(), camera=()` | always sent |
| `SECURITY_HEADERS_CONTENT_SECURITY_POLICY` | unset (no header sent) | **enable deliberately** — a strict CSP will break `/docs`/`/redoc` unless tuned for your own static asset hosting |
| `SECURITY_HEADERS_HSTS_ENABLED` | `false` | **enable only once genuinely served over HTTPS** — sending it over plain HTTP is actively wrong |
| `SECURITY_HEADERS_HSTS_MAX_AGE_SECONDS` | `31536000` (1 year) | only used if `HSTS_ENABLED=true` |
| `SECURITY_HEADERS_HSTS_INCLUDE_SUBDOMAINS` | `true` | only used if `HSTS_ENABLED=true` |

## Authentication & Authorization — `SECRET_KEY`/`ALGORITHM`/`ACCESS_TOKEN_EXPIRE_MINUTES` (no prefix) + `AUTH_*`

`SECRET_KEY` **must** be changed from `change-me-in-production` before
any real deployment — it signs every access/refresh token; a leaked or
guessable value is a full authentication bypass. `ALGORITHM` (default
`HS256`), `ACCESS_TOKEN_EXPIRE_MINUTES` (default `60`),
`AUTH_REFRESH_TOKEN_EXPIRE_MINUTES` (default `10080` = 7 days),
`AUTH_CLOCK_SKEW_TOLERANCE_SECONDS` (default `30`).

## PostgreSQL — `POSTGRES_*` / `DATABASE_URL`

Either set `DATABASE_URL` directly (`postgresql+asyncpg://user:pass@host:port/db`)
or the individual `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB`/
`POSTGRES_HOST`/`POSTGRES_PORT` fields — `PostgreSQLSettings` builds the
URL from them if `DATABASE_URL` is unset. `POSTGRES_PASSWORD` must not
be left at `change-me` in any real deployment.

## Redis — `REDIS_*`

Reserved for a future distributed rate-limiter/idempotency-store/event-bus
implementation — **not consumed by anything in this release**. RC1's
rate limiting and idempotency abstractions are interfaces only (Sprint
60's own explicit scope: "No Redis. No external implementation.");
`/ws`'s `ConnectionManager` is in-process only. Setting these variables
has no effect on RC1's actual behavior.

## ChromaDB — `CHROMA_*`

`CHROMA_HOST`, `CHROMA_PORT`, `CHROMA_PERSIST_DIRECTORY`. Missing/
unreachable ChromaDB degrades `knowledge_repository`/`knowledge_hub` to
`None` — company research and portfolio intelligence then return `503`,
nothing else is affected.

## Claude API — `ANTHROPIC_API_KEY` / `CLAUDE_MODEL`

`ANTHROPIC_API_KEY` has no default — required only for company research
and portfolio intelligence. Every other endpoint works without it.
`CLAUDE_MODEL` defaults to `claude-sonnet-5`.

## Scheduler — `SCHEDULER_*`

`SCHEDULER_ENABLED` (default `true`) — set `false` to disable the
background scheduling subsystem entirely (no `APSchedulerService`
constructed, no timer running).

## Ingestion & embeddings — `INGESTION_*` / `EMBEDDING_*` (Milestone 11)

| Variable | Default | Notes |
|---|---|---|
| `INGESTION_ENABLED` | `false` | Gates the scheduled Market Intelligence Ingestion cycle (RSS -> embed -> `KnowledgeRepository`). Same "off by default, never silently change an existing deployment's behavior" convention as every other milestone toggle below. |
| `INGESTION_INTERVAL_SECONDS` | `3600.0` | 1 hour. |
| `EMBEDDING_PROVIDER` | `local` | Only `local` is implemented; any other value degrades `embedding_provider` to unavailable (logged), which in turn degrades ingestion to unavailable — never crashes startup. |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Passed to the local embedding provider. |

## Entity Resolution — `ENTITY_RESOLUTION_*` / `ENTITY_MATCH_*` / `ENTITY_MAX_CANDIDATES` (Milestone 12)

| Variable | Default | Notes |
|---|---|---|
| `ENTITY_RESOLUTION_ENABLED` | `true` | Set `false` to disable entity resolution entirely (`entity_resolution_service` becomes `None` — ingestion/backfill/research all degrade gracefully, never crash). |
| `ENTITY_MATCH_HIGH_THRESHOLD` | `0.85` | Minimum score (after the ambiguity-margin check) for `ConfidenceTier.HIGH`. |
| `ENTITY_MATCH_MEDIUM_THRESHOLD` | `0.5` | Minimum score for `ConfidenceTier.MEDIUM`. |
| `ENTITY_MAX_CANDIDATES` | `5` | Maximum candidates returned per resolution. |
| `CANONICAL_ENTITIES_OVERLAY_PATH` | unset | Milestone 16 §8: optional path to a JSON file of *additional* real canonical companies, validated (collision + alias-governance checks) and merged into the base 12-company reference set at startup. Unset = no overlay, zero behavior change. See `docs/architecture/CONTINUOUS_INTELLIGENCE_PERSISTENCE.md` §8. |

## Live Market Data — `MARKET_DATA_*` (Milestone 13)

| Variable | Default | Notes |
|---|---|---|
| `MARKET_DATA_ENABLED` | `false` | Gates the *scheduled* Market Data Refresh cycle — separate from `MARKET_DATA_PROVIDER` below, which configures the provider itself regardless of whether the schedule runs. |
| `MARKET_DATA_PROVIDER` | `mock` | Set `yahoo_finance` for real live prices (Yahoo Finance's public, unauthenticated chart endpoint — no API key). `mock` is safe for any environment without real network access. |
| `MARKET_DATA_TIMEOUT_SECONDS` | `10.0` | Per-request HTTP timeout. |
| `MARKET_DATA_RETRY_ATTEMPTS` | `1` | Retries on transient failure (timeout/connection/5xx/429), fixed backoff. |
| `MARKET_DATA_RETRY_BACKOFF_SECONDS` | `1.0` | Delay between retry attempts. |
| `MARKET_DATA_CACHE_TTL_SECONDS` | `60.0` | How long a fetched snapshot is served from cache before a fresh fetch is attempted. |

Milestone 16 §10 additionally tracks real, observed consecutive-failure
history on the Yahoo provider to report `DEGRADED`/`UNAVAILABLE` health
status (thresholds are code-level constants, not currently
environment-configurable — see
`app/providers/market_data/yahoo.py::YahooFinanceProviderConfig`).

## Continuous Intelligence — `CONTINUOUS_INTELLIGENCE_*` / significance thresholds (Milestone 15/16)

| Variable | Default | Notes |
|---|---|---|
| `CONTINUOUS_INTELLIGENCE_ENABLED` | `false` | Gates the scheduled proactive-detection cycle. |
| `CONTINUOUS_INTELLIGENCE_INTERVAL_SECONDS` | `900.0` | 15 minutes. |
| `MARKET_CHANGE_THRESHOLD` | `3.0` | Minimum \|change_percent\| for a market move to be significant. |
| `NEWS_SIGNIFICANCE_THRESHOLD` | `2` | Minimum newly-seen knowledge-record count since the last cycle. |
| `NEWS_HIGH_CONFIDENCE_THRESHOLD` | `0.75` | Confidence score an entity's evidence must *newly* cross. |
| `RECOMMENDATION_SCORE_DELTA_THRESHOLD` | `10.0` | Minimum score delta (0-100) when the recommendation type itself didn't change. |
| `STRATEGY_ALIGNMENT_DELTA_THRESHOLD` | `10.0` | Minimum alignment delta (0-100). |
| `CONTINUOUS_INTELLIGENCE_SUPPRESSION_COOLDOWN_MINUTES` | `60.0` | How long an identical change fingerprint is suppressed after being emitted once. |
| `CONTINUOUS_INTELLIGENCE_LOCK_TTL_SECONDS` | `300.0` | Milestone 16 §5/§6: how long a cross-process cycle-lock claim is honored before being treated as abandoned and automatically reclaimed. Must comfortably exceed one real cycle's duration (observed ~90-100s for 12 canonical entities) — a value shorter than actual cycle time risks two cycles overlapping via the stale-reclaim path. |

Persistence for Continuous Intelligence's own state/suppression/locking
(Milestone 16) requires no separate configuration — it reuses the same
`DATABASE_URL`/`POSTGRES_*` settings above, falling back to in-memory
(same-process-only, restart-unsafe) automatically if PostgreSQL is
unreachable at startup. See
`docs/architecture/CONTINUOUS_INTELLIGENCE_PERSISTENCE.md`.

## RSS — `RSS_*`

Feed URLs for `NewsCollectorAgent`. Empty by default — the agent
constructs successfully either way; an empty feed list just means
nothing to collect.

## Frontend

Unlike every setting above, the frontend's 2 environment variables are
read at **build time**, not at container/process start — Vite compiles
`import.meta.env.VITE_*` references directly into the static JS bundle
when `npm run build` (or the Docker image build) runs. Setting them on
an already-built container or server has no effect; a different value
means a different build.

| Variable | Required | Default (dev only) | Notes |
|---|---|---|---|
| `VITE_API_BASE_URL` | Yes, in production | `http://localhost:8000/api/v1` | Must be the browser-reachable URL of the backend's `/api/v1` — not a Docker-internal service name (the browser loading the page is not inside your container network). |
| `VITE_WS_BASE_URL` | Yes, in production | `ws://localhost:8000/ws` | Same origin as `VITE_API_BASE_URL` in almost every real deployment, just `ws(s)://` instead of `http(s)://` and pointed at `/ws` instead of `/api/v1`. |

**Validation**: `src/services/api/config.ts`'s `validateRequiredUrl` runs
the moment the bundle's entry module evaluates (i.e. the instant the
page loads in a browser). In dev mode, an unset value silently falls
back to the local backend dev server default above — zero-config
`npm run dev`. In a production build, an unset value, a malformed URL,
or a URL using the wrong protocol (`VITE_API_BASE_URL` must be
`http:`/`https:`; `VITE_WS_BASE_URL` must be `ws:`/`wss:`) throws a
clear, specific error immediately — visible in the browser console —
rather than the app silently shipping requests to the wrong place or a
`localhost` that doesn't exist in this deployment.

**No separate frontend authentication configuration exists.**
Authentication is just HTTP calls (`POST /auth/login`, `POST
/auth/refresh`, `/ws?token=...`) against the two URLs above — there is
no client id/secret, OAuth config, or third-party auth provider on the
frontend side. Validating `VITE_API_BASE_URL`/`VITE_WS_BASE_URL` *is*
validating the frontend's authentication configuration; there is
nothing further to check.

**Setting them**: see `frontend/.env.example` for local `npm run
build`/`npm run dev`, or pass `--build-arg VITE_API_BASE_URL=... 
--build-arg VITE_WS_BASE_URL=...` to `docker build` (see
`frontend/Dockerfile`'s own header comment) — or, via
`docker-compose.prod.yml`, set them in `.env` at the repo root before
running `docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build`.

## What is *not* configurable in RC1

- Rate limiting: no concrete limiter ships, so there is nothing to tune
  (limits, windows) yet — see `app.api.rate_limiting`'s own module
  docstring.
- Idempotency: no concrete store ships, so there is no TTL/eviction
  policy to configure yet.
- `/ws` heartbeat interval: client-driven (the client decides how often
  to ping), not server-configurable — see
  `docs/architecture/WEBSOCKET_FRAMEWORK.md` §7.
