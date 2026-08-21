# MarketMind AI — Production Operations & Recovery Runbook

For a non-developer operator running MarketMind AI's Docker production
stack on a Windows machine (Docker Desktop + WSL2). This document tells
you exactly what to run and what to expect — it does not re-explain
architecture or every configuration field.

**This is an operations runbook, not a design document.** For the "why"
behind anything below, follow the specific cross-reference given — most
of this document deliberately **points at**, rather than duplicates,
already-verified content in:

- `docs/release/OPERATIONAL_RUNBOOK.md` — health/logs/restart/scripts/migrations reference
- `docs/release/ADMINISTRATOR_GUIDE.md` — the tested backup/restore procedure this document reuses verbatim
- `docs/release/TROUBLESHOOTING_GUIDE.md` — symptom → cause table
- `docs/release/DEPLOYMENT_GUIDE.md` — first-time setup, environment variables, scaling
- `docs/release/PRODUCTION_CONFIGURATION_GUIDE.md` — every setting, its default, what it does
- `docs/release/SECURITY_CONSIDERATIONS.md` — auth, CORS, secrets, rate limiting
- `docs/release/UPGRADE_POLICY.md` — versioning scheme, migration policy
- `docs/release/KNOWN_LIMITATIONS.md` — deliberate scope boundaries
- `docs/architecture/CONTINUOUS_INTELLIGENCE_PERSISTENCE.md` — state/suppression/locking internals

**Verification basis**: every command in sections C–N below was executed
live against this deployment's actual running production stack
(`docker-compose.yml` + `docker-compose.prod.yml`, tag `v1.1.1`, Alembic
head `0005_ci_persistence`) on 2026-08-21, not copied from documentation
claims. Where a command could not be safely exercised against a live
system with real data, it is explicitly marked **NOT VERIFIED** rather
than assumed to work — see §Q's own note and each section's own marking.

---

## A. System overview

Five containers, one Docker bridge network (`marketmind-network`):

| Container | Image | Published port | Role |
|---|---|---|---|
| `marketmind-backend` | built from `backend/Dockerfile` | `8000` | FastAPI app (`/api/v1`, `/ws`) |
| `marketmind-frontend` | built from `frontend/Dockerfile` | `8080` | Static React SPA, served by nginx |
| `marketmind-postgres` | `postgres:16-alpine` | none (internal only) | Primary relational store |
| `marketmind-redis` | `redis:7-alpine` | none (internal only) | Provisioned, not yet consumed by any feature (`README.md`) |
| `marketmind-chromadb` | `chromadb/chroma:latest` | none (internal only) | Vector store for knowledge/research |

Postgres/Redis/Chroma are deliberately **not** published to the host —
verified live (§F) — only `backend` and `frontend` are reachable outside
the Docker network. See `docs/release/KNOWN_LIMITATIONS.md` for why
(an unpatched ChromaDB advisory, mitigated this way).

## B. Prerequisites

- **Docker Desktop** running (WSL2 backend on Windows — Docker Desktop
  manages this; you do not start WSL separately in normal operation).
- A shell: this document's commands are shown for **Git Bash /
  PowerShell** on Windows — both work; pick one and stay consistent
  within one session (path syntax differs, see §L).
- The repository checked out locally, with a real `.env` at its root
  (never committed — see §R). `cp .env.example .env` then fill in real
  values if this is a first-time setup (`docs/release/DEPLOYMENT_GUIDE.md` §3).
- You do **not** need Python, Node, or `uv` installed to operate the
  Docker stack day-to-day — only to develop against it natively.

---

## C. Daily startup

From the repository root:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

(Add `--build` only after pulling new code or changing a Dockerfile —
unnecessary, and slower, for a routine daily start of unchanged images.)

**Expected container states** (`docker compose -f docker-compose.yml -f
docker-compose.prod.yml ps`):

```
NAME                  STATUS
marketmind-backend    Up ... (healthy)
marketmind-chromadb   Up ...              <- no HEALTHCHECK defined; "Up" is the expected state, not "(healthy)"
marketmind-frontend   Up ... (healthy)
marketmind-postgres   Up ... (healthy)
marketmind-redis      Up ... (healthy)
```

