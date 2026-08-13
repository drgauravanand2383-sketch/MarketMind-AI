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
      0001_baseline_schema.py   Baseline: every table, as of Sprint 54
```

## Why `target_metadata` is a *list*, not one `MetaData`

This codebase has **ten independent `DeclarativeBase` subclasses** — one
per repository package (`app.repositories.alerts.postgres.models.Base`,
`app.repositories.risk.postgres.models.Base`, and so on) — not a single
shared `Base`. `app/operations/migrations/discovery.py::collect_metadata()`
is the single place that list is defined; both `alembic/env.py` and
`app.operations.validation.startup.StartupValidationService`'s "model
metadata discovery" check import from it, so the two can never silently
diverge.

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
