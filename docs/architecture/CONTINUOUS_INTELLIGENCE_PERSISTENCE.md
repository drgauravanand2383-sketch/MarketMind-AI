# Continuous Intelligence — Persistence, Concurrency & Reliability (Milestone 16)

Milestone 15 shipped Continuous Intelligence with in-memory comparison
state and in-memory suppression — safe (never floods on restart) but not
restart-*preserving* (a genuine transition emitted just before a restart
could re-emit after one, and two overlapping cycle executions — same
process or a second one entirely — had no shared mutual-exclusion
mechanism at all). Milestone 16 hardens exactly this: durable state,
durable suppression, and cross-process cycle locking, all built on the
smallest schema this codebase's own conventions call for — one new table.

This document is the persistence-specific deep dive. See
`docs/architecture/CONTINUOUS_INTELLIGENCE.md` for the rest of the
Continuous Intelligence architecture (change detection, significance
rules, decision impact, event types, scheduler) — unchanged except where
cross-referenced below.

## 1. Persistent state model

One generic table, `continuous_intelligence_state`
(`app/repositories/continuous_intelligence/postgres/models.py`):

| Column | Type | Notes |
|---|---|---|
| `domain` | `String`, part of PK | e.g. `MARKET`, `RISK_SEVERITY`, `SUPPRESSION`, `LOCK` |
| `key` | `String`, part of PK | entity id / portfolio id / fingerprint / lock name, depending on `domain` |
| `value` | `JSON`, nullable | compact value only — never a full domain result (see below) |
| `observed_at` | `DateTime(timezone=True)`, indexed | last-write timestamp; doubles as "emitted_at" for suppression and "claimed_at" for locks |

**Why one table, three responsibilities.** The milestone brief explicitly
warns against blindly creating both a state table and a suppression
table "if one structure can safely serve both responsibilities" — this
design extends that reasoning to a third, cycle locking, because all
three are structurally identical: a durable value (or no value) keyed by
a compact identifier, with a timestamp used for either comparison,
cooldown-expiry, or staleness-expiry. `domain` disambiguates the three
uses:

- **Comparison state** (`MARKET`, `MARKET_STATUS`, `NEWS`,
  `NEWS_CONFIDENCE`, `RISK_SEVERITY`, `RECOMMENDATION`,
  `STRATEGY_ALIGNMENT`, `SIGNAL_TRIGGERED`) — `value` holds the
  previously-observed value for that key; `observed_at` is informational
  only here.
- **Suppression** (`SUPPRESSION`) — `key` is a `DetectedChange.fingerprint`;
  `value` is unused (`null`); `observed_at` is the emission time a
  cooldown check compares `now` against.
- **Cycle locking** (`LOCK`) — a single well-known key
  (`"continuous_intelligence_cycle"`); `value` is `{"holder": "<execution
  id>"}`; `observed_at` is the claim time used for staleness recovery.