`backend`/`frontend`/`postgres`/`redis` reach `(healthy)` within ~30-60s
(their `HEALTHCHECK`'s own `start-period`); `chromadb` has no
`HEALTHCHECK` directive at all (confirmed by reading `docker-compose.yml`)
— absence of a health column is expected, not a fault.

**Verify** (§F has the full set; minimum for "did it come up"):

```bash
curl http://localhost:8000/api/v1/health     # -> 200, "state": "HEALTHY"
curl http://localhost:8000/api/v1/ready      # -> 200, "ready": true
```

Open `http://localhost:8080` in a browser — it should redirect to
`/login`.

**Migrations**: a fresh database needs `alembic upgrade head` run once
(§H) — an *existing* deployment's data volume already has this applied;
routine daily startup does **not** require re-running it. Only run it
again after deploying new code that ships a new migration.

## D. Daily shutdown

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml stop
```

`stop` (not `down`) — sends `SIGTERM` to each container, same graceful
path `docs/release/OPERATIONAL_RUNBOOK.md`'s "Restarting / rolling
deployment" section describes (`app.bootstrap.shutdown_application_state`
runs; in-flight requests drain). Containers and their named volumes
remain on disk, ready for `up -d` again later — this is the safe,
routine shutdown.

**Do not** run `docker compose down -v` for a routine shutdown — `-v`
**deletes the named volumes**, i.e. your Postgres/Redis/Chroma data.
Reserve `down -v` for a deliberate, backed-up-first full reset (§O).

Every WebSocket client disconnects on shutdown and does not receive
events while stopped — expected, documented in
`docs/release/KNOWN_LIMITATIONS.md` (`/ws` has no message persistence or
replay). Nothing needs to be "resumed" — the frontend reconnects and
resyncs automatically on next connect.

## E. Restart after laptop reboot

After any of: Windows reboot, Docker Desktop restart, WSL restart,
unexpected power loss — none of these corrupt or lose your data (see
"What persists" below), but nothing restarts automatically unless Docker
Desktop is configured to.

1. **Open Docker Desktop** and wait for it to report "Engine running"
   (the whale icon in the system tray stops animating). This can take
   30-90 seconds after a fresh boot — a `docker` command run too early
   fails with a connection error (§O "Docker not found").
2. **Open a terminal, `cd` into the repository root.**
3. **Inspect containers**:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
   ```
   If Docker Desktop was configured to restart containers automatically,
   they may already be `Up`. If the list is empty or shows `Exited`,
   proceed to step 4.
4. **Start the stack if necessary** (§C):
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
   ```
5. **Verify health** (§F) — wait for all 4 healthchecked containers to
   report `(healthy)`, not just `Up`, before trusting the deployment.
6. **Verify migrations**:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend python -m alembic current
   ```
   Expect `0005_ci_persistence (head)`. A different value means the
   volume is from an older release — do not proceed without
   investigating (§P/§Q).
7. **Verify frontend**: open `http://localhost:8080`, confirm it loads
   and redirects to `/login`.
8. **Verify backend**: `curl http://localhost:8000/api/v1/ready` → `200`.
9. **Verify scheduler / Continuous Intelligence** (read-only, safe):
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend python scripts/inspect_continuous_intelligence.py
   ```
   Check the `"scheduler"` object: `"scheduler_running": true`. This
   confirms the in-process scheduler re-registered correctly after the
   restart — it does **not** mean Continuous Intelligence is enabled
   (check `"enabled_schedules"` against what you expect from
   `CONTINUOUS_INTELLIGENCE_ENABLED` in `.env`).

**What persists across any of the above** (Docker named volumes are
independent of the container lifecycle):

- `marketmind-ai_postgres_data` — all relational data (watchlists,
  portfolios, auth users, alerts, Continuous Intelligence state/
  suppression/lock rows, everything in the 24 tables under Alembic).
- `marketmind-ai_redis_data` — provisioned but not consumed by any
  current feature (§A); nothing operationally depends on this surviving.
- `marketmind-ai_chroma_data` — ingested knowledge/research vectors.
- `marketmind-ai_backend_chroma_cache` — the backend's own local
  Chroma cache directory (`/app/data/cache`) used by knowledge
  ingestion's embedding step.
- The Git repository and Docker images (once built) — both live on the
  host filesystem, untouched by a container restart.

**What does NOT persist**:

- **In-memory process state**: if Postgres was ever unreachable at a
  given startup, Continuous Intelligence's state/suppression/lock fall
  back to in-memory-only for that process (`CONTINUOUS_INTELLIGENCE_PERSISTENCE.md`
  §1) — a restart in that configuration loses it. With Postgres reachable
  (the normal case), this doesn't apply — state is durable.
- **Temporary container state**: anything written inside a container's
  own writable layer (not a named volume) — e.g. the ONNX embedding
  model cached at `~/.cache/chroma/onnx_models/` inside the backend
  container is **not** on the persistent volume (a known, documented
  characteristic — `docs/release/KNOWN_LIMITATIONS.md` Milestone 17
  section) and re-downloads (~79MB) on a freshly *recreated* container,
  not just an image rebuild. A first ingestion-related operation after
  a container recreation is correspondingly slower.
- **Browser session**: the frontend holds its access/refresh token in
  browser storage, not a cookie tied to the container — this survives a
  *backend* restart on its own, but not clearing browser data.
- **Every open `/ws` connection** — reconnects automatically
  (exponential backoff, `docs/release/TROUBLESHOOTING_GUIDE.md`).

---

## F. Health / diagnostics

All commands run from the repository root; all confirmed live against
this deployment (2026-08-21).

**Container status:**
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
```
Expect `backend`/`frontend`/`postgres`/`redis` each `Up ... (healthy)`;
`chromadb` `Up ...` (no healthcheck defined — this is normal, not a gap).

**Backend health** (always `200`; inspect the body for actual state):
```bash
curl http://localhost:8000/api/v1/health
```
Healthy response includes `"data":{"state":"HEALTHY", ..., "summary":"21/21 component(s) healthy"}`.

**Backend readiness** (the one to alert on — `503` means something
required is actually down):
```bash
curl -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8000/api/v1/ready
```
Expect `HTTP 200`.

**Frontend availability:**
```bash
curl -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8080/
```
Expect `HTTP 200`.

**Version currently running:**
```bash
curl http://localhost:8000/api/v1/version
```

**Backend logs** (last N lines, or follow with `-f`):
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=50 backend
```

**Frontend logs** (nginx access log — client-side JS errors are
**not** here, only in the browser's own console, per
`docs/release/ADMINISTRATOR_GUIDE.md`):
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=50 frontend
```

**PostgreSQL status:**
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec postgres pg_isready -U marketmind -d marketmind
```
Expect `/var/run/postgresql:5432 - accepting connections`.

**Redis status** — **important gotcha, verified live**: `$REDIS_PASSWORD`
is baked into the container's startup `command` at compose time, but is
**not** set as an environment variable inside the running container —
running `redis-cli -a "$REDIS_PASSWORD" ping` directly inside `exec`
fails with `WRONGPASS`/`NOAUTH`. Pass it in explicitly from your own
shell (which must have `.env` sourced or `REDIS_PASSWORD` exported):
```bash
export $(grep -E '^REDIS_PASSWORD=' .env | xargs)
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
    exec -e REDIS_PASSWORD="$REDIS_PASSWORD" redis sh -c 'redis-cli -a "$REDIS_PASSWORD" ping'
unset REDIS_PASSWORD
```
Expect `PONG`. **Never** paste the actual password value into a ticket,
log, or chat (§R).

**Chroma status** (no published port — reachable only from inside the
Docker network, so check it via the backend container):
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend curl -s http://chromadb:8000/api/v2/heartbeat
```
Expect `{"nanosecond heartbeat": <number>}`.

**Alembic current revision:**
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend python -m alembic current
```
Expect `0005_ci_persistence (head)`.

**Diagnosing a `DEGRADED`/`UNHEALTHY` `/health` response**: see
`docs/release/OPERATIONAL_RUNBOOK.md`'s own section of the same name —
not duplicated here.

---

## G. Logs

Covered above (§F). One addition specific to this runbook: to capture
logs *before* restarting a misbehaving container (so you don't lose the
evidence), always run the `logs` command first, optionally redirected to
a file:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=500 backend > backend_incident_log.txt
```

Do not paste raw log output into a public ticket/chat without first
scanning it — `RequestLoggingMiddleware` itself logs no secrets by
design (`docs/release/OPERATIONAL_RUNBOOK.md`), but a stack trace from
an unrelated bug could theoretically include unexpected local context.

---

## H. Database / migrations

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend python -m alembic upgrade head
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend python -m alembic current
```

- Safe to run against a live database — idempotent, verified by
  `tests/operations/test_alembic_environment.py::test_upgrade_head_is_idempotent`
  (`docs/release/OPERATIONAL_RUNBOOK.md`).
- **Always** run migrations *before* deploying new application code that
  depends on the schema change, never after.
- **Never** hand-edit an already-shipped migration file
  (`docs/release/UPGRADE_POLICY.md`) — if one is wrong, ship a new
  migration that corrects it forward.
- `alembic downgrade <revision>` exists but is destructive to any data
  added since — last resort, never routine (§P).
- Current head as of `v1.1.1`: `0005_ci_persistence`.

---

## I. News ingestion (Milestone 11)

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend python scripts/run_ingestion.py
```

| | |
|---|---|
| **Purpose** | Fetch configured RSS feeds (`RSS_FEED_URLS`), embed, and persist new knowledge records to ChromaDB. |
| **When to use** | On demand between scheduled runs, or to confirm the pipeline works right after a config change (e.g. adding a feed URL). Scheduled automatically every `INGESTION_INTERVAL_SECONDS` (default 3600s) when `INGESTION_ENABLED=true`. |
| **Success looks like** | Exit code `0`, JSON summary with `providers_succeeded`, `articles_fetched`, `embeddings_generated`, `articles_persisted`. |
| **Common failure** | `RSS_FEED_URLS` empty (`[]` by default — nothing to collect, not an error, exits `0` with zero counts) or `INGESTION_ENABLED` not `true` (exits `1`, `{"status": "disabled", ...}`). |
| **Changes data?** | **Yes** — writes new records to ChromaDB. |
| **Safe to rerun?** | Yes — idempotent upsert; overlapping/repeated runs are redundant, not harmful (`docs/release/KNOWN_LIMITATIONS.md`). |

**NOT independently re-executed this session** — this deployment is
live production; running ingestion here would insert real new data
outside this runbook-verification task's scope. Behavior above is
sourced directly from `backend/scripts/run_ingestion.py` and
independently confirmed live in `docs/release/RELEASE_CHECKLIST_V1_1.md`
§5/§8 (real RSS ingestion, 10 genuine live articles fetched, against
this same codebase).

## J. Entity resolution backfill (Milestone 12)

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend python scripts/run_entity_backfill.py [--dry-run] [--batch-size N]
```

| | |
|---|---|
| **Purpose** | Retroactively resolve canonical-company entities for already-ingested knowledge records. |
| **When to use** | After adding companies to the reference set (`CANONICAL_ENTITIES_OVERLAY_PATH`), or to catch up records ingested before entity resolution was enabled. |
| **Success looks like** | Exit `0`, JSON with per-confidence-tier counts (`resolved_high`/`resolved_medium`/`unresolved`, exact field names in `BackfillResult`). |
| **Common failure** | `ENTITY_RESOLUTION_ENABLED=false` or ChromaDB unreachable → `{"status": "unavailable", ...}`, exit `1`. |
| **Changes data?** | Yes, unless `--dry-run` (resolves and counts without writing). |
| **Safe to rerun?** | Yes — idempotent, single-process only (redundant if run concurrently, not harmful). |

**NOT independently re-executed this session** — same live-production
reasoning as §I. `--dry-run` is the safe way to preview impact before a
real run. Behavior confirmed live in `RELEASE_CHECKLIST_V1_1.md` §8 (28
real records processed: 7 HIGH, 1 MEDIUM, 20 correctly unresolved).

## K. Market data (Milestone 13)

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend python scripts/run_market_data_refresh.py
```

| | |
|---|---|
| **Purpose** | Refresh live market snapshots (price, change%, volume) for every canonical entity, via `MARKET_DATA_PROVIDER` (default `mock`; `yahoo_finance` for real data). |
| **When to use** | On demand between scheduled runs (default interval 3600s when `MARKET_DATA_ENABLED=true`), or to force-refresh before checking Recommendations. |
| **Success looks like** | Exit `0`, JSON with `fresh_count`/`stale_count`/`unavailable_count` and a `stale_or_unavailable` list naming exactly which symbols, if any. |
| **Common failure** | `MARKET_DATA_ENABLED` not `true` → `{"status": "disabled"}`, exit `1`. A `stale`/`unavailable` entity individually is not a script failure — the script itself still exits `0`; check the per-entity `reason`. |
| **Changes data?** | Yes — updates the in-memory market snapshot cache (`InMemoryMarketSnapshotCache`, lost on restart per `KNOWN_LIMITATIONS.md`) and Continuous Intelligence's own `MARKET`/`MARKET_STATUS` comparison state if persistence is configured. |
| **Safe to rerun?** | Yes — read of an external API, write is an upsert. |

**NOT independently re-executed this session** (same reasoning). Real
live Yahoo Finance data flowing end-to-end was confirmed in
`RELEASE_CHECKLIST_V1_1.md` §8 (`market_price: 491.27`,
`market_freshness: "FRESH"`).

## L. Continuous intelligence

**Run one cycle now:**
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend python scripts/run_continuous_intelligence.py
```

| | |
|---|---|
| **Purpose** | Detect meaningful market/news/decision-context changes across canonical entities and portfolios, publish WS events + notifications, respecting suppression cooldown. |
| **When to use** | On demand (default schedule interval 900s when `CONTINUOUS_INTELLIGENCE_ENABLED=true`, disabled by default). |
| **Success looks like** | Exit `0`, JSON with `entities_examined`, `events_emitted`, `events_suppressed`, `notifications_published`, `changes`/`suppressed` (each individually named, not just counted), `failures: []`. |
| **Common failure** | `CONTINUOUS_INTELLIGENCE_ENABLED` not `true` → `{"status": "disabled"}`, exit `1`. Lock contention (another cycle already running, same or different process) → not a script failure, the cycle result includes `"cycle_skipped: ..."` in `failures`. |
| **Changes data?** | Yes — updates comparison state/suppression/publishes notifications (durably, if Postgres-backed). |
| **Safe to rerun?** | Yes — `CycleLock` prevents two cycles overlapping (§L below); a contended run safely no-ops rather than corrupting anything. |

**Inspect state without mutating anything** (§F "Alembic current" and
this are the two safe-to-run-anytime diagnostics):
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend python scripts/inspect_continuous_intelligence.py
```

**Verified live** (this session, real output): `"status": "ok"`,
comparison state for `MARKET`/`MARKET_STATUS`/`NEWS`/`NEWS_CONFIDENCE`/
`RISK_SEVERITY`/`RECOMMENDATION`/`SIGNAL_TRIGGERED` (12 entities each, 0
in `STRATEGY_ALIGNMENT` — none evaluated yet on this deployment), 3
suppression fingerprints (all past cooldown), `"lock": {"status":
"free"}`, `"scheduler": {"scheduler_running": true, "registered_schedules":
3, "enabled_schedules": 1, ...}`.

**Reading the output**:
- `"lock"` — `"free"` (no cycle running), `"held"` (one is, right now,
  in this or another process — normal, not stuck), or `"stale (will be
  reclaimed by the next cycle)"` (a prior holder crashed without
  releasing — self-heals automatically after `CONTINUOUS_INTELLIGENCE_LOCK_TTL_SECONDS`,
  default 300s; **do not** manually intervene in the database for this).
- `"suppression"` entries with `cooldown_remaining_minutes: 0.0` are
  simply past cooldown — not stale data to clean up.
- `"status": "in_memory_only"` (top-level, instead of `"ok"`) means no
  Postgres-backed repository was reachable at the *last backend
  startup* — state/suppression/locking are not restart-safe in this
  configuration. Not an error; see
  `docs/architecture/CONTINUOUS_INTELLIGENCE_PERSISTENCE.md` §1.

This script is read-only by source inspection (only `.get()`/
`.list_domain()`/`.health_check()` calls — verified in
`RELEASE_CHECKLIST_V1_1.md` §12) — always safe to run, including during
an active incident.

---

## M. Backup

**Tested procedure, re-verified live this session** (2026-08-21,
against this exact `v1.1.1` deployment's real production database — not
a syntax check):

```bash
export $(grep -E '^POSTGRES_USER=' .env | xargs)
MSYS_NO_PATHCONV=1 docker compose -f docker-compose.yml -f docker-compose.prod.yml \
    exec postgres pg_dump -U "$POSTGRES_USER" -d marketmind -Fc \
    -f /tmp/marketmind_backup.dump
MSYS_NO_PATHCONV=1 docker cp marketmind-postgres:/tmp/marketmind_backup.dump ./marketmind_backup.dump
```

**Git Bash / Windows-specific gotcha, discovered live**:
without `MSYS_NO_PATHCONV=1`, Git Bash silently rewrites the in-container
path `/tmp/marketmind_backup.dump` into a **host** Windows path
(`C:/Users/.../Temp/marketmind_backup.dump`) before it ever reaches
`docker`, and both `pg_dump -f` and `docker cp`'s container-side
argument fail with "No such file or directory". Always prefix these two
commands with `MSYS_NO_PATHCONV=1` in Git Bash. (PowerShell does not
have this problem — no path-rewriting for arguments after `docker`.)

Produced a real 89,917-byte dump this session (close to the ~88KB
figure `RELEASE_CHECKLIST_V1_1.md` §11 independently recorded on an
earlier run — consistent).

**Where to store it**: copy `marketmind_backup.dump` off this host
immediately — the named `postgres_data` volume and this machine's disk
can fail together. Any durable location *outside* Docker and outside
this Git repository works (external drive, cloud storage you control,
network share) — **never** commit it to Git, and never store it
anywhere covered by this repository's own `.gitignore` exclusions being
your only safeguard (`.env`/backups are conceptually the same class of
"never in version control" asset — see §R).

## N. Restore

**Tested procedure, re-verified live this session** — restored into a
fresh, fully isolated scratch PostgreSQL container, **never** the live
`marketmind-postgres`:

```bash
# 1. Start an isolated scratch Postgres (own container, own DB name)
export $(grep -E '^POSTGRES_(USER|PASSWORD)=' .env | xargs)
docker run -d --name marketmind-restore-verify \
  --network marketmind-ai_marketmind-network \
  -e POSTGRES_USER="$POSTGRES_USER" \
  -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
  -e POSTGRES_DB=marketmind_restore_check \
  postgres:16-alpine

# 2. Wait for it to accept connections
docker exec marketmind-restore-verify pg_isready -U "$POSTGRES_USER" -d marketmind_restore_check

# 3. Copy the dump in and restore
MSYS_NO_PATHCONV=1 docker cp ./marketmind_backup.dump marketmind-restore-verify:/tmp/marketmind_backup.dump
MSYS_NO_PATHCONV=1 docker exec marketmind-restore-verify \
  pg_restore -U "$POSTGRES_USER" -d marketmind_restore_check --no-owner --no-privileges /tmp/marketmind_backup.dump

# 4. Verify Alembic state
docker exec marketmind-restore-verify psql -U "$POSTGRES_USER" -d marketmind_restore_check -c "SELECT version_num FROM alembic_version;"
# Expect: 0005_ci_persistence

# 5. Verify the application actually starts against it (not just that SQL replayed)
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec \
  -e DATABASE_URL="postgresql+asyncpg://$POSTGRES_USER:$POSTGRES_PASSWORD@marketmind-restore-verify:5432/marketmind_restore_check" \
  backend python scripts/inspect_continuous_intelligence.py

# 6. Clean up the scratch container once satisfied
docker rm -f marketmind-restore-verify
```

**Confirmed live, this session**: `pg_restore` completed with no errors,
all 24 tables present, `alembic_version` = `0005_ci_persistence`
(matching the source), and step 5's inspection script returned the
**exact same suppression fingerprints** as the live database — proving
genuine data continuity through the dump/restore cycle, not just a
structurally-valid-but-empty restore.

**Recovery** (restoring a *live* deployment after real data loss — a
different, higher-stakes procedure than the verification above):

1. **Stop the backend first** so nothing writes during the restore:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml stop backend
   ```
2. Restore the dump into the real `postgres_data`-backed database — same
   `pg_restore` command as step 3 above, but targeting
   `marketmind-postgres`/`marketmind` directly, not a scratch container.
3. `alembic current` — confirm the head matches what the running
   application code expects. If the backup predates the current
   version's migrations, `alembic upgrade head` **before** starting the
   backend, never after.
4. Start the backend:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml start backend
   ```
5. Verify health (§F).

**NOT independently re-executed this session** — this final "restore
onto the real live database" path was deliberately not rehearsed against
the actual live `marketmind-postgres` (that would mean real, if brief,
production downtime and risk to real accumulated data, for a procedure
whose restore-into-scratch mechanics are already fully proven above).
The underlying `pg_restore`/Alembic/inspection steps are identical to
what step 1-5 above just verified live — only the target container
differs.

---

## O. Failure recovery

General principle: **never** run a destructive command (`down -v`, `rm
-f` on a volume, `alembic downgrade`) as a first response to an
incident — collect logs first (§G), diagnose (§F, this section, and
`docs/release/TROUBLESHOOTING_GUIDE.md`), and only then act.

| Symptom | Likely cause | What to do |
|---|---|---|
| `/api/v1/ready` returns `503` | A required repository/service didn't construct | `curl http://localhost:8000/api/v1/health`, check `data.blocking_issues`/per-component state; cross-reference `docs/release/PRODUCTION_CONFIGURATION_GUIDE.md` |
| Backend container `Exited` / unhealthy | Crash on startup, or Postgres not reachable | `docker compose ... logs backend`, look for `bootstrap_completed` / `startup_validation_passed: false` |
| Frontend unhealthy | nginx failed to start, or build was bad | `docker compose ... logs frontend`; if it never was healthy since a rebuild, rebuild with correct `VITE_API_BASE_URL`/`VITE_WS_BASE_URL` build args (§D of `DEPLOYMENT_GUIDE.md`) |
| Database unhealthy | Postgres container crashed, disk full, bad credentials | `docker compose ... logs postgres`; `pg_isready` (§F); check host disk space |
| Redis unhealthy | Container crashed; note Redis isn't consumed by any feature yet, so this alone doesn't degrade the app | `docker compose ... logs redis`; ping test (§F) |
| Chroma unavailable | Container crashed or OOM (no healthcheck to auto-restart it) | `docker compose ... logs chromadb`; heartbeat check (§F); knowledge/research features degrade to `503`, everything else keeps working |
| Migration failure | `DATABASE_URL` wrong, or database not empty/not at expected prior revision | `alembic current` vs. latest revision in `backend/alembic/versions/`; never hand-edit a shipped migration (§H) |
| CORS / login failure | `ALLOWED_ORIGINS` doesn't include the frontend's real origin | Check backend `.env`'s `ALLOWED_ORIGINS`; must be the frontend's actual scheme+host+port |
| WebSocket disconnected | Expected on any backend restart — no replay by design | Confirm client reconnects automatically (frontend does, with backoff); if it doesn't reconnect, that's a frontend bug, not a backend one |
| Market data unavailable | `MARKET_DATA_ENABLED=false`, or provider (Yahoo Finance) degraded/unavailable | `run_market_data_refresh.py`'s own per-entity `reason` field (§K); provider health surfaces via `/api/v1/health` |
| News ingestion failure | `RSS_FEED_URLS` empty, feed unreachable, or `INGESTION_ENABLED=false` | `run_ingestion.py`'s own summary (§I); a per-feed failure is isolated, doesn't fail the whole run |
| Continuous Intelligence lock stuck | Looks stuck but usually isn't — see §L | `inspect_continuous_intelligence.py`'s `"lock"` field: `"stale"` self-heals after `CONTINUOUS_INTELLIGENCE_LOCK_TTL_SECONDS` (default 300s) on the *next* cycle attempt automatically — do not manually edit the database |
| Continuous Intelligence notifications duplicated | Suppression cooldown expired, or Postgres was unreachable at the process's last startup (in-memory fallback, restart-unsafe) | `inspect_continuous_intelligence.py`'s `"suppression"` section; check top-level `"status"` for `"in_memory_only"` |
| `Docker not found` / commands hang | Docker Desktop not running yet | Open Docker Desktop, wait for "Engine running", retry (§E step 1) |
| WSL not running | Docker Desktop's WSL2 backend didn't start | Restart Docker Desktop; if persistent, `wsl --status` in PowerShell to check WSL itself, or restart the machine |
| Port already in use | Another process (or a duplicate stack) already bound `8000`/`8080` | `docker compose ... ps` first — you may already be running; otherwise identify the conflicting process (`netstat -ano \| findstr :8000` in PowerShell) before killing anything |

---

## P. Rollback

Two independent things can be rolled back — never treat them as one
operation.

### A. Application code / image rollback

The frontend and backend communicate only through the frozen
`/api/v1`/`/ws` contract (`docs/release/API_VERSIONING_POLICY.md`) — the
two can be rolled back independently, without coordination, **as long as
the release being rolled back to didn't itself change that contract**
(true for every release so far; re-confirm for any future one before
relying on this).

```bash
git fetch --tags
git log --oneline -1 v1.1.0        # inspect what v1.1.0 actually is, before acting
git checkout v1.1.0                # detached HEAD at the previous tag — inspect only, or:
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

- This rebuilds the backend/frontend images from the `v1.1.0` source and
  restarts just those two containers — Postgres/Redis/Chroma and their
  data are untouched.
- **Do not** alter any existing tag (`v1.1.0`, `v1.1.1`, ...) to "move"
  it — check out the tag, or branch from it, never `git tag -f`.
- Return to the latest state afterward with `git checkout main`.

### B. Database migration rollback

**Never casually downgrade a production database.** Per
`docs/release/UPGRADE_POLICY.md`: `alembic downgrade <revision>` is
supported for every revision but is destructive to any data added since
— a last resort, not routine rollback.

- Rolling back **application code alone** (A, above) almost never
  requires a matching database downgrade — every migration to date is
  additive (new tables/columns), and older application code simply
  doesn't read the new columns/tables; it does not break against a
  *newer* schema.
- Only downgrade the schema itself if a specific migration is
  independently known to be broken, and only after a fresh backup (§M)
  of the current (pre-downgrade) state.
- `v1.1.1` and `v1.1.0` are both at Alembic head `0005_ci_persistence` —
  rolling back between them (§Q "when this applies") involves **no**
  schema change at all (`v1.1.1` only touched the release CI workflow —
  see `git show v1.1.1 --stat`), so §B does not apply to that specific
  rollback.

**NOT independently rehearsed live this session** — actually checking
out `v1.1.0`, rebuilding, and restarting the live backend/frontend
containers was judged too disruptive to this session's live-verification
scope (it would briefly take the real deployment's API/frontend down).
The underlying mechanics (image rebuild from a tagged commit, restart
scoped to backend/frontend only) are standard Docker Compose behavior,
not MarketMind-specific, and the "no schema change between v1.1.0 and
v1.1.1" fact above was directly confirmed via `git diff v1.1.0 v1.1.1`
this session.

---

## Q. Release update procedure

For promoting a *new* release (not covered by rollback, above):

1. Read the new release's own `docs/release/RELEASE_NOTES_*.md` and
   `docs/release/RELEASE_CHECKLIST_*.md` for anything version-specific
   (new required settings, new migrations).
2. Back up the database first (§M) — always, before any schema-bearing
   update.
3. `git fetch --tags && git checkout <new-tag>`.
4. `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`.
5. Run migrations (§H) — safe/idempotent, but only actually change
   anything if the new release ships a new one.
6. Verify health (§F) fully before considering the update complete.
7. `git checkout main` once satisfied (returns your working tree to the
   branch tip; the running containers are unaffected by this — they run
   from the image already built, not from the working tree live).

This project's versioning scheme (MAJOR.MINOR.PATCH, what qualifies as
each) is `docs/release/UPGRADE_POLICY.md` — not re-explained here.

---

## R. Security precautions

- **`.env` must remain local/secret.** Never commit it — confirmed
  enforced by `.gitignore` (`.env`, `.env.*`, with `.env.example`
  explicitly excepted) and independently confirmed via `git log --all --
  .env`: zero history of it ever being committed to this repository.
- **Never paste JWTs, passwords, or `.env` values into a ticket, chat,
  or log excerpt** — including the Redis password needed for the §F
  ping check; export it into your own shell session only, never echo it.
- **Docker production port isolation**: Postgres/Redis/Chroma are not
  host-published (§A, confirmed live via `docker compose ... ps` and
  `docker compose ... config`) — only `backend`(8000)/`frontend`(8080)
  are. Do not add a `ports:` mapping to any of the three infra services
  in `docker-compose.prod.yml` "for convenience" — that reopens a real,
  documented ChromaDB advisory's mitigation (`KNOWN_LIMITATIONS.md`).
- **CORS**: `ALLOWED_ORIGINS` in `.env` must list the frontend's real
  origin(s), never a wildcard alongside credentialed requests
  (`docs/release/SECURITY_CONSIDERATIONS.md`).
- **Secret rotation**: rotating `SECRET_KEY` invalidates **every**
  currently-issued token — every signed-in user is logged out
  immediately (no revocation list exists, so this is also the only way
  to force-end every session at once if a leak is suspected).
  `POSTGRES_PASSWORD`/`REDIS_PASSWORD`/`ANTHROPIC_API_KEY` are read once
  at process start — rotate via your secrets process, then restart the
  backend (§D + §C) for the new value to take effect.
- **Backup security**: `marketmind_backup.dump` (§M) is a full database
  dump — treat it with the same sensitivity as `.env`. Never commit it,
  never store it inside this Git repository's working tree even
  temporarily-but-forgotten, and store it somewhere with access control
  you actually manage.
- **Public GitHub repository implications**: this repository's `origin`
  is `https://github.com/drgauravanand2383-sketch/MarketMind-AI.git`. If
  it is public, every commit, tag, and workflow run is visible to
  anyone — this is exactly why `.env`/secrets/backups must never be
  committed (source code being public is a deliberate choice; leaking
  credentials through it would not be). Confirm the repository's actual
  visibility in GitHub's own Settings → General if you're unsure.
- **Dependency / security updates**: `chromadb 1.5.9` has a known,
  currently-unpatched advisory (`PYSEC-2026-311`) — mitigated by the
  port-isolation above, not by a version bump (none exists yet). Track
  it; do not attempt a speculative upgrade without confirming a fixed
  version has actually shipped. `pip-audit`/`npm audit` are the tools
  this project's own release checklists use to check for anything new.

---

## S. Version / release check

**"What version am I running?" checklist:**

```bash
# 1. Current Git commit and tag
git log --oneline -1
git describe --tags --exact-match 2>/dev/null || echo "(not exactly on a tag)"

# 2. Running application version (what the container actually serves,
#    which can differ from your working tree if you haven't rebuilt)
curl http://localhost:8000/api/v1/version

# 3. Current migration head
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend python -m alembic current
```

As of this document: Git tag `v1.1.1` (CI-workflow-only patch on top of
`v1.1.0`'s application code — see `git show v1.1.1 --stat`),
`GET /api/v1/version` reports `application_version: "1.0.0"` (the
FastAPI app's own version string was deliberately not bumped for the
v1.1 line — a recorded, deliberate deferral, see
`docs/release/RELEASE_CHECKLIST_V1_1.md` §14, not a bug), Alembic head
`0005_ci_persistence`.

**A mismatch between `git describe` and `/api/v1/version`** means the
running containers were built from a different commit than your current
working tree — rebuild (§Q) if that's not intentional.

---

## T. Escalation checklist — when NOT to touch the system

Stop and get a second opinion (or the original engineering team) before
proceeding, rather than improvising, when:

- **`alembic downgrade` looks like the only fix.** This is destructive
  to any data added since the target revision (§P.B) — get confirmation
  this data loss is acceptable before running it, not after.
- **A restore is being considered against the *live* database**, not a
  scratch copy. Back up the current (possibly-still-partially-working)
  state first (§M), even if it looks broken — a bad state you can
  compare against is better than none.
- **You don't recognize the failure mode** and it isn't in §O's table or
  `docs/release/TROUBLESHOOTING_GUIDE.md`. Guessing at a fix on a
  production system with real user data is how a recoverable incident
  becomes an unrecoverable one.
- **A security incident is suspected** (leaked `SECRET_KEY`, leaked
  `.env`, unexpected access). Rotate `SECRET_KEY` immediately (§R) to
  force-end every session, capture logs (§G) before restarting anything,
  then escalate — do not quietly rotate and move on without recording
  what happened and why.
- **`docker compose down -v` or any `rm`/`prune` targeting a named
  volume is being considered.** This is irreversible data loss for
  whichever volume is targeted. Confirm a recent, verified-restorable
  backup (§M/§N) exists first, every time, no exceptions.
- **The fix would mean hand-editing an already-shipped Alembic migration
  file, or directly `UPDATE`/`DELETE`-ing rows in `continuous_intelligence_state`
  (the `LOCK`/`SUPPRESSION`/comparison-state table)** to "unstick"
  something. Both self-heal on their own (§H, §L) — manual intervention
  here is far more likely to introduce a new, harder-to-diagnose problem
  than to fix the original one.
- There is no automated alerting/paging configured by this codebase
  itself (`docs/release/OPERATIONAL_RUNBOOK.md`'s own "Escalation"
  section) — if you're the only operator and something above applies,
  that itself is the signal to slow down, not proceed faster.
