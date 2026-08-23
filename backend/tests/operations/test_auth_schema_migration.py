"""Regression tests for `0002_auth_schema` — the migration that creates
the Authentication & Authorization Framework's tables, missing from
`0001_baseline_schema` because `app.auth.repositories.postgres.models
.Base` was never registered in `app.operations.migrations.discovery`
(see that migration's own docstring for the full root-cause story).
Exercises the real Alembic upgrade/downgrade path — not the ad-hoc
`Base.metadata.create_all` fixture `tests/auth/repositories/postgres
/test_repository.py` uses — against a throwaway SQLite database, the
same substitution every other migration test in this codebase uses in
place of a live PostgreSQL server.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
import uuid
from datetime import UTC, datetime

import pytest
from alembic.config import Config
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from alembic import command
from app.auth.models.role import Role
from app.auth.models.user import User
from app.auth.repositories.postgres.repository import PostgresAuthRepository

ALEMBIC_INI_PATH = "alembic.ini"
AUTH_TABLES = ("auth_users", "auth_roles", "auth_revoked_tokens")


@pytest.fixture
def sqlite_db_path() -> str:
    path = os.path.join(tempfile.gettempdir(), f"mm_auth_migration_test_{uuid.uuid4().hex}.db")
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def alembic_config(sqlite_db_path: str) -> Config:
    config = Config(ALEMBIC_INI_PATH)
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{sqlite_db_path}")
    return config


def _table_names(sqlite_db_path: str) -> set[str]:
    connection = sqlite3.connect(sqlite_db_path)
    try:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        return {row[0] for row in rows}
    finally:
        connection.close()


def _unique_columns(sqlite_db_path: str, table: str) -> set[str]:
    """Column names covered by a single-column UNIQUE index on `table`."""
    connection = sqlite3.connect(sqlite_db_path)
    try:
        columns: set[str] = set()
        for row in connection.execute(f"PRAGMA index_list('{table}')"):
            _, index_name, is_unique = row[0], row[1], row[2]
            if not is_unique:
                continue
            info = connection.execute(f"PRAGMA index_info('{index_name}')").fetchall()
            if len(info) == 1:
                columns.add(info[0][2])
        return columns
    finally:
        connection.close()


def test_upgrade_head_creates_every_auth_table(alembic_config: Config, sqlite_db_path: str) -> None:
    command.upgrade(alembic_config, "head")

    created = _table_names(sqlite_db_path)
    for table in AUTH_TABLES:
        assert table in created


def test_upgrade_from_stamped_baseline_to_head_adds_auth_tables(alembic_config: Config, sqlite_db_path: str) -> None:
    """Reproduces the exact live-production scenario: a database whose
    `alembic_version` already reads `0001_baseline_schema` — `stamp`, not
    `upgrade`, so no table is created yet, mirroring a database that was
    migrated to `0001` back when `0001`'s own `collect_metadata()` call
    didn't yet include the auth `Base` — then upgraded to head must gain
    the auth tables via `0002_auth_schema` alone."""
    command.stamp(alembic_config, "0001_baseline_schema")
    before = _table_names(sqlite_db_path)
    assert not any(table in before for table in AUTH_TABLES)

    command.upgrade(alembic_config, "head")

    after = _table_names(sqlite_db_path)
    for table in AUTH_TABLES:
        assert table in after


def test_downgrade_from_head_removes_only_auth_tables(alembic_config: Config, sqlite_db_path: str) -> None:
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "0001_baseline_schema")

    remaining = _table_names(sqlite_db_path)
    for table in AUTH_TABLES:
        assert table not in remaining
    assert "watchlists" in remaining  # a 0001 table, untouched by the auth downgrade


def test_downgrade_to_base_removes_auth_tables_too(alembic_config: Config, sqlite_db_path: str) -> None:
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")

    remaining = _table_names(sqlite_db_path)
    for table in AUTH_TABLES:
        assert table not in remaining


def test_auth_users_has_unique_username_and_email(alembic_config: Config, sqlite_db_path: str) -> None:
    command.upgrade(alembic_config, "head")
    assert {"username", "email"}.issubset(_unique_columns(sqlite_db_path, "auth_users"))


def test_auth_roles_has_unique_name(alembic_config: Config, sqlite_db_path: str) -> None:
    command.upgrade(alembic_config, "head")
    assert "name" in _unique_columns(sqlite_db_path, "auth_roles")


def test_postgres_auth_repository_works_against_the_migrated_schema(
    alembic_config: Config, sqlite_db_path: str
) -> None:
    """Closes the loop: the real Alembic-created schema (not the ad-hoc
    `Base.metadata.create_all` fixture `tests/auth/repositories/postgres
    /test_repository.py` uses) is actually usable by the repository the
    live Auth API depends on.

    Deliberately a sync test that calls `asyncio.run()` itself after
    `command.upgrade()` returns, rather than an `async def` test — Alembic's
    own `env.py` calls `asyncio.run()` internally (see its module
    docstring), which raises if invoked from inside a already-running
    event loop, which an `async def` test under `asyncio_mode = "auto"`
    would be."""
    command.upgrade(alembic_config, "head")

    async def _exercise_repository() -> User:
        engine = create_async_engine(f"sqlite+aiosqlite:///{sqlite_db_path}")
        try:
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            repository = PostgresAuthRepository(session_factory)

            now = datetime.now(UTC)
            user = User(id="u1", username="alice", email="alice@example.com", created_at=now, updated_at=now)
            await repository.create_user(user, "hash1")
            role = Role(id="r1", name="ADMIN", permissions=("watchlist:read",))
            await repository.create_role(role)
            await repository.assign_role(user.id, role.id)

            fetched = await repository.get_user_by_username("alice")
            assert fetched is not None
            return fetched
        finally:
            await engine.dispose()

    fetched = asyncio.run(_exercise_repository())
    assert fetched.roles == ("r1",)