**Compact values only** (§2's own instruction): a `MarketSnapshot` is
stored as its own JSON dump (a handful of fields), never the full
`MarketSnapshotResult`/provider response; a risk/recommendation
comparison stores only `overall_severity`/`(type, score)`, never the
`RiskAssessment`/`RecommendationResult` itself. Nothing here is a second
copy of a downstream engine's own stored result — `RiskAssessment`,
`RecommendationResult`, etc. remain the single source of truth in their
own tables; this table only remembers "what did we last compare against."

**Two implementations of one interface.** `ContinuousIntelligenceStateStore`,
`Suppression`, and `CycleLock` (`app/services/continuous_intelligence/{state,suppression,locking}.py`)
are each satisfied by an in-memory implementation (Milestone 15,
unchanged) and a Postgres-backed implementation (new). `ChangeDetectionService`
and `ContinuousIntelligenceService` are written against the interfaces —
neither knows or cares which backing store is injected. Bootstrap wiring
(`app.bootstrap.build_continuous_intelligence_state_store`/
`build_continuous_intelligence_suppression`/`build_continuous_intelligence_lock`)
picks Postgres-backed when a repository is reachable at startup, in-memory
otherwise — the same graceful-degradation shape every other optional
dependency in `app.bootstrap` already uses. **Persistence is a reliability
enhancement, not a hard requirement**: the system functions identically
either way, just with weaker restart-survival guarantees in the in-memory
case (exactly Milestone 15's own behavior, unchanged).

## 2. Suppression persistence

`PostgresSuppressionService` implements the same `is_duplicate(fingerprint)`
/ `record_emitted(fingerprint)` interface as the in-memory
`SuppressionService`, backed by `continuous_intelligence_state` with
`domain="SUPPRESSION"`. `is_duplicate` reads the row's `observed_at` and
compares elapsed time against the configured cooldown at read time — the
cooldown duration itself is never stored, so the same table serves any
caller-configured `suppression_cooldown_minutes` without a schema change.

**Why this matters, concretely**: without durable suppression, a genuine
transition emitted at 04:06 (recorded as `SUPPRESSED_UNTIL 05:06`
conceptually) that survived a restart at 04:10 would lose that record —
the identical transition re-observed at 04:15 would re-emit, producing a
duplicate notification the cooldown was specifically supposed to prevent.
With Postgres-backed suppression, the record survives the restart and the
cooldown is honored correctly. Verified:
`tests/services/continuous_intelligence/test_service.py
::test_postgres_backed_service_restart_does_not_duplicate_and_still_detects_new_change`.

## 3. Concurrency / locking

`ContinuousIntelligenceService.run_cycle()` wraps its entire body in a
`CycleLock` acquire/release (`app/services/continuous_intelligence/locking.py`):

```python
async def run_cycle(self, execution_id: str) -> ContinuousIntelligenceCycleResult:
    acquired = await self._lock.try_acquire(lock_holder, _CYCLE_LOCK_KEY)
    if not acquired:
        return <empty result, failures=("cycle_skipped: ...",)>
    try:
        return await self._run_cycle_locked(execution_id, started_at)
    finally:
        await self._lock.release(lock_holder, _CYCLE_LOCK_KEY)
```

**`PostgresCycleLock`** claims `(domain="LOCK", key="continuous_intelligence_cycle")`
via `BaseContinuousIntelligenceStateRepository.try_claim`, a portable,
two-path atomic claim (no Postgres-only primitive like
`pg_advisory_lock` — deliberately, so the exact same claim semantics are
exercised by the SQLite-backed test suite as by production Postgres):

1. **No existing row**: a plain `INSERT` — if a concurrent caller wins
   the same race, the loser's `INSERT` raises `IntegrityError` on the
   primary-key conflict, caught and treated as "not claimed."
2. **An existing row**: `UPDATE ... WHERE observed_at < :stale_before` —
   only succeeds (checked via rowcount) if the existing claim is older
   than `cycle_lock_ttl_seconds` (default 300s). A live lock leaves the
   row untouched.

Both paths are single, atomic SQL statements — no read-then-write gap for
a second caller to race into. Verified directly with genuine
`asyncio.gather` concurrency at the repository level
(`test_concurrent_try_claim_only_one_winner`) and the lock level
(`test_postgres_lock_concurrent_acquire_only_one_winner`).

**Bounded acquisition**: `try_acquire` is a single non-blocking attempt —
never a wait/retry loop. A contended cycle returns immediately with a
clearly-marked skip (`"cycle_skipped: another continuous intelligence
cycle is already running"` in `.failures`), not a hang.

**Automatic stale-lock recovery**: if a holder crashes without calling
`release()`, its claim simply ages past `cycle_lock_ttl_seconds` and the
next `try_acquire` reclaims it via the stale-`UPDATE` path above — no
process-exit hook, no manual intervention. `release()` itself only clears
a claim still owned by the caller's own holder id, so a lock already
reclaimed by a new legitimate owner (after a stale timeout) can never be
released out from under it by a late call from the original holder.

**Cross-process safety, the actual target scenario**: two independent
`ContinuousIntelligenceService` instances — a second backend replica, or
the real incident Milestone 15's own live-acceptance testing surfaced (a
one-off diagnostic script that itself calls `bootstrap_application_state`,
registering its own periodic scheduler as a side effect, running
concurrently with the already-live server) — sharing the same database
correctly contend for the same lock. Verified:
`test_postgres_backed_lock_prevents_concurrent_cycles_across_service_instances`.

**`InMemoryCycleLock`** (the fallback when no Postgres repository is
available) is an `asyncio.Lock`-backed, same-process-only guard — real
protection for a manual trigger racing the scheduler within one process,
but explicitly **not** cross-process safe. This boundary is intentional
and documented, not a bug: without a durable store there is no
cross-process coordination mechanism to build on.

**Scheduler-level review** (§6): `Scheduler`/`APSchedulerService`
themselves are unmodified. APScheduler's own `max_instances=1` already
prevents its *own* interval trigger from overlapping itself (unrelated to
this milestone); the new `CycleLock` inside `ContinuousIntelligenceService`
covers every other overlap source (manual trigger vs. scheduled, two
processes) without touching shared scheduler infrastructure used by every
other workflow. `APSchedulerService.shutdown()` already `wait=True`s for
an in-flight job before returning — unchanged, still correct.

## 4. Restart behavior

| Scenario | In-memory (no Postgres) | Postgres-backed |
|---|---|---|
| Unchanged state after restart | No event (first observation is never a change) | No event (previous value genuinely read back) |
| Genuinely new change after restart | Detected correctly (fresh baseline, then the *next* cycle detects it) | Detected correctly (previous value compared directly) |
| Duplicate emission right after a restart | Possible in the narrow window right after restart, before a fresh baseline is re-established (an accepted, documented Milestone 15 gap) | Never — suppression record survives |
| A crashed cycle's lock | N/A (in-memory lock dies with the process) | Automatically reclaimed after `cycle_lock_ttl_seconds` |

A restart **never floods** in either mode — this was true in Milestone 15
and remains true. What Milestone 16 adds is that, *with* Postgres, a
restart also never **loses** already-established comparison state or
suppression cooldowns — both regressions verified together in
`test_postgres_backed_service_restart_does_not_duplicate_and_still_detects_new_change`.

## 5. Migration

`alembic/versions/0005_ci_persistence.py` creates
`continuous_intelligence_state` by driving DDL directly off the live
`ContinuousIntelligenceStateModel.metadata` (`create_all(checkfirst=True)`
/ `drop_all(checkfirst=True)`) — the same `0002_auth_schema` pattern, so
the migration can never drift from the actual model. Registered in
`app.operations.migrations.discovery._BASES`, the single collection point
Alembic and `StartupValidationService`'s own metadata-discovery check both
consume.

A related, smaller migration, `0004_strategy_linkage.py`,
adds the nullable `recommendation_result_id` column to
`strategy_evaluation_results` — see §7 below and
`docs/architecture/CONTINUOUS_INTELLIGENCE.md` §16.

Both migrations are column/table-existence-checked (the same
`0003_risk_market_data_coverage` idiom), never assumed — safe against a
database stamped at an earlier revision without the table/column having
actually been created yet. Verified:
`tests/operations/test_continuous_intelligence_persistence_migration.py`
(upgrade/downgrade, composite primary key, stamped-baseline graceful
skip, and the repository actually working against the real
Alembic-created schema, not just an ad-hoc `create_all`).

## 6. Strategy linkage — resolved

Milestone 15 deliberately left Strategy change detection disabled: a
*stored* `StrategyEvaluationResult` carried no portfolio linkage at all.
Milestone 16 §12 resolved this safely — `recommendation_result_id`
(itself a `RecommendationRequest.id`, the same "*_result_id is actually a
request id" convention `RiskAssessmentRequest`/`ExplainabilityRequest`/
`BacktestSnapshot` already use) was added to `StrategyEvaluationResult`
as a nullable, additive field, populated from a value
`StrategyEvaluationService.evaluate_recommendations()` already received
as a parameter but previously never persisted. No ownership was invented:
an evaluation stored before this field existed
(`recommendation_result_id is None`) is simply excluded from automatic
detection, never guessed at. Full detail:
`docs/architecture/CONTINUOUS_INTELLIGENCE.md` §16.

## 7. Provider resilience

`YahooFinanceProvider.health()` (Milestone 15) always reported `HEALTHY`
regardless of actual request outcomes. Milestone 16 §10 makes it reflect
real, observed failure history: `_consecutive_failures` increments on
each fully-retry-exhausted network/rate-limit/5xx failure and resets to 0
on the next successful HTTP response (a ticker-specific "no data" error
does *not* count — that is a data problem, not a provider-availability
problem). `health()` reports `DEGRADED` past
`degraded_after_consecutive_failures` (default 3) and `UNAVAILABLE` past
`unavailable_after_consecutive_failures` (default 8), still without
making a new request (matching the existing health-check-must-be-cheap
contract). No second provider was added, and no circuit breaker blocks
calls — this is honest status reporting only, layered onto the existing
retry/stale-cache behavior `MarketSnapshotService` already had (§10's own
"resilience without unnecessary provider complexity" instruction).

## 8. Multi-entity coverage & entity resolution alias governance

`app/services/entity_resolution/reference_overlay.py` — an optional,
operator-supplied JSON file (`CANONICAL_ENTITIES_OVERLAY_PATH`) of
*additional real companies*, merged at startup into the exact same
`COMPANY_KEYWORDS` dict every consumer (`MarketIntelligenceEngine`,
`EvidenceEngine`, `EntityResolutionService`) already reads — never a
second, parallel entity model. No default overlay ships; the base 12
companies remain the only ones present unless an operator configures
more. Every entry is validated before merging:

- **Collision rejection**: an overlay `entity_id`/`ticker`/`canonical_name`
  that already exists in the base set is rejected outright — an overlay
  can only *add*, never silently override, a real, already-known company.
- **Alias governance (§9)**: any alias or canonical name shorter than 3
  characters, or matching a small stoplist of generic business words
  (`"group"`, `"corp"`, `"holdings"`, `"technologies"`, ...), is rejected
  — the same class of false-positive risk `EntityResolutionService
  ._find_ticker_occurrences`'s own docstring already identifies for short
  tickers, enforced here at configuration-load time instead, so a bad
  overlay entry never reaches the scoring engine. A short alias equal to
  the entry's own ticker is exempt (matched case-sensitively as a ticker,
  the existing safeguard).

