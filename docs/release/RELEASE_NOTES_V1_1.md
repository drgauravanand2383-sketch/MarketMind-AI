# MarketMind AI — Version 1.1 Release Candidate Notes

This document covers everything since `docs/release/RELEASE_NOTES_V1.md`
(the frozen v1.0.0 release notes, unchanged and not retroactively
rewritten). v1.0.0 remains exactly what it was: request-driven market
intelligence, no live market data, no broker integration. Everything
below was added **after** that release, across Milestones 11-17.

**Status**: Release Candidate. Not tagged, not pushed, not released —
see `docs/release/RELEASE_CHECKLIST_V1_1.md` for the full verification
record and current sign-off status.

## What's new since v1.0.0

### Milestone 11 — Live Market Intelligence & News Ingestion
Real RSS ingestion (configurable feed URLs) → local embedding generation
→ `KnowledgeRepository`/ChromaDB, on a scheduled cycle
(`INGESTION_ENABLED`). No LLM required for ingestion itself.

### Milestone 12 — Entity Resolution & Company Intelligence
Deterministic, whole-word-matching entity resolution against a static
canonical company reference set (12 companies as shipped) — confidence
tiers, ambiguity handling, no ML model. Enriches ingested knowledge
records and supports backfill of previously-ingested ones
(`scripts/run_entity_backfill.py`).

### Milestone 13 — Live Market Data & Price Intelligence
A real `MarketDataProvider` (Yahoo Finance, `MARKET_DATA_PROVIDER=
yahoo_finance`) — real prices, freshness-aware caching, stale-data
fallback, retry-with-backoff. `MockMarketDataProvider` remains the
default; no behavior change for an existing deployment that doesn't
opt in.

### Milestone 14 — Portfolio Intelligence & Decision Integration
Risk analytics, strategy evaluation, and recommendations now factor in
live market data. New Decision Center workspace ties Recommendations,
Risk, Strategy, Signals, and Alerts together per-portfolio.

### Milestone 15 — Continuous Intelligence & Decision Automation
The system became proactive: a scheduled cycle
(`CONTINUOUS_INTELLIGENCE_ENABLED`) detects meaningful changes in
market data, news, and decision context (risk/recommendation/signal
transitions) and pushes real-time WebSocket notifications — without
duplicating any existing scoring/evaluation logic. Deduplication and
cooldown-based suppression prevent notification floods.

### Milestone 16 — Intelligence Reliability, Persistence & Multi-Entity Scale
Continuous Intelligence's comparison state, suppression records, and
cycle-execution lock all became durable (PostgreSQL-backed, one generic
table: `continuous_intelligence_state`) — restart-safe, and safe against
two processes (a second replica, or an operational script) running a
cycle at the same time. Strategy-change detection was wired into the
automatic cycle for the first time (a real, safe portfolio linkage was
found — nothing was guessed). The Yahoo Finance provider now reports
real, observed-failure-history-driven health status. An optional
canonical-entity overlay lets an operator add real companies to the
reference set without editing code.

### Milestone 17 — Production Hardening & v1.1 Release Candidate
This milestone added no new user-facing capability — it verified and
hardened everything above for release:
- **Security**: an insecure default `SECRET_KEY`/database password is
  now a release-blocking validation error specifically when
  `ENVIRONMENT=production` (previously advisory-only in every
  environment, including production).
- **A real, evidence-backed bug was found and fixed**: two Milestone 16
  migration revision ids exceeded Alembic's own `VARCHAR(32)` limit for
  `alembic_version.version_num` — invisible to the SQLite-backed test
  suite, only surfaced against real PostgreSQL. Renamed
  (`0004_strategy_recommendation_linkage` → `0004_strategy_linkage`,
  `0005_continuous_intelligence_persistence` → `0005_ci_persistence`),
  with a permanent regression guard added so a future migration named
  too long fails the normal test suite immediately.
