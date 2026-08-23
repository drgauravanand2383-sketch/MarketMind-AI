"""Regression tests for `0004_strategy_linkage` and
`0005_ci_persistence` (Milestone 16 §4/§18) — the
migrations adding the `recommendation_result_id` column to
`strategy_evaluation_results` and creating the `continuous_intelligence_state`
table. Exercises the real Alembic upgrade/downgrade path against a
throwaway SQLite database, the same substitution
`test_auth_schema_migration.py` and every other migration test in this
codebase uses in place of a live PostgreSQL server.
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
from app.repositories.continuous_intelligence.postgres.repository import (
    PostgresContinuousIntelligenceStateRepository,
)

ALEMBIC_INI_PATH = "alembic.ini"
CONTINUOUS_INTELLIGENCE_TABLE = "continuous_intelligence_state"
STRATEGY_RESULTS_TABLE = "strategy_evaluation_results"


@pytest.fixture
def sqlite_db_path() -> str:
    path = os.path.join(tempfile.gettempdir(), f"mm_m16_migration_test_{uuid.uuid4().hex}.db")
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


def _column_names(sqlite_db_path: str, table: str) -> set[str]:
    connection = sqlite3.connect(sqlite_db_path)
    try:
        return {row[1] for row in connection.execute(f"PRAGMA table_info('{table}')")}
    finally:
        connection.close()


def _pk_columns(sqlite_db_path: str, table: str) -> set[str]:
    connection = sqlite3.connect(sqlite_db_path)
    try:
        return {row[1] for row in connection.execute(f"PRAGMA table_info('{table}')") if row[5] > 0}
    finally:
        connection.close()


# --- 0005: continuous_intelligence_state -----------------------------------------------------------


def test_upgrade_head_creates_continuous_intelligence_state_table(
    alembic_config: Config, sqlite_db_path: str
) -> None:
    command.upgrade(alembic_config, "head")

    assert CONTINUOUS_INTELLIGENCE_TABLE in _table_names(sqlite_db_path)
    assert {"domain", "key", "value", "observed_at"}.issubset(
        _column_names(sqlite_db_path, CONTINUOUS_INTELLIGENCE_TABLE)
    )


def test_continuous_intelligence_state_has_composite_domain_key_primary_key(
    alembic_config: Config, sqlite_db_path: str
) -> None:
    command.upgrade(alembic_config, "head")

    assert _pk_columns(sqlite_db_path, CONTINUOUS_INTELLIGENCE_TABLE) == {"domain", "key"}


def test_downgrade_from_head_removes_only_continuous_intelligence_state_table(
    alembic_config: Config, sqlite_db_path: str
) -> None:
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "0004_strategy_linkage")

    remaining = _table_names(sqlite_db_path)
    assert CONTINUOUS_INTELLIGENCE_TABLE not in remaining
    assert "watchlists" in remaining  # a 0001 table, untouched by this downgrade


def test_downgrade_to_base_removes_continuous_intelligence_state_table_too(
    alembic_config: Config, sqlite_db_path: str
) -> None:
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")

    assert CONTINUOUS_INTELLIGENCE_TABLE not in _table_names(sqlite_db_path)


def test_postgres_continuous_intelligence_repository_works_against_the_migrated_schema(
    alembic_config: Config, sqlite_db_path: str
) -> None:
    """Closes the loop: the real Alembic-created schema is actually usable
    by the repository Continuous Intelligence depends on. Sync test
    calling `asyncio.run()` itself, same reasoning as
    `test_auth_schema_migration.py`'s own equivalent test."""
    command.upgrade(alembic_config, "head")

    async def _exercise_repository() -> tuple[object, datetime]:
        engine = create_async_engine(f"sqlite+aiosqlite:///{sqlite_db_path}")
        try:
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            repository = PostgresContinuousIntelligenceStateRepository(session_factory)

            now = datetime.now(UTC)
            await repository.put("MARKET", "dell", {"price": 100.0}, now)
            row = await repository.get("MARKET", "dell")
            assert row is not None
            return row
        finally:
            await engine.dispose()

    value, observed_at = asyncio.run(_exercise_repository())
    assert value == {"price": 100.0}


# --- 0004: strategy_evaluation_results.recommendation_result_id -----------------------------------------------------------


def test_upgrade_head_adds_recommendation_result_id_to_strategy_results(
    alembic_config: Config, sqlite_db_path: str
) -> None:
    command.upgrade(alembic_config, "head")

    assert "recommendation_result_id" in _column_names(sqlite_db_path, STRATEGY_RESULTS_TABLE)


def test_downgrade_from_head_removes_recommendation_result_id_column(
    alembic_config: Config, sqlite_db_path: str
) -> None:
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "0003_risk_market_data_coverage")

    assert "recommendation_result_id" not in _column_names(sqlite_db_path, STRATEGY_RESULTS_TABLE)
    assert STRATEGY_RESULTS_TABLE in _table_names(sqlite_db_path)  # table itself untouched


def test_upgrade_from_a_stamped_only_baseline_skips_the_column_gracefully(
    alembic_config: Config, sqlite_db_path: str
) -> None:
    """The complementary case: a database whose `alembic_version` reads
    `0003` via `stamp` alone (table never actually created — the same
    "stamped baseline" scenario `test_auth_schema_migration.py` exercises
    for `0002`) upgrades to head without error, and — correctly — without
    the column either, since `0004`'s own table-existence check means
    there is no table yet to add it to. Table creation remains `0001`'s
    responsibility; this only proves `0004` degrades gracefully rather
    than raising."""
    command.stamp(alembic_config, "0003_risk_market_data_coverage")
    assert STRATEGY_RESULTS_TABLE not in _table_names(sqlite_db_path)

    command.upgrade(alembic_config, "head")  # must not raise

    assert STRATEGY_RESULTS_TABLE not in _table_names(sqlite_db_path)
