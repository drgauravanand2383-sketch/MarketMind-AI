"""Tests for the Alembic migration environment: config loading, and a
real upgrade/downgrade cycle against a throwaway SQLite database (the
same in-memory-database-via-file substitution every other repository test
in this codebase uses in place of a live PostgreSQL server).

`alembic.ini`'s own `sqlalchemy.url` is intentionally blank (see that
file's own comment) — every test here overrides it via
`Config.set_main_option`, exactly the mechanism `alembic/env.py`'s
`_database_url()` is written to respect.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import uuid

import pytest
from alembic.config import Config

from alembic import command
from app.operations.migrations.discovery import collect_table_names

ALEMBIC_INI_PATH = "alembic.ini"


@pytest.fixture
def sqlite_db_path() -> str:
    path = os.path.join(tempfile.gettempdir(), f"mm_alembic_test_{uuid.uuid4().hex}.db")
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


def test_alembic_config_loads() -> None:
    config = Config(ALEMBIC_INI_PATH)
    assert config.get_main_option("script_location") == "alembic"


def test_upgrade_head_creates_every_discovered_table(alembic_config: Config, sqlite_db_path: str) -> None:
    command.upgrade(alembic_config, "head")

    created = _table_names(sqlite_db_path)
    expected = set(collect_table_names())
    assert expected.issubset(created)


def test_upgrade_head_creates_alembic_version_table(alembic_config: Config, sqlite_db_path: str) -> None:
    command.upgrade(alembic_config, "head")

    assert "alembic_version" in _table_names(sqlite_db_path)


def test_upgrade_head_is_idempotent(alembic_config: Config, sqlite_db_path: str) -> None:
    """Running `upgrade head` twice against the same database must not raise."""
    command.upgrade(alembic_config, "head")
    command.upgrade(alembic_config, "head")

    assert "alembic_version" in _table_names(sqlite_db_path)


def test_downgrade_base_drops_every_created_table(alembic_config: Config, sqlite_db_path: str) -> None:
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")

    remaining = _table_names(sqlite_db_path)
    for table_name in collect_table_names():
        assert table_name not in remaining


def test_current_revision_is_the_head_after_upgrade(alembic_config: Config, sqlite_db_path: str) -> None:
    command.upgrade(alembic_config, "head")

    connection = sqlite3.connect(sqlite_db_path)
    try:
        (version,) = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    finally:
        connection.close()
    assert version == "0006_alert_explanation"


# --- Milestone 16 regression: revision id width vs alembic_version column -------------------------

# Alembic's own `alembic_version.version_num` column is `VARCHAR(32)` by
# default (not something this codebase configures — Alembic's own
# built-in default). A revision id longer than this is accepted silently
# by SQLite (no length enforcement) but fails against a real PostgreSQL
# database with `StringDataRightTruncationError` — exactly what happened
# during this milestone's own live Docker acceptance testing with the
# original `0004_strategy_recommendation_linkage`/
# `0005_continuous_intelligence_persistence` names (36/40 characters),
# invisible to every SQLite-backed migration test in this file and
# `test_continuous_intelligence_persistence_migration.py` until then.
_ALEMBIC_VERSION_COLUMN_WIDTH = 32


def test_every_migration_revision_id_fits_the_alembic_version_column() -> None:
    from alembic.script import ScriptDirectory

    config = Config(ALEMBIC_INI_PATH)
    script_directory = ScriptDirectory.from_config(config)
    revisions = list(script_directory.walk_revisions())
    assert revisions, "expected at least one migration to be discovered"

    for revision in revisions:
        assert len(revision.revision) <= _ALEMBIC_VERSION_COLUMN_WIDTH, (
            f"Revision id {revision.revision!r} is {len(revision.revision)} characters, "
            f"exceeding alembic_version.version_num's {_ALEMBIC_VERSION_COLUMN_WIDTH}-character "
            "column width — this upgrades fine against SQLite but fails against real PostgreSQL."
        )
