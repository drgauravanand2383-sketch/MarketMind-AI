# MarketMind AI — Backend Architecture

Final backend documentation, produced by Sprint 54 (Production Hardening &
Release Readiness). Covers the complete backend as of Sprint 54 — the
last planned backend sprint. This document describes what exists; it
introduces no new business behavior.

## 1. Architecture Overview

MarketMind AI's backend is a modular, layered, dependency-injected Python
3.13 / FastAPI application. Every domain capability (screening, signal
detection, alerts, recommendations, strategy evaluation, risk analytics,
backtesting, explainability, and more) is built as an independent
**vertical slice** with the same four layers:

```
app/<domain>/
  models.py       Domain — fully typed Pydantic models, no I/O
  exceptions.py    Domain — typed exception hierarchy for that engine
  engine.py         Application — the *Service class: business logic,
                     orchestration, pure/deterministic scoring
  __init__.py        Public exports

app/repositories/<domain>/
  repository.py     Repository abstraction — an ABC (Base*Repository)
  postgres/
    models.py        Infrastructure — SQLAlchemy ORM models
    mapper.py         Infrastructure — domain model <-> ORM model translation
    repository.py      Infrastructure — Postgres*Repository, implements the ABC
```

**Dependency direction is strictly inward.** Domain layers
(`models.py`/`engine.py`) know nothing about SQLAlchemy, FastAPI, or any
concrete infrastructure — they depend only on an abstract
`Base*Repository` (and, since Sprint 52, on other already-built
Application-layer services injected directly). Infrastructure
(`postgres/*`) depends on the domain layer, never the reverse. This is
Clean Architecture applied consistently across every one of the ~20
domain/engine packages built across Sprints 1-53.

**Composition root.** `app/bootstrap.py` is the single place every
concrete component gets constructed and wired together — one
`build_<component>()` function per component, all invoked from
`bootstrap_application_state(app: FastAPI)`, populating `app.state`. No
other module constructs a repository, engine, or provider itself. This
is what makes the dependency graph (below) auditable in one file.

**Graceful degradation, never a startup crash.** Every `build_*_repository`
function catches its own construction failure and returns `None` rather
than raising; every `build_*_service` function short-circuits to `None`
when a dependency is `None`. A missing `ANTHROPIC_API_KEY`, an
unreachable PostgreSQL server, or an uninstalled optional dependency
(ChromaDB) degrades the affected component to unavailable — the
application still starts. Sprint 54's `StartupValidationService` makes
this degradation *visible* (a structured report) rather than changing it.

## 2. Dependency Graph

