"""Regression tests for `0010_ranked_asset_performance_windows` — the
migration adding the `performance_windows` JSON column to
`global_market_ranked_assets`. Exercises the real Alembic upgrade/downgrade
path against a throwaway SQLite database, the same substitution every
other migration test in this codebase uses in place of a live PostgreSQL
server (see `test_continuous_intelligence_persistence_migration.py`).
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
from app.global_markets.models import (
    DataFreshnessStatus,
    DataProvenance,
    NormalizedAssetSnapshot,
    PerformanceWindow,
    ReportCategory,
    WindowedPerformance,
)
from app.global_markets.ranked_asset import RankedAsset
from app.repositories.global_markets.postgres.ranked_asset_repository import PostgresRankedAssetRepository

ALEMBIC_INI_PATH = "alembic.ini"
RANKED_ASSETS_TABLE = "global_market_ranked_assets"
_COLUMN = "performance_windows"


@pytest.fixture
def sqlite_db_path() -> str:
    path = os.path.join(tempfile.gettempdir(), f"mm_0010_migration_test_{uuid.uuid4().hex}.db")
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


def test_upgrade_head_adds_performance_windows_column(alembic_config: Config, sqlite_db_path: str) -> None:
    command.upgrade(alembic_config, "head")

    assert _COLUMN in _column_names(sqlite_db_path, RANKED_ASSETS_TABLE)


def test_downgrade_from_head_removes_only_the_performance_windows_column(
    alembic_config: Config, sqlite_db_path: str
) -> None:
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "0009_global_market_reports")

    columns = _column_names(sqlite_db_path, RANKED_ASSETS_TABLE)
    assert _COLUMN not in columns
    assert {"id", "run_id", "category", "factor_scores", "snapshot"}.issubset(columns)  # table itself intact


def test_downgrade_to_base_removes_the_ranked_assets_table_too(
    alembic_config: Config, sqlite_db_path: str
) -> None:
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")

    assert RANKED_ASSETS_TABLE not in _table_names(sqlite_db_path)


def test_upgrade_from_a_stamped_only_baseline_skips_the_column_gracefully(
    alembic_config: Config, sqlite_db_path: str
) -> None:
    """A database whose `alembic_version` reads `0008` via `stamp` alone
    (the ranked-assets table never actually created) upgrades to head
    without error, and without the column — `0010`'s own table-existence
    check means there is no table yet to add it to."""
    command.stamp(alembic_config, "0008_global_market_ranked")
    assert RANKED_ASSETS_TABLE not in _table_names(sqlite_db_path)

    command.upgrade(alembic_config, "head")  # must not raise


def test_ranked_asset_repository_persists_performance_windows_against_the_migrated_schema(
    alembic_config: Config, sqlite_db_path: str
) -> None:
    """Closes the loop: the real Alembic-created schema actually round-trips
    a `RankedAsset`'s `performance_windows`."""
    command.upgrade(alembic_config, "head")

    now = datetime(2026, 9, 1, tzinfo=UTC)
    provenance = DataProvenance(
        source_timestamp=now, retrieved_at=now, provider="fixture", data_freshness_status=DataFreshnessStatus.LIVE
    )
    asset = RankedAsset(
        run_id="run-1",
        category=ReportCategory.US_EQUITY,
        rank=1,
        final_score=88.0,
        performance_windows=(
            WindowedPerformance(
                window=PerformanceWindow.Y5,
                start_value=10.0,
                end_value=34.0,
                percent_change=240.0,
                observation_start=datetime(2021, 9, 1, tzinfo=UTC),
                observation_end=now,
                periods_used=1250,
                is_complete=True,
            ),
        ),
        snapshot=NormalizedAssetSnapshot(
            ticker="AAPL", report_category=ReportCategory.US_EQUITY, price=100.0, provenance=provenance
        ),
    )

    async def _round_trip() -> RankedAsset:
        engine = create_async_engine(f"sqlite+aiosqlite:///{sqlite_db_path}")
        try:
            repository = PostgresRankedAssetRepository(async_sessionmaker(engine, expire_on_commit=False))
            await repository.replace_ranked_assets("run-1", ReportCategory.US_EQUITY, (asset,))
            return (await repository.list_ranked_assets("run-1", ReportCategory.US_EQUITY))[0]
        finally:
            await engine.dispose()

    fetched = asyncio.run(_round_trip())
    assert fetched.performance_windows[0].window is PerformanceWindow.Y5
    assert fetched.performance_windows[0].percent_change == 240.0
