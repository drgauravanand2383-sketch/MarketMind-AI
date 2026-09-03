# 0003 — Scheduler liveness watchdog + pinned backend dependencies

**Status:** Accepted · **Date:** 2026-09-04

## Context

The backend runs one in-process `AsyncIOScheduler` (`APSchedulerService`)
for every recurring job: hourly ingestion, hourly market-data refresh,
15-minute Continuous Intelligence, and the daily 08:30 IST Global Market
Intelligence run.

After a routine image rebuild + `docker compose up -d`, the scheduler
came up reporting `running=True` but **never dispatched a single job for
~20 hours** — no Continuous Intelligence cycles, and the daily Global
Market Intelligence run silently did not happen. A later restart brought
it back. It could not be reproduced on demand; an isolated repro of the
exact bootstrap ordering (construct early, `.start()` after heavy async
work, under the real `uvicorn` CLI on uvloop) fires jobs correctly every
time.

Two independent gaps made this possible:

1. **No liveness signal.** `scheduler_running` is a synchronous "`.start()`
   was called" flag. Nothing checked whether the timer loop was actually
   *ticking*, and scheduler state was exposed by no API at all — the
   outage was invisible until someone noticed missing data a day later.
2. **Unpinned dependencies.** `backend/pyproject.toml` uses open ranges
   (`fastapi>=0.115`, `uvicorn[standard]>=0.32`, …) with no lockfile, so
   every rebuild re-resolves the entire transitive tree. "Worked before
   the rebuild, broke after" cannot be diagnosed or prevented when the
   installed versions are not recorded.

## Decision

### Canary + watchdog (`app/scheduler/ap_scheduler.py`)

- **Canary job** — an internal `IntervalTrigger` job (`_CANARY_JOB_ID`,
  60 s) whose only effect is stamping `_last_canary_at`. A recent stamp
  is positive proof the timer loop is alive. It is excluded from
  `registered_jobs`, `next_execution`, and `_last_execution_at` — it is
  not a schedule anyone registered.
- **Watchdog** — an independent `asyncio.Task` (never an APScheduler job:
  a dead scheduler could not run its own watchdog). Every 120 s it checks
  `dispatching`; if the canary has been silent past a 300 s threshold
  (5 missed ticks; a startup grace of the same length applies before the
  first stamp), it logs `CRITICAL` and calls `restart()`.
- **`restart()`** — shuts the `AsyncIOScheduler` down and builds a
  **fresh instance** on the current (definitely-running) event loop, then
  re-registers every schedule. A new instance re-captures
  `asyncio.get_running_loop()`, which is the recovery even if the root
  cause is a stale event-loop capture.
- **`GET /api/v1/system/scheduler`** exposes `SchedulerHealthStatus`,
  now including `dispatching`, `last_canary`, and `watchdog_recoveries`.
  Unauthenticated, like the other `/health` / `/services` probes.

A dead-on-startup scheduler now self-heals within ~6 minutes and the
event is loud (`CRITICAL` log + a non-zero `watchdog_recoveries` on the
health endpoint), instead of silent for a day.

### Pinned dependencies (`backend/requirements.lock`)

- `backend/requirements.lock` records the exact version of every direct
  and transitive dependency, captured with `pip freeze` from a known-good
  running container.
- The Dockerfile installs with `pip install -c requirements.lock .` — the
  project is still installed from `pyproject.toml`, the constraint file
  only removes version drift between rebuilds.
- **Regenerate** after an intentional dependency change: `pip freeze` in
  a healthy container, drop the `marketmind-backend @ file://` self-line,
  commit the diff.

## Consequences

- Rebuilds are now reproducible; an unplanned dependency bump shows up as
  a `requirements.lock` diff in review, not as a production incident.
- The watchdog adds one recurring 60 s no-op job and one lightweight
  120 s task per process — negligible.
- The exact trigger of the original 20 h stall is still unknown. The
  watchdog is deliberately a recovery mechanism, not a fix for a
  diagnosed bug; `watchdog_recoveries > 0` in production is the signal to
  investigate further with the (now available) health data.

## Alternatives considered

- *Diagnose and fix the root cause only* — not possible without a
  reproduction; leaving the system with no detection in the meantime was
  unacceptable for an unattended daily job.
- *Make the watchdog an APScheduler job* — rejected: circular (it cannot
  run if the thing it checks is dead).
- *`uv.lock` instead of a `pip freeze` constraint file* — `uv` is not in
  the toolchain here; a constraint file needs no new tooling and installs
  with plain `pip`.
- *Fail startup hard if the scheduler doesn't dispatch within N seconds* —
  rejected: blocks the whole API on a scheduler check, and a crash-loop
  is worse than a self-healing degraded state for this workload.