Reuse chains as of Sprint 54 (`A -> B` means "A is constructed with B
injected"):

```
PostgreSQLSettings ─────────────────────┐
                                          v
                              Postgres*Repository (x10)
                                          │
        ┌─────────────────────────────────┼──────────────────────────────┐
        v                                 v                                v
ScreeningEngine              SignalDetectionService              AlertService
(screening_repository)       (signal_repository)         (alert_rule_repository,
                                                            alert_repository)
        │                                 │                                │
        └───────────────┬─────────────────┴────────────────┬───────────────┘
                         v                                  v
              PortfolioRecommendationService      (consumes CandidateEvidence
              (recommendation_repository)          supplied by the caller —
                         │                          never calls the above itself)
                         v
              StrategyEvaluationService
              (strategy_repository)
                         │
                         v
              RiskAnalyticsService
              (risk_repository)
                         │
        ┌────────────────┴─────────────────┐
        v                                    v
BacktestingService                ExplainabilityService
(backtesting_repository,          (explainability_repository,
 recommendation_service,           recommendation_service,
 strategy_service,                 strategy_service,
 risk_service)                     risk_service,
                                    backtesting_service)
```

Two distinct reuse disciplines coexist by design:

- **Sprints 44-51 (Screening → Risk):** each engine *consumes* an
  already-computed object the caller supplies directly as a method
  parameter (e.g. `AlertService` takes a `SignalResult`) — it never calls
  back into the engine that produced it.
- **Sprints 52-53 (Backtesting, Explainability):** these two engines are
  constructed with the *actual service instances* of everything upstream
  injected, and call those services' read-only `get_result`/`get_evaluation`/
  `get_assessment`/`get_run` methods to resolve id references. They never
  call the generate/evaluate/assess/run methods — only read already-stored
  results. This is what "replay" and "explain" fundamentally are: lookups
  across already-computed pipeline output, not re-computation.

Sprint 54 adds a third, orthogonal graph — **operational infrastructure**
— with no dependency on or from the domain graph above:

```
StdlibStructuredLogger    InMemoryMetricsRecorder    InMemoryProfiler
HealthCheckService          (reads every repository's own health_check())
ConfigurationValidationService
        v
StartupValidationService (composes ConfigurationValidationService;
                           reads app.state + app.operations.migrations
                           .discovery.collect_table_names())
```

## 3. Service Catalog

| Service | Package | Repository | Sprint |
|---|---|---|---|
| `WatchlistService` | `app.watchlist` | `watchlist` | 44 |
| `ScreeningEngine` | `app.screening` | `screening` | 45 |
| `SignalDetectionService` | `app.signals` | `signals` | 47 |
| `AlertService` | `app.alerts` | `alerts` (2 repos: rule + alert) | 48 |
| `PortfolioRecommendationService` | `app.recommendations` | `recommendations` | 49 |
| `StrategyEvaluationService` | `app.strategy` | `strategy` | 50 |
| `RiskAnalyticsService` | `app.risk` | `risk` | 51 |
| `BacktestingService` | `app.backtesting` | `backtesting` | 52 |
| `ExplainabilityService` | `app.explainability` | `explainability` | 53 |
| `HealthCheckService` | `app.operations.health` | — | 54 |
| `ConfigurationValidationService` | `app.operations.validation` | — | 54 |
| `StartupValidationService` | `app.operations.validation` | — | 54 |

Also present (pre-Sprint-44 subsystems, unchanged, out of scope for this
sprint's own catalog but part of the running application): `NewsCollectorAgent`,
`CompanyResearchAgent`, `PortfolioIntelligenceAgent`, `MorningBriefGenerator`
(`app.agents.*`); `LLMService`, `MarketIntelligenceService`,
`EvidenceEngine`, `RelationshipEngine`, `KnowledgeIngestionService`,
`GuardrailsService` (`app.services.*`); `Scheduler`/`APSchedulerService`
(`app.scheduler`); `WorkflowEngine` (`app.workflows`).

## 4. Repository Catalog

Every repository follows the identical shape: an abstract `Base*Repository`
(ABC) in `app/repositories/<name>/repository.py`, and one concrete
`Postgres*Repository` in `app/repositories/<name>/postgres/repository.py`,
backed by its own independent SQLAlchemy `DeclarativeBase` subclass (see
§9 — this codebase has ten separate `Base` classes, not one shared base).

| Repository | Tables | Domain models |
|---|---|---|
| `alerts` | `alert_rules`, `alerts` | `app.alerts.models` |
| `backtesting` | `backtest_requests`, `backtest_runs`, `backtest_results` | `app.backtesting.models` |
| `explainability` | `explainability_requests`, `explainability_results` | `app.explainability.models` |
| `knowledge` | `knowledge_records` | `app.knowledge.models` |
| `recommendations` | `recommendation_requests`, `recommendation_results` | `app.recommendations.models` |
| `risk` | `risk_assessment_requests`, `risk_assessments` | `app.risk.models` |
| `screening` | `screening_profiles` | `app.screening.models` |
| `signals` | `signal_definitions` | `app.signals.models` |
| `strategy` | `investment_strategies`, `strategy_evaluation_results` | `app.strategy.models` |
| `watchlist` | `watchlists`, `watchlist_items`, `watchlist_snapshots` | `app.watchlist.models` |

`app.operations.migrations.discovery.collect_table_names()` is the
single, live source of truth for this table — call it rather than
trusting this table to stay in sync by hand.

## 5. Domain Packages (Sprints 44-53)

| Sprint | Package | Purpose |
|---|---|---|
| 44 | `app.watchlist` | Curated ticker collections with intelligence snapshots |
| 45 | `app.screening` | Rule-based company screening |
| 46 | `app.market_data` + `app.providers.market_data` | Normalized market data abstraction (mock provider only — no live feed) |
| 47 | `app.signals` | Condition-based signal detection over market data snapshots |
| 48 | `app.alerts` | Rule-based alert generation with cooldown/dedup, from signals |
| 49 | `app.recommendations` | Weighted multi-component recommendation scoring |
| 50 | `app.strategy` | Population-level strategy alignment evaluation |
| 51 | `app.risk` | Portfolio risk analytics (HHI-based + honest proxies) |
| 52 | `app.backtesting` | Deterministic replay of the above pipeline across historical snapshots |
| 53 | `app.explainability` | Deterministic explanation & performance attribution over the above pipeline's output |

Every domain package's own module docstrings are the authoritative,
detailed design record for that engine — this document intentionally
does not restate formulas already documented at the source (see each
`app/<domain>/engine.py`'s own docstring for exact scoring/attribution
formulas).

## 6. Configuration

All configuration is `pydantic_settings.BaseSettings`, loaded from
environment variables / `.env` — see `app/config/models.py` (per-domain
sections: `PostgreSQLSettings`, `RedisSettings`, `ChromaDBSettings`,
`AnthropicSettings`, `EmbeddingProviderSettings`, `RSSSettings`,
`LoggingSettings`, `LLMSettings`, `SchedulerSettings`, `APISettings`) and
`app.bootstrap.AppSettings` (the flatter settings class the composition
root actually reads for cross-cutting values like `environment`,
`log_level`, `watchlist_max_size`, and the various `*_max_*` engine
limits). See `.env.example` at the repository root for every documented
environment variable and its default.

**Known quirk:** several settings fields carry a `validation_alias` to
preserve a previously-documented env var name that doesn't follow that
section's own prefix convention (e.g. `PostgreSQLSettings.database_url`
is aliased to `DATABASE_URL`, not `POSTGRES_DATABASE_URL`). Because
`populate_by_name` is not enabled, constructing one of these settings
classes directly in code must use the **alias**, not the python attribute
name, as the keyword argument (`PostgreSQLSettings(DATABASE_URL=...)`,
not `PostgreSQLSettings(database_url=...)`) — the attribute name only
works when the value comes from the environment. This affects
`PostgreSQLSettings.database_url`, `RedisSettings.redis_url`,
`AnthropicSettings.model`, `LoggingSettings.level`, and
`APISettings.allowed_origins`.

`app.operations.validation.ConfigurationValidationService` (Sprint 54)
validates already-loaded settings objects for release readiness — see §12.

## 7. Deployment Prerequisites

- Python 3.13, dependencies per `backend/pyproject.toml`.
- A reachable PostgreSQL 16 server (see `docker-compose.yml` at the
  repository root for a local instance) — every repository degrades to
  `None`/unavailable without one, never crashes startup.
- `ANTHROPIC_API_KEY` set for any LLM-backed agent/service to function;
  its absence is caught by `ConfigurationValidationService`/
  `StartupValidationService` as an `ERROR`-severity (blocking) check.
- ChromaDB and a real embedding provider are **optional** — neither is
  wired to a concrete implementation as of Sprint 54; `knowledge_repository`/
  `embedding_provider` are `None` without them, by design (see
  `app.bootstrap.build_knowledge_repository`/`build_embedding_provider`'s
  own docstrings).
- Redis is configured (`RedisSettings`) but not yet consumed by any
  concrete component as of Sprint 54 — reserved for a future sprint.
- Run `alembic upgrade head` (see §8) before first startup, or startup's
  own `StartupValidationService`'s `model_metadata_discovery` check will
  still pass (it only checks tables are *defined*, not that they exist in
  the target database) — a repository whose table doesn't exist yet will
  surface as `UNHEALTHY` via `HealthCheckService.check_repositories()`.

## 8. Migration Workflow

See `docs/database/MIGRATIONS.md` for the full guide. In brief:

```bash
cd backend
alembic upgrade head      # apply every migration (baseline: 0001_baseline_schema)
alembic current            # show the applied revision
alembic downgrade base    # drop every table this codebase defines
```

`alembic/env.py` reads connection settings from `PostgreSQLSettings` (the
same class every repository's own `build_*_repository` reads) — no
separate, divergent connection configuration exists. `target_metadata`
is `app.operations.migrations.discovery.collect_metadata()` — the same
collection point `StartupValidationService`'s "model metadata discovery"
check uses.

## 9. Startup Validation

`app.operations.validation.StartupValidationService` (Sprint 54) runs
automatically at the end of `bootstrap_application_state()` and its
report is stored at `app.state.startup_validation_report`. It never
blocks or crashes startup — a failed check is a signal for an operator
(or a future health/readiness HTTP endpoint) to act on, not an exception.

Three check groups, composed into one `ValidationReport`:

1. **`validate_components`** — dependency injection wiring: every name in
   `DEFAULT_REQUIRED_COMPONENTS` (every domain repository/service built
   by `bootstrap_application_state`) is present and non-`None`
   (`ERROR` if missing); no component name was registered twice
   (`ERROR`); no two different `app.state` attribute names hold the exact
   same object instance (`WARNING` — an aliasing bug class).
2. **`validate_metadata_discovery`** — every repository package's
   `Base.metadata` is discoverable (`ERROR` if none found) and no two
   packages claim the same table name (`ERROR`) — reuses
   `app.operations.migrations.discovery`, the same collection point
   Alembic's own `env.py` uses.
3. **`validate_configuration`** — see §12 below (delegates entirely to
   `ConfigurationValidationService`, injected).

## 10. Health Model

`app.operations.health.HealthCheckService` (Sprint 54) exposes **service
methods only** — no HTTP endpoint exists anywhere in this codebase for
health/readiness as of Sprint 54; a future API sprint wraps these methods
in a route.

- `RepositoryHealth` — one repository's own `health_check()` result,
  relayed verbatim (never recomputed); `UNHEALTHY` if `None` (not
  constructed) or if `health_check()` itself raises (caught, never
  propagated).
- `ServiceHealth` — `HEALTHY` iff dependency injection constructed the
  service (non-`None`); services hold no connection of their own to
  probe.
- `DependencyHealth` — for an external dependency with no repository
  wrapper (reserved for future use — nothing currently populates this).
- `ApplicationHealth` — aggregates all of the above:
  `UNHEALTHY` if any component is `UNHEALTHY`, else `DEGRADED` if any is
  `DEGRADED`, else `HEALTHY`.
- `ReadinessStatus` — `ready=False` whenever any repository or service is
  `UNHEALTHY`; a `DEGRADED` dependency does not block readiness.

## 11. Logging Architecture

`app.operations.logging.BaseStructuredLogger` (Sprint 54) — five
categories (`APPLICATION`/`REPOSITORY`/`SERVICE`/`STARTUP`/`VALIDATION`),
every emission a fully-typed `LogRecord` (never a free-form string).
`StdlibStructuredLogger` (wraps the standard-library `logging` module —
not a vendor SDK) is what `app.bootstrap` wires as
`app.state.structured_logger`, emitting each `LogRecord` as JSON via the
already-configured `marketmind.bootstrap` logger.
`InMemoryStructuredLogger` captures records in a list — for tests, or a
future caller that wants to inspect what was logged without parsing
stdlib output.

**Operational note:** `app.bootstrap.configure_logging()` calls
`logging.basicConfig(force=True)`, which clears every handler already
attached to the root logger. This is correct for a real process (logging
is configured exactly once, at startup) but matters if `bootstrap_application_state()`
is ever called more than once in the same process — the test suite's own
`tests/lifecycle/` module isolates this via a save/restore fixture rather
than changing this behavior.

## 12. Metrics Architecture

`app.operations.metrics.BaseMetricsRecorder` (Sprint 54) — counters via
`increment(name, **labels)`, durations via `record_duration(name, seconds,
**labels)`. Six named constants for the metrics this sprint specifically
calls out: `METRIC_SERVICE_CALLS`, `METRIC_REPOSITORY_CALLS`,
`METRIC_VALIDATION_FAILURES`, `METRIC_STARTUP_DURATION_SECONDS`,
`METRIC_BACKTEST_RUNS`, `METRIC_RECOMMENDATION_GENERATIONS`.
`InMemoryMetricsRecorder` is the only concrete implementation — no
Prometheus/StatsD/OpenTelemetry integration exists; `app.bootstrap` wires
it as `app.state.metrics_recorder` and records
`METRIC_STARTUP_DURATION_SECONDS` once, at the end of bootstrap. A future
sprint can add a vendor-backed `BaseMetricsRecorder` without changing any
caller.

## 13. Profiling Architecture

`app.operations.profiling.BaseProfiler` (Sprint 54) — plain wall-clock
timing (`time.perf_counter()`) via `record(operation, duration_seconds)`
or the `measure(operation)` context manager, usable as either
`with profiler.measure(...):` or `async with profiler.measure(...):` (every
timed operation in this codebase is async in practice — repository calls,
service methods, pipeline execution). No sampling profiler, no external
tooling. `InMemoryProfiler` is the only concrete implementation, wired as
`app.state.profiler`.

## 14. Testing Strategy

Consistent across all ~20 sprints: an in-memory SQLite database (via
`aiosqlite`) stands in for PostgreSQL in every repository test — the same
SQLAlchemy async engine code path, no live server required. Coverage
categories, per domain package: domain model validation, repository CRUD
(direct, bypassing the service), mapper round-trips (including the
naive-datetime-from-SQLite `_ensure_aware` normalization every mapper
performs), engine/service unit tests (scoring, evaluation, orchestration),
and `tests/test_bootstrap.py` (one pair of tests per `build_*_repository`/
`build_*_service` function, verifying graceful `None` degradation).

Sprint 54 adds three testing categories with no earlier equivalent:

- **`tests/operations/`** — unit tests for every operational abstraction
  (migrations discovery, the Alembic environment itself via a real
  `alembic upgrade`/`downgrade` cycle against a throwaway SQLite file,
  logging, metrics, profiling, health, configuration/startup validation).
- **`tests/stress/`** — large CRUD batches (500 rows), large reads,
  concurrent read safety (`asyncio.gather` over many repository calls),
  deterministic ordering (`list_*` returns every row exactly once,
  regardless of order), and bulk persistence, across four representative
  repositories (Risk, Recommendations, Watchlist).
- **`tests/lifecycle/`** — the full `bootstrap_application_state()`/
  `shutdown_application_state()` sequence against a real `FastAPI` app
  instance (not the individual `build_*` unit tests already in
  `tests/test_bootstrap.py`), including the startup validation report
  and metrics it produces.

Verification methodology per sprint (unchanged since Sprint 45): a
throwaway virtual environment, a hand-written sanity script exercising
the new engine end-to-end before the full pytest suite is written, then
the scoped test suite, `tests/test_bootstrap.py`, and the full `pytest
tests` suite — expecting zero regressions every time.

## 15. Known Limitations

- **No live market data provider.** `app.providers.market_data` ships
  only `MockMarketDataProvider` (deterministic, hash-derived) — Sprint 46
  explicitly forbade connecting to a real feed. `NormalizationService`
  and the `MarketDataProvider` interface are ready for a real
  implementation to be dropped in.
- **No broker integration, no trade execution** anywhere in this
  codebase, by explicit constraint in every sprint from 44 onward.
- **No HTTP API surface for the domain engines themselves, only for
  operational introspection.** Sprint 55 (Phase 2) added `/api/v1` —
  see `docs/architecture/API_ARCHITECTURE.md` — but it exposes only
  read-only health/version/configuration/capabilities/services endpoints
  reusing Sprint 54's operational services; no domain engine (Screening
  through Explainability) has a CRUD route yet. Each remains a
  DI-ready service class, not a route.
- **Authentication exists but protects nothing yet.** Sprint 56 added
  `app/auth/` — see `docs/architecture/AUTHENTICATION_ARCHITECTURE.md` —
  and `AuthenticationMiddleware` is registered on the live application
  (resolves a bearer token into `request.state.principal`), but no
  `/api/v1` route requires authentication or applies a policy yet; every
  Sprint 55 endpoint remains publicly reachable. `require_policy(...)` is
  ready-to-use, unused infrastructure until a future sprint protects a route.
- **Redis, ChromaDB, and an embedding provider are configured but not
  concretely wired.** `RedisSettings` has no consumer;
  `build_knowledge_repository`/`build_embedding_provider` degrade to
  `None` without a real ChromaDB/embedding implementation.
- **No vendor metrics/logging/tracing backend.** Sprint 54's
  `InMemoryMetricsRecorder`/`StdlibStructuredLogger` are real, working
  defaults — not placeholders — but nothing exports to Prometheus,
  Datadog, OpenTelemetry, or similar.
- **`BacktestPeriod.portfolio_value` is a score-derived proxy, not a real
  P&L simulation** (see `app.backtesting.engine`'s own docstring) — no
  real historical price, position size, or trade fill exists anywhere in
  this pipeline, by design.

## 16. Extension Points

- **Live Market Data Providers.** Implement `app.providers.market_data
  .provider.MarketDataProvider` (13 abstract methods) and register it in
  `app.bootstrap.build_market_data_provider()` in place of
  `MockMarketDataProvider` — every downstream consumer (`NormalizationService`,
  `SignalDetectionService`, and beyond) is already written against the
  abstract interface, not the mock.
- **Broker Integrations.** No abstraction exists yet — this is new
  surface area, not a drop-in extension point. Follow the established
  pattern (`app/providers/<name>/{provider.py, models.py}` + a
  `Base*Provider` ABC) when it is built.
- **Notification Providers.** `app.alerts.models.NotificationChannel`
  already enumerates 8 channels (EMAIL/PUSH/SMS/TELEGRAM/DISCORD/SLACK/
  WEBHOOK/IN_APP) and `Alert.eligible_channels` already computes which
  apply — no channel *delivery* implementation exists yet; that is the
  extension point (a `Base*NotificationSender` per channel, invoked by a
  new orchestration layer consuming `AlertService`'s already-computed
  output, mirroring the Backtesting/Explainability reuse discipline).
- **Frontend APIs.** `/api/v1` (Sprint 55) established the pattern —
  see `docs/architecture/API_ARCHITECTURE.md` §8 for exactly how a future
  sprint wraps each domain engine's own service methods (Screening
  through Explainability) in a CRUD router following the same
  dependency-injection, response-envelope, and exception-handling
  conventions already in place.