- **A genuine, deterministic frontend test-timing issue was root-caused
  and fixed globally**: `waitFor`'s own default 1000ms internal timeout
  (independent of vitest's 30s `testTimeout`) was too tight for a real
  async round-trip under load — raised to 5000ms suite-wide, not patched
  per-test.
- Full clean-Docker-rebuild verification, fresh-database and
  upgrade-path migration verification (with real data proven to survive
  the upgrade), a real backup/restore cycle proven end-to-end, and a
  comprehensive live end-to-end walkthrough (login through Continuous
  Intelligence and WebSocket delivery) using real accumulated data —
  documented in full in `docs/release/RELEASE_CHECKLIST_V1_1.md`.
- Documentation reconciliation: several stale/contradictory claims
  across `README.md`, `USER_GUIDE.md`, `docs/database/MIGRATIONS.md`,
  `DEPLOYMENT_GUIDE.md`, and `PRODUCTION_CONFIGURATION_GUIDE.md` were
  corrected — the last of which was missing an entire generation of
  Milestone 11-16 settings despite claiming to document "every setting."

## Migrations

Five migrations exist as of this release, current head `0005_ci_persistence`:

| Revision | Adds |
|---|---|
| `0001_baseline_schema` | Every table, driven directly from ORM metadata |
| `0002_auth_schema` | Authentication & Authorization Framework tables |
| `0003_risk_market_data_coverage` | `risk_assessments.market_data_coverage` (nullable) |
| `0004_strategy_linkage` | `strategy_evaluation_results.recommendation_result_id` (nullable) |
| `0005_ci_persistence` | `continuous_intelligence_state` (new table) |

All verified this milestone against real PostgreSQL, both from an empty
database and from a database at v1.0.0's own recorded state
(`0002_auth_schema`), with real data proven to survive the upgrade.

## Operational changes

New container-exec-only scripts (no HTTP endpoint for any of them):
`scripts/run_ingestion.py`, `scripts/run_entity_backfill.py`,
`scripts/run_market_data_refresh.py`,
`scripts/run_portfolio_intelligence_refresh.py`,
`scripts/run_continuous_intelligence.py`, and the read-only
`scripts/inspect_continuous_intelligence.py`. See
`docs/release/OPERATIONAL_RUNBOOK.md`.

New environment variables — see
`docs/release/PRODUCTION_CONFIGURATION_GUIDE.md` for the complete,
current list. All new settings default to their v1.0.0-compatible,
"off" or safe-default state; an existing v1.0.0 deployment upgrading
with no `.env` changes behaves identically to before, except for the
new production-secret validation check (§Compatibility below).

## Compatibility

- **The `/api/v1` contract is unchanged.** No endpoint added, removed,
  renamed, or had a breaking field change since v1.0.0 — every new
  capability surfaced through existing endpoints (additive response
  fields only, e.g. `RiskAssessment.market_data_coverage`,
  `StrategyEvaluationResult.recommendation_result_id`), new WebSocket
  event types, or new operational scripts.
- **One behavior change**: a deployment with `ENVIRONMENT=production`
  and an insecure default `SECRET_KEY` or `POSTGRES_PASSWORD` will now
  show `startup_validation_passed: false` in its health/startup
  logging (a new blocking-severity validation check) — it will **not**
  fail to start (this codebase never hard-exits on a validation
  failure, by long-standing design), but the problem is now impossible
  to miss via `/api/v1/health`. Any real production deployment should
  already have real secrets configured, in which case this is a no-op.
- Every other new setting defaults to `false`/disabled/unset — a v1.0.0
  deployment's `.env`, carried forward unchanged, produces identical
  runtime behavior to before, aside from the secret-validation check
  above.

## Test suite

- Backend: **3197 passed, 0 failed** (full suite).
- Frontend: **425 passed, 0 failed** (84/84 test files); typecheck and
  lint (`--max-warnings 0`) both clean; production build succeeds.

## Known limitations

See `docs/release/KNOWN_LIMITATIONS.md` for the complete, current list,
organized by milestone. Highlights carried into this release candidate:

- No live organic market-movement verification this cycle (real markets
  were closed for the entire test window) — covered by automated tests.
- No real Anthropic API key was available in the test environment, so
  Research/Portfolio Intelligence's LLM-dependent behavior beyond
  authentication/routing is not independently verified this milestone
  (unchanged, pre-existing dependency, not new).
- Browser acceptance remains unverified — Chrome browser automation
  tooling has not been available in any milestone through M17.
- No distributed event bus; cross-process WebSocket event *coordination*
  is solved (Milestone 16), cross-process event *fan-out* to a
  different replica's connected clients is not.
- State/suppression/locking fall back to in-memory (restart-unsafe,
  single-process) automatically whenever PostgreSQL is unreachable at
  startup — a graceful degradation, not a silent failure.

## Upgrade procedure

1. Back up the database first (`docs/release/ADMINISTRATOR_GUIDE.md`
   "Database" section has the exact, tested procedure).
2. Deploy the new application code/image — do **not** let it run yet if
   your process runs migrations automatically (this codebase's own
   images never do; migrations are always a separate, explicit step).
3. Run `alembic upgrade head` — safe against a live database (every
   migration is idempotent and existence-checked). Confirm
   `alembic current` reports `0005_ci_persistence`.
4. Start/restart the application.
5. Confirm `GET /api/v1/health` reports `HEALTHY` and `GET /api/v1/ready`
   reports `ready: true` before routing production traffic.
6. Optional: review `docs/release/PRODUCTION_CONFIGURATION_GUIDE.md` for
   any of the new Milestone 11-16 settings you want to enable (all
   default off/safe).

## Rollback considerations

- **Application code**: rolling back to a pre-Milestone-11 image against
  a database already migrated to `0005_ci_persistence` works — every
  migration since `0001` is purely additive (new nullable columns, one
  new table); older code simply never reads the new column/table.
- **Database**: `alembic downgrade <revision>` is supported for every
  revision but is destructive to any data added since (a real
  `DROP TABLE`/`DROP COLUMN`) — a last resort, not routine rollback.
  Restoring from the backup taken in step 1 of the upgrade procedure is
  the safer path if a genuine rollback is ever needed.
- **No v1.0.0 behavior was changed** by any of Milestones 11-17 except
  the one documented production-secret validation check above — rolling
  back the application code alone (without a database downgrade) is
  expected to be safe in the overwhelming majority of cases.
