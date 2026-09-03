# MarketMind AI — Deployment Guide

Practical steps to run MarketMind AI in a new environment. See
`docs/release/PRODUCTION_CONFIGURATION_GUIDE.md` for what every setting
means and `docs/release/RELEASE_CHECKLIST.md` before promoting any build.
§1-10 below cover the **backend** (unchanged since RC1); §11 covers the
**frontend**, new for v1.0.0.

## 1. Prerequisites

- Python 3.13+ (the project's own `pyproject.toml` pins `requires-python
  = ">=3.13"`).
- A reachable PostgreSQL server (every repository is Postgres-backed;
  the application starts without one but every dependent endpoint
  returns `503`).
- An Anthropic API key, if company research / portfolio intelligence
  (`CompanyResearchAgent`, `PortfolioIntelligenceAgent`) are needed — the
  application starts and everything else works without one; those two
  agents alone degrade to `503`.
- ChromaDB, if knowledge-hub-backed features are needed — same
  graceful-degradation behavior.
- Docker, if using the provided `docker-compose.yml` rather than running
  directly.

## 2. Install

```bash
cd backend
pip install -c requirements.lock -e .   # -c pins every transitive dep to a known-good set
pip install --group dev                 # test/lint tooling, not required to run the app
```

`backend/requirements.lock` is the pinned dependency set (see
`docs/decisions/0003-*`). The production `backend/Dockerfile` installs
with the same `-c requirements.lock`, so image rebuilds resolve to
identical versions. **After an intentional dependency change**,
regenerate it: `pip freeze` inside a healthy container, delete the
`marketmind-backend @ file://` self-reference line, and commit the diff.

## 3. Configure

```bash
cp .env.example .env
# edit .env — see PRODUCTION_CONFIGURATION_GUIDE.md for every field
```

At minimum for a real deployment: `SECRET_KEY` (auth token signing —
**must** be changed from the development default), `DATABASE_URL` (or
the individual `POSTGRES_*` fields), `ANTHROPIC_API_KEY` (if company
research/portfolio intelligence are needed), `ALLOWED_ORIGINS` (your
actual frontend origin(s), not `localhost`).

## 4. Run migrations

```bash
alembic upgrade head
alembic current   # should report 0005_ci_persistence (head)
```

Migrations are async and idempotent — see
`docs/database/MIGRATIONS.md` and
`tests/operations/test_alembic_environment.py` for the exact behavior
this is tested against (a real upgrade/downgrade cycle, not just a
syntax check).

## 5. Start the application

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Or via the provided `docker-compose.yml` at the repo root:

```bash
docker compose up --build
```

On startup, `app.lifespan.lifespan` runs
`app.bootstrap.bootstrap_application_state` — every repository/service
this application depends on is constructed once, here, and every
optional external dependency (ChromaDB, Anthropic, a real embedding
provider) that isn't reachable degrades to `None`/unused rather than
crashing startup. Check the structured startup log
(`bootstrap_completed`, `startup_validation_passed`) for what actually
came up.

## 6. Verify

```bash
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/ready
curl http://localhost:8000/openapi.json | jq '.paths | keys | length'   # expect 49
```

`GET /ready` returns `503` (with `data.blocking_issues` populated) if
any *required* repository/service isn't reachable — the conventional
readiness-probe contract most orchestrators expect. `GET /health`
always returns `200` with the actual state in the body, even when
degraded — use `/ready`, not `/health`, for a load balancer's health
check.

## 7. WebSocket connectivity

`/ws` requires the same reverse proxy/load balancer to support WebSocket
upgrade (the `Upgrade: websocket` header) — a plain HTTP-only proxy
config will reject the handshake. Test with:

```bash
# any WebSocket client, e.g. websocat
websocat "ws://localhost:8000/ws?token=<a real access token>"
```

## 8. Reverse proxy / TLS

This application does not terminate TLS itself — deploy behind a reverse
proxy (nginx, an ALB/NLB, etc.) that does. Once the deployment is
genuinely served over HTTPS, enable HSTS
(`SECURITY_HEADERS_HSTS_ENABLED=true`) — it is disabled by default
because sending it over plain HTTP is actively wrong (see
`docs/release/SECURITY_CONSIDERATIONS.md`).

## 9. Scaling

The application is stateless at the HTTP-request level and safe to run
as multiple replicas **except** for one component: `/ws`'s
`ConnectionManager` is in-process, in-memory only (Sprint 59's own
explicit constraint — no Kafka/RabbitMQ/Redis Streams). A client
connected to replica A never sees an event published by replica B. If
horizontal scaling is required, either sticky-session WebSocket traffic
to one replica, or wait for the distributed event bus integration point
`docs/architecture/WEBSOCKET_FRAMEWORK.md` §9 describes.

## 10. Shutdown

`app.bootstrap.shutdown_application_state` runs on every graceful
shutdown (`SIGTERM`, or exiting a `TestClient` context) — releases the
scheduler and any held resources. Standard `uvicorn`/orchestrator
graceful-shutdown handling (SIGTERM, drain, then SIGKILL after a grace
period) applies; no custom shutdown hook is required beyond what
`app.main:app`'s lifespan already provides.

## 11. Frontend (v1.0.0)

The frontend is a static single-page app — there is no server process
to run, only static files to build once and serve forever (until the
next deployment). `frontend/Dockerfile` (multi-stage: Node build →
nginx serve) and `frontend/nginx.conf` are the reference implementation;
adapt them to your own static hosting if you're not using Docker (any
static host that supports an SPA fallback route works — S3+CloudFront,
Netlify, Vercel's static mode, a plain nginx/Apache server, etc.).

### 11.1 The critical distinction: build-time, not runtime

Unlike every backend setting, `VITE_API_BASE_URL`/`VITE_WS_BASE_URL`
are compiled into the JS bundle when `npm run build` (or the Docker
image build) runs — **not** read when the container starts or a
request arrives. A different backend URL means rebuilding the frontend
with different values, full stop. See
`docs/release/PRODUCTION_CONFIGURATION_GUIDE.md`'s Frontend section for
the full explanation, and `src/services/api/config.ts` for what happens
if they're missing or malformed (a clear thrown error, visible in the
browser console, the instant the page loads).