A malformed or invalid overlay is logged and skipped — it never crashes
startup, and the base canonical entity set (never empty) remains fully
usable regardless. Must be applied before the first
`get_company_reference_data()` call in the process (that function
memoizes its result); `apply_reference_overlay` resets the memoized cache
after merging so the very next call picks up the new entries. Wired in
`app.bootstrap` immediately before `build_entity_resolution_service`.

`EntityResolutionService`'s own scoring algorithm (whole-word matching,
ambiguity margin/penalty, confidence tiers) is unchanged — deterministic
behavior preserved, no ML model introduced, per §9's own instruction.

## 9. Single-process boundaries that remain

Even with every Milestone 16 improvement:

- **Detection remains single-process per cycle.** `PostgresCycleLock`
  prevents two processes from running a cycle *concurrently*, but there is
  still exactly one active WebSocket publisher process at a time — this
  milestone does not introduce a distributed event bus (explicitly out of
  scope), so a second replica configured to also run cycles would need
  its own WS connections to actually deliver notifications to clients
  connected to it; state/suppression coordination via the shared database
  is what Milestone 16 provides, not multi-replica event fan-out.
- **In-memory fallback remains genuinely single-process.** `InMemoryCycleLock`/
  `InMemoryContinuousIntelligenceStateStore`/`SuppressionService` provide
  zero cross-process coordination — a deployment without a reachable
  PostgreSQL database is exactly as safe as Milestone 15 was, no more, no
  less.
