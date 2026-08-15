# MarketMind AI — Operational Runbook (RC1)

Day-to-day operational procedures. See `docs/release/DEPLOYMENT_GUIDE.md`
for first-time setup and `docs/release/RELEASE_CHECKLIST.md` before any
deployment.

## Health & readiness

- `GET /api/v1/health` — always `200`, body's `data.state` is
  `HEALTHY`/`DEGRADED`/`UNHEALTHY`. Use for dashboards/observability, not
  as a load-balancer health check (it never fails the HTTP status itself).
- `GET /api/v1/ready` — `200` if ready to serve traffic, `503` (with
  `data.blocking_issues` populated) if not. **Use this for your load
  balancer's health check.**
- Both reuse `HealthCheckService` (Sprint 54) against every repository's
  own `health_check()` and every constructed service — no separate
  monitoring logic to maintain.

## Diagnosing a `DEGRADED`/`UNHEALTHY` state

1. `GET /api/v1/health`, inspect `data.repositories`/`data.services`/
   `data.dependencies` for which specific component reported the problem.
2. Cross-reference against `docs/release/PRODUCTION_CONFIGURATION_GUIDE.md`
   — a `None` service almost always means its underlying settings/external
   dependency (PostgreSQL, ChromaDB, Anthropic) is unreachable or
   misconfigured, not an application bug.
3. Check the structured startup log for `bootstrap_completed` /
   `startup_validation_passed` — `app.state.startup_validation_report`
   (also loggable on demand) lists exactly which `build_*` calls
   degraded to `None` and why.

## Logs

`app.state.structured_logger` (`StdlibStructuredLogger`, Sprint 54) wraps
the standard `logging` module — every log line is structured JSON with
`category` (`STARTUP`/`APPLICATION`/...), `event`, and `context`. Key
events to alert on:

- `bootstrap_completed` with `startup_validation_passed: false` — a
  required component failed to construct; investigate immediately, don't
  let traffic reach this instance.
- `unhandled_exception` (from `handle_unhandled_exception`) — always a
  bug or an unhandled edge case; the client only ever sees a generic
  500, so this log line is the *only* place the real cause is visible.
- `ws_send_failed_disconnecting` — a WebSocket connection died
  mid-broadcast; expected under normal client churn, alert only on an
  unusual spike (could indicate a network-layer problem between this
  instance and its clients).

## Metrics & profiling

`app.state.metrics_recorder` (`InMemoryMetricsRecorder`) and
`app.state.profiler` (`InMemoryProfiler`), Sprint 54 — every HTTP
request's duration and status code, and every `http.<METHOD>.<path>`
timing, are already recorded via `TimingMiddleware`. Both are in-process
only in RC1 (no Prometheus/StatsD exporter ships yet) — for production
observability, either scrape `app.state.metrics_recorder`'s own
snapshot via a future export endpoint, or run an APM agent alongside.

## Restarting / rolling deployment

Standard graceful shutdown: send `SIGTERM`, let in-flight requests
drain, then terminate. `app.bootstrap.shutdown_application_state` runs
automatically on lifespan exit. **`/ws` connections do not survive a
restart** — clients must reconnect and re-subscribe; there is no session
resumption or missed-event replay (Sprint 59's own explicit constraint).
If running multiple replicas, restart one at a time behind your load
balancer's readiness check (`/ready`) rather than all at once.

## Scheduled workflows & operational scripts (Milestones 11-16)

Post-v1.0.0 work added several background schedules (each gated by its
own `*_ENABLED` setting — see `docs/release/PRODUCTION_CONFIGURATION_GUIDE.md`)
and matching container-exec-only operational scripts (no HTTP admin
endpoint exists for any of these — reachable only by whoever can already
run a command inside the backend container):

| Schedule | Setting | Manual "run now" script |
|---|---|---|
| Market Intelligence Ingestion (M11) | `INGESTION_ENABLED` | `python scripts/run_ingestion.py` |
| Entity Resolution Backfill (M12) | manual only, no schedule | `python scripts/run_entity_backfill.py` |
| Market Data Refresh (M13) | `MARKET_DATA_ENABLED` (default `false`; separate from `MARKET_DATA_PROVIDER`/`MARKET_DATA_*` in the Configuration Guide, which configure the provider itself, not whether this schedule runs) | `python scripts/run_market_data_refresh.py` |
| Portfolio Intelligence Refresh (M14) | manual only, no schedule | `python scripts/run_portfolio_intelligence_refresh.py` |
| Continuous Intelligence (M15/M16) | `CONTINUOUS_INTELLIGENCE_ENABLED` | `python scripts/run_continuous_intelligence.py` |

Every manual trigger prints a JSON summary to stdout and exits non-zero
on fatal failure — safe to run against a live deployment; each shares the
same `Schedule.enabled` gate as its own scheduled cycle (a disabled
schedule cannot be run through either path).

**Read-only inspection** (Milestone 16 §15):
`python scripts/inspect_continuous_intelligence.py` — reports current
Continuous Intelligence comparison-state entries, suppression entries
(with remaining cooldown), the cycle lock's current claim
(held/stale/free), and overall scheduler health, without executing a
cycle or mutating anything. Reports `"status": "in_memory_only"` (not an
error) when no durable PostgreSQL repository is configured — see
`docs/architecture/CONTINUOUS_INTELLIGENCE_PERSISTENCE.md` §10-11.

Run any of the above via:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
    exec backend python scripts/<script_name>.py
```

## Database migrations in production

```bash
alembic upgrade head
```

Safe to run against a live database — the baseline migration uses
`checkfirst=True` (`CREATE TABLE IF NOT EXISTS` semantics) and is
idempotent (verified: `tests/operations/test_alembic_environment.py::test_upgrade_head_is_idempotent`).
Run migrations *before* deploying new application code that depends on
schema changes, never after.

## Common incidents

| Symptom | Likely cause | Where to look |
|---|---|---|
| `/ready` returns 503 | A required repository/service didn't construct | `/api/v1/health`'s `data.blocking_issues`, startup logs |
| `503` from a specific domain endpoint, everything else fine | That domain's service specifically failed to construct (e.g. `ANTHROPIC_API_KEY` unset → company research/portfolio intelligence only) | `docs/release/PRODUCTION_CONFIGURATION_GUIDE.md` |
| `401` on every request including previously-working ones | `SECRET_KEY` changed/rotated — every previously-issued token is now invalid | Confirm this was intentional (a rotation); if not, investigate why the secret changed |
| `/ws` clients silently stop receiving events after a deploy | Expected — connections don't survive a restart | Confirm clients reconnect + re-subscribe on disconnect (client-side responsibility) |
| A specific `/api/v1` client suddenly gets `422` on requests that used to work | A client bug (sending a now-extra field, wrong type) — the contract is frozen, this application did not change | Compare the failing request against `docs/release/API_CONTRACT_V1.md` |

## Escalation

There is no automated alerting/paging configured by this codebase
itself — wire your own alerting on top of the log events and `/ready`
status above; this is deployment-specific and out of RC1's scope.
