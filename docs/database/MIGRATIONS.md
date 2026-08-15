# Database Migrations (Alembic)

Sprint 54 introduces the Alembic migration environment. It does not
change any repository's runtime behavior — repositories still connect
directly via SQLAlchemy async engines, exactly as every `build_*_repository`
function in `app/bootstrap.py` already did. Alembic exists to create and
evolve the schema those repositories read and write.

## Layout

```
backend/
  alembic.ini              Alembic config — sqlalchemy.url intentionally blank
  alembic/
    env.py                  Migration environment (async, reuses PostgreSQLSettings)
    script.py.mako           Template for new revisions
    versions/
      0001_baseline_schema.py       Baseline: every table, as of Sprint 54
      0002_auth_schema.py           Auth tables (Sprint 56's framework), added
                                     after `0001` shipped without them — see
                                     that revision's own docstring
      0003_risk_market_data_coverage.py
                                     Milestone 14: adds the nullable
                                     `market_data_coverage` JSON column to
                                     `risk_assessments`
      0004_strategy_linkage.py      Milestone 16 §12: adds the nullable
                                     `recommendation_result_id` column to
                                     `strategy_evaluation_results`, letting a
                                     stored strategy evaluation be traced back
                                     to the portfolio that produced it
      0005_ci_persistence.py        Milestone 16 §2-§5: creates
                                     `continuous_intelligence_state` — one
                                     generic `(domain, key)` table serving
                                     Continuous Intelligence's durable
                                     comparison state, suppression records,
                                     and cycle-lock claims
```

Current head: `0005_ci_persistence`. Every migration is column/table-existence-checked (never assumed) and is exercised by a real Alembic upgrade/downgrade cycle in `tests/operations/` — see
`tests/operations/test_alembic_environment.py` and
`tests/operations/test_continuous_intelligence_persistence_migration.py`.

## Why `target_metadata` is a *list*, not one `MetaData`

This codebase has **twelve independent `DeclarativeBase` subclasses** — one
per repository package (`app.repositories.alerts.postgres.models.Base`,
`app.repositories.risk.postgres.models.Base`, `app.auth.repositories
.postgres.models.Base`, `app.repositories.continuous_intelligence.postgres
.models.Base` (Milestone 16), and so on) — not a single shared `Base`.
`app/operations/migrations/discovery.py::collect_metadata()` is the single
place that list is defined; both `alembic/env.py` and
`app.operations.validation.startup.StartupValidationService`'s "model
metadata discovery" check import from it, so the two can never silently
diverge.

Historical note: the Auth framework's `Base` (Sprint 56) was built and
tested against an in-memory SQLite database only, and was never actually
added to this list — so despite being fully implemented and tested, its
tables never existed in any real Postgres deployment until `0002_auth_schema`
(a post-freeze release-blocking fix) both registered it here and added the
catch-up migration. `collect_metadata()`'s single-list design is what made
the gap easy to close correctly once found: registering the missing `Base`
is the entire fix, with no risk of `env.py`/`StartupValidationService`
disagreeing about the schema.

## Connection configuration

`alembic/env.py`'s `_database_url()` reuses `app.config.models
.PostgreSQLSettings` — the exact same settings class every
`build_*_repository` function in `app.bootstrap` reads, constructing the
URL the same way:

```python
settings.database_url or (
    f"postgresql+asyncpg://{settings.user}:{settings.password.get_secret_value()}"
    f"@{settings.host}:{settings.port}/{settings.db}"
)
```

`alembic.ini`'s own `sqlalchemy.url` is intentionally left blank — there
is exactly one place database credentials are assembled from environment
variables in this codebase, and it is not this file.

An already-configured `sqlalchemy.url` (set via `config.set_main_option`,
e.g. by a test running migrations against a throwaway SQLite database) is
always honored first — `PostgreSQLSettings` is only consulted as a
fallback. This is how `tests/operations/test_alembic_environment.py`
exercises the real migration environment without a live PostgreSQL
server.

## Async throughout

Every repository in this codebase already uses `create_async_engine`/
`asyncpg` — `alembic/env.py` follows the same convention
(`async_engine_from_config` + `connection.run_sync(...)`), never
introducing a sync driver (`psycopg2`) this codebase doesn't otherwise
depend on.

## The baseline migration

`0001_baseline_schema.py`'s `upgrade()`/`downgrade()` do not hand-write
column definitions. They drive directly off
`collect_metadata()` via SQLAlchemy's own `MetaData.create_all()`/
`drop_all()`:

```python
def upgrade() -> None:
    bind = op.get_bind()
    for metadata in collect_metadata():
        metadata.create_all(bind=bind, checkfirst=True)
```

This guarantees the baseline can never drift from the ORM models it
represents — there is no hand-transcription step to get wrong. Future
schema changes should be captured as new revisions in the conventional
Alembic way (`alembic revision --autogenerate -m "..."`, reviewed, then
committed) rather than by editing the baseline.

## Common commands

Run from `backend/`:

```bash
# Apply every migration up to the latest
alembic upgrade head

# Show the currently applied revision
alembic current

# Roll back everything this codebase defines
alembic downgrade base

# Generate a new revision (after changing a repository's ORM models)
alembic revision --autogenerate -m "describe the change"
```

## Known operational fix from Milestone 16: revision id length

Alembic's own `alembic_version.version_num` tracking column is
`VARCHAR(32)` by default — not something this codebase configures, an
Alembic built-in. A revision id longer than 32 characters is accepted
silently by SQLite (no length enforcement, so every SQLite-backed
migration test in this codebase's own suite passes regardless) but fails
against a real PostgreSQL database with `StringDataRightTruncationError`
the moment Alembic tries to record the new revision.

This actually happened during Milestone 16's live Docker acceptance
testing: the two new migrations were first authored as
`0004_strategy_recommendation_linkage` (36 characters) and
`0005_continuous_intelligence_persistence` (40 characters), both over the
limit, and both passed every local test before failing on the first real
`alembic upgrade head` against Postgres. They were renamed to
`0004_strategy_linkage` and `0005_ci_persistence` (21 and 19 characters).

A permanent regression guard now exists for this:
`tests/operations/test_alembic_environment.py
::test_every_migration_revision_id_fits_the_alembic_version_column`
enumerates every migration via `alembic.script.ScriptDirectory` and
asserts each revision id is ≤32 characters — so a future migration
authored with a name that's too long fails immediately in the normal
SQLite-backed test suite, without needing a live Postgres run to
discover it. **Keep every future revision id at 32 characters or fewer.**

## Known operational fix from Sprint 54

`alembic/env.py` calls `logging.config.fileConfig(config.config_file_name,
disable_existing_loggers=False)`. The `disable_existing_loggers=False` is
deliberate: `fileConfig`'s own default (`True`) disables every logger
that already exists and isn't explicitly listed in `alembic.ini`'s own
`[loggers]` section — which would silently and permanently disable every
`marketmind.*` application logger for the rest of the process if a
migration is ever run in the same process as the running application
(e.g. under test, or via an in-process migration runner). This was
discovered and fixed during Sprint 54's own full-suite verification.