- **No multi-region / distributed-lock service was introduced** (§5's own
  explicit prohibition) — the claim-row pattern is scoped to one shared
  database, not a distributed system.

## 10. Operational diagnostics

`scripts/inspect_continuous_intelligence.py` (Milestone 16 §15) — a
read-only, container-exec-only diagnostic (same boundary as
`scripts/run_continuous_intelligence.py`; no HTTP endpoint anywhere)
printing: current comparison-state entries per domain, suppression
entries with remaining cooldown, the cycle lock's current claim
(held/stale/free), and overall scheduler health. Reports
`"status": "in_memory_only"` (not an error) when no durable repository is
configured, rather than failing.

## 11. Observability

New structured log events (`logging.Logger`, the existing convention
throughout this codebase — no new telemetry platform):

| Event | Where | Meaning |
|---|---|---|
| `continuous_intelligence_cycle_started` / `_completed` | `service.py` | Cycle boundaries, with `duration_seconds`, `events_emitted`, `events_suppressed`, `failure_count` |
| `continuous_intelligence_cycle_skipped_overlap` | `service.py` | Lock contention — another cycle already running |
| `continuous_intelligence_suppression_hit` | `service.py` | A candidate change was suppressed (fingerprint + domain) |
| `continuous_intelligence_publish_failed` | `service.py` | A WS publish failed (state/suppression already recorded regardless) |
| `continuous_intelligence_lock_contended` | `locking.py` | `PostgresCycleLock.try_acquire` returned `False` |
| `canonical_entity_overlay_loaded` / `_applied` | `reference_overlay.py` | Overlay file accepted, entry merged |
| `yahoo_finance_request_failed` (extended) | `yahoo.py` | Now includes `consecutive_failures` |

## 12. Performance

Persistence adds at most one small read + one small write per
`observe_*`/`is_duplicate`+`record_emitted` call — no N+1 storm, since
each detector call already corresponds to exactly one comparison per
entity/portfolio/domain per cycle (the same call shape Milestone 15 had
against in-memory dicts, now against indexed `(domain, key)` lookups on a
single table). The lock adds exactly one claim attempt and one release
per cycle, not per entity. No batching was introduced because none of
these operations were ever batched across entities to begin with — each
domain/key pair is independently meaningful and independently comparable.
