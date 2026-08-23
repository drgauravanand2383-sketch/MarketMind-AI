"""Alembic migration environment for MarketMind AI.

Reuses existing infrastructure rather than duplicating it: the database
connection URL is built from `app.config.models.PostgreSQLSettings` — the
same settings class every `build_*_repository` function in
`app.bootstrap` already reads — and `target_metadata` is the same
`app.operations.migrations.discovery.collect_metadata()` collection point
`app.operations.validation.startup.StartupValidationService`'s own "model
metadata discovery" check uses. Neither the connection URL construction
nor the list of repository `Base` classes is duplicated anywhere else in
this codebase.

Async throughout, matching this codebase's own async-first convention
(every repository already uses `create_async_engine`/`asyncpg`) — no
sync driver (`psycopg2`) is introduced.

Supports both offline mode (`alembic upgrade head --sql`, emits SQL
without a live connection) and online mode (`alembic upgrade head`,
applies migrations against a live database).
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.config.models import PostgreSQLSettings
from app.operations.migrations.discovery import collect_metadata

config = context.config

if config.config_file_name is not None:
    # `disable_existing_loggers=False`: `logging.config.fileConfig`
    # defaults to disabling every logger that already exists and isn't
    # explicitly listed in `alembic.ini`'s own `[loggers]` section
    # (`root`/`sqlalchemy`/`alembic` only) — that would silently and
    # permanently disable every `marketmind.*` application logger for the
    # rest of the process whenever a migration runs in the same process
    # as the application (e.g. under test).
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = list(collect_metadata())


def _database_url() -> str:
    """The connection URL migrations run against.

    Honors an already-configured `sqlalchemy.url` first (set explicitly
    via `-x` / `config.set_main_option`, e.g. by tests running migrations
    against a throwaway SQLite database) — only when unset does this fall
    back to `PostgreSQLSettings`, mirroring every `build_*_repository`
    function in `app.bootstrap`.
    """
    configured = config.get_main_option("sqlalchemy.url")
    if configured:
        return configured
    settings = PostgreSQLSettings()
    return settings.database_url or (
        f"postgresql+asyncpg://{settings.user}:{settings.password.get_secret_value()}"
        f"@{settings.host}:{settings.port}/{settings.db}"
    )


def run_migrations_offline() -> None:
    """Emit migration SQL without a live database connection."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Apply migrations against a live database, via an async engine."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _database_url()
    connectable = async_engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)

    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