### 11.2 Build and run via Docker

```bash
cd frontend
docker build \
  --build-arg VITE_API_BASE_URL=https://api.example.com/api/v1 \
  --build-arg VITE_WS_BASE_URL=wss://api.example.com/ws \
  -t marketmind-frontend .
docker run -p 8080:8080 marketmind-frontend
```

Or, to build and run the whole stack (Postgres/Redis/ChromaDB + backend
+ frontend) together for a local "production-like" test:

```bash
cp .env.example .env   # fill in real values
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend alembic upgrade head
```

This is additive to, not a replacement for, the plain
`docker compose up -d` command documented in `README.md`/
`docs/release/INSTALLATION_GUIDE.md` for local development (infra
containers only, backend/frontend run natively) — running the `-prod`
overlay never changes what the plain command does.

### 11.3 Build and serve without Docker

```bash
cd frontend
npm ci
VITE_API_BASE_URL=https://api.example.com/api/v1 \
VITE_WS_BASE_URL=wss://api.example.com/ws \
npm run build
# serve the frontend/dist directory with any static file server that
# supports an SPA fallback (unknown paths -> index.html) — see
# frontend/nginx.conf for the reference config to translate to your
# own server.
```

### 11.4 Reverse proxy / TLS

Same requirement as the backend (§8): this container does not terminate
TLS — put it behind a reverse proxy/load balancer that does, and add
`Strict-Transport-Security` there once genuinely served over HTTPS
end-to-end. See `docs/release/SECURITY_REVIEW_V1.md` for the full
frontend security review, including a ready-to-adapt
`Content-Security-Policy` value.

### 11.5 Verify

Open the deployed URL in a browser — it should redirect to `/login` and
show no errors in the console. If it shows a blank page with a thrown
error instead, `VITE_API_BASE_URL`/`VITE_WS_BASE_URL` were missing or
malformed at build time — rebuild with correct values (§11.1).
