# MarketMind AI — Administrator Guide (v1.0.0)

Operating a running deployment. For getting one running in the first
place, see `docs/release/DEPLOYMENT_GUIDE.md`.

## Health and readiness

- `GET /api/v1/health` — always `200`; the response body reports the
  actual state of every repository/service/dependency
  (`HEALTHY`/`DEGRADED`/`UNHEALTHY`). Check this to see *what* is
  degraded, not *whether* to route traffic.
- `GET /api/v1/ready` — `200` once every *required* dependency is
  reachable, `503` (with `data.blocking_issues` listing exactly what's
  missing) otherwise. This is the one to point a load balancer's
  health check at.
- `GET /api/v1/version` — static version identifiers
  (`application_version`, `api_version`, `environment`) for confirming
  what's actually deployed.
- Frontend: the site-wide connectivity banner (visible on every page,
  not just the dashboard) shows offline/degraded state to every signed-in
  user automatically — no separate admin-only health page exists on the
  frontend.

## Logs

Every backend log line is a structured JSON record
(`app/operations/logging/logger.py`) — `category`, `level`, `event`,
and arbitrary `context` fields, plus a timestamp. Key events to know:

- `bootstrap_completed` / `startup_validation_passed` — on every
  process start; check this first after a deploy or restart.
- `http_request_completed` — one per request (method, path, status
  code, request id) — the primary source for request-level debugging.
- `ws_message_handling_failed` / `ws_send_failed_disconnecting` —
  WebSocket-specific failure events.

Frontend errors caught by the app's error boundaries log to the
browser's own console (`[ErrorBoundary] ...`) — there is no server-side
aggregation of frontend errors (no telemetry vendor is wired up, by
design — see `docs/release/OBSERVABILITY_VERIFICATION.md`). If a user
reports a broken page, ask them to check their browser console or send
a screenshot of it.

## Users, roles, and permissions

Every protected endpoint requires a specific permission string,
evaluated via policy-based authorization
(`docs/architecture/AUTHENTICATION_ARCHITECTURE.md`). There is **no
admin UI for user/role/permission management in v1.0.0** — provisioning
a user (and their role/permission set) is a direct database or seeding-
script operation, not something exposed through the REST API or
frontend. Plan for this operationally: onboarding a new user is a
backend/ops task, not a self-service one.

## Secrets and rotation

- `SECRET_KEY` signs every access/refresh token. Rotating it
  **invalidates every currently-issued token** — every signed-in user
  is logged out. There is no token revocation list, so this is also
  the only way to forcibly end every session at once (e.g. if a leak is
  suspected).
- `POSTGRES_PASSWORD`/`REDIS_PASSWORD`/`ANTHROPIC_API_KEY` — rotate via
  your usual secrets-management process, then restart the backend
  (these are read once at process start, not re-read live).
- The frontend has no secrets of its own to rotate — see
  `docs/release/SECURITY_REVIEW_V1.md`'s Client-side secret handling
  section.

## Database

- Migrations: `alembic upgrade head` — always run before deploying
  application code that depends on the new schema, never after or
  automatically on container start (neither Dockerfile in this repo
  runs migrations on `CMD`).
- Backups: standard PostgreSQL backup/restore practice (`pg_dump`/
  `pg_restore`, or your managed database provider's own snapshot
  mechanism) — this application does not provide its own backup
  tooling, and Milestone 17 does not introduce any managed backup
  infrastructure. The procedure below is the exact sequence verified
  live during Milestone 17's own release-hardening pass (real dump,
  real restore into a separate database, real application startup
  against the restored copy — not a syntax check).

  **Create a backup** (custom format, compressed, portable across
  PostgreSQL versions via `pg_restore`):
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.prod.yml \
      exec postgres pg_dump -U marketmind -d marketmind -Fc \
      -f /tmp/marketmind_backup.dump
  docker cp marketmind-postgres:/tmp/marketmind_backup.dump ./marketmind_backup.dump
  ```
  Store `marketmind_backup.dump` somewhere durable *outside* the Docker
  host (the named `postgres_data` volume and the host filesystem can
  fail together) — this application does not do that for you.

  **Restore to a clean instance** (verify a backup is actually usable
  *before* you need it — restoring to a scratch database, never
  directly overwriting a live one):
  ```bash
  # Against a fresh/scratch PostgreSQL instance:
  createdb -U marketmind marketmind_restore_check
  pg_restore -U marketmind -d marketmind_restore_check --no-owner --no-privileges \
      ./marketmind_backup.dump
  ```
  Then confirm two things before trusting the backup:
  1. **Alembic state is correct**: `SELECT version_num FROM alembic_version;`
     must show your expected head revision (`0005_ci_persistence` as of
     Milestone 16) — a dump taken mid-migration or from an
     inconsistent snapshot would show something else or fail to restore
     at all.
  2. **The application actually starts against it**: point `DATABASE_URL`
     at the restored database and run any read-only operational script,
     e.g. `DATABASE_URL=postgresql+asyncpg://... python
     scripts/inspect_continuous_intelligence.py` — a clean JSON report
     (not a bootstrap traceback) confirms every repository/service
     constructs correctly against the restored schema and data, not just
     that the SQL replayed without error.

  **Recovery** (restoring a live deployment after real data loss): stop
  the backend (so nothing writes during restore), restore the dump into
  the real `postgres_data`-backed database exactly as above but pointed
  at the live instance, run `alembic current` to confirm the head
  matches what the running application code expects, then start the
  backend. If the backup predates the current application version's
  migrations, run `alembic upgrade head` before starting the backend —
  never after.
- `alembic downgrade <revision>` is supported for every revision but is
  destructive to any data added since — a last resort, not routine
  rollback (`docs/release/UPGRADE_POLICY.md`).

## Scheduled workflows & operational scripts

Post-v1.0.0 (Milestones 11-16) added background schedules (Ingestion,
Market Data Refresh, Continuous Intelligence, ...) and matching
container-exec-only manual-trigger/diagnostic scripts, including
`scripts/inspect_continuous_intelligence.py` (read-only — safe to run
any time). See `docs/release/OPERATIONAL_RUNBOOK.md`'s "Scheduled
workflows & operational scripts" section for the full list, settings,
and usage.

## Restarting / scaling

The application is stateless at the HTTP-request level and safe to run
as multiple replicas **except** `/ws`'s `ConnectionManager`, which is
in-process/in-memory only — a client connected to replica A never sees
an event from replica B (`docs/release/KNOWN_LIMITATIONS.md`). If you
scale horizontally, either use sticky sessions for WebSocket traffic or
accept this limitation until a distributed event bus is added.

Restarting the backend disconnects every WebSocket client — the
frontend's `WebSocketClient` reconnects automatically with exponential
backoff; no manual client-side action is needed after a routine
restart.

## Rate limiting and abuse

Not enforced by this application in v1.0.0 (interfaces only — see
`docs/release/SECURITY_CONSIDERATIONS.md` and
`docs/release/KNOWN_LIMITATIONS.md`). If this deployment is
internet-facing, put rate limiting at the edge (reverse proxy, API
gateway, WAF) — do not assume the application protects itself.

## Rollback

See `docs/release/RELEASE_CHECKLIST_V1.md`'s Rollback plan section.
