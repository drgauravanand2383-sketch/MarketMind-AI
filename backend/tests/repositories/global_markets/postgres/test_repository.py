"""Tests for PostgresGlobalMarketRunRepository.

Run against an in-memory SQLite database via aiosqlite, exercising the
repository's own CRUD/uniqueness/health-check behavior directly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.global_markets.models import (
    CategoryRunOutcome,
    IntelligenceRun,
    IntelligenceRunStatus,
    ReportCategory,
)
from app.repositories.global_markets.postgres.models import Base
from app.repositories.global_markets.postgres.repository import PostgresGlobalMarketRunRepository
from app.repositories.global_markets.repository import DuplicateIntelligenceRunError

NOW = datetime(2026, 8, 29, 3, 0, tzinfo=UTC)


@pytest.fixture
async def repository() -> AsyncIterator[PostgresGlobalMarketRunRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PostgresGlobalMarketRunRepository(session_factory)
    finally:
        await engine.dispose()


def _run(run_id: str = "run-1", run_date: date = date(2026, 8, 29), **overrides: object) -> IntelligenceRun:
    defaults: dict[str, object] = {
        "id": run_id,
        "run_date": run_date,
        "status": IntelligenceRunStatus.RUNNING,
        "category_outcomes": (),
        "triggered_by": "scheduler",
        "started_at": NOW,
    }
    defaults.update(overrides)
    return IntelligenceRun(**defaults)  # type: ignore[arg-type]


# --- create_run / get_run -----------------------------------------------------------


async def test_create_run_then_get_returns_it(repository: PostgresGlobalMarketRunRepository) -> None:
    await repository.create_run(_run())

    fetched = await repository.get_run("run-1")

    assert fetched is not None
    assert fetched.run_date == date(2026, 8, 29)
    assert fetched.status is IntelligenceRunStatus.RUNNING


async def test_get_run_missing_returns_none(repository: PostgresGlobalMarketRunRepository) -> None:
    assert await repository.get_run("does-not-exist") is None


async def test_create_run_persists_category_outcomes(
    repository: PostgresGlobalMarketRunRepository,
) -> None:
    outcome = CategoryRunOutcome(category=ReportCategory.INDIA_EQUITY, succeeded=True)
    run = _run(category_outcomes=(outcome,), status=IntelligenceRunStatus.PARTIAL)

    await repository.create_run(run)

    fetched = await repository.get_run("run-1")
    assert fetched is not None
    assert len(fetched.category_outcomes) == 1
    assert fetched.category_outcomes[0].category is ReportCategory.INDIA_EQUITY
    assert fetched.category_outcomes[0].succeeded is True


# --- Uniqueness: no duplicate report for the same run_date -----------------------------------------------------------


async def test_a_second_run_for_the_same_run_date_is_rejected(
    repository: PostgresGlobalMarketRunRepository,
) -> None:
    await repository.create_run(_run(run_id="run-1", run_date=date(2026, 8, 29)))

    with pytest.raises(DuplicateIntelligenceRunError):
        await repository.create_run(_run(run_id="run-2", run_date=date(2026, 8, 29)))


async def test_a_run_for_a_different_date_succeeds(repository: PostgresGlobalMarketRunRepository) -> None:
    await repository.create_run(_run(run_id="run-1", run_date=date(2026, 8, 29)))

    # No exception — a different run_date is not a duplicate.
    await repository.create_run(_run(run_id="run-2", run_date=date(2026, 8, 30)))

    assert len(await repository.list_runs()) == 2


# --- get_run_by_date -----------------------------------------------------------


async def test_get_run_by_date_returns_the_matching_run(
    repository: PostgresGlobalMarketRunRepository,
) -> None:
    await repository.create_run(_run(run_id="run-1", run_date=date(2026, 8, 29)))

    fetched = await repository.get_run_by_date(date(2026, 8, 29))

    assert fetched is not None
    assert fetched.id == "run-1"


async def test_get_run_by_date_returns_none_when_no_run_exists(
    repository: PostgresGlobalMarketRunRepository,
) -> None:
    assert await repository.get_run_by_date(date(2026, 1, 1)) is None


# --- update_run -----------------------------------------------------------


async def test_update_run_overwrites_status_and_outcomes(
    repository: PostgresGlobalMarketRunRepository,
) -> None:
    await repository.create_run(_run())
    outcome = CategoryRunOutcome(category=ReportCategory.US_EQUITY, succeeded=True)
    updated = _run(status=IntelligenceRunStatus.COMPLETED, category_outcomes=(outcome,), completed_at=NOW)

    result = await repository.update_run(updated)

    assert result is not None
    fetched = await repository.get_run("run-1")
    assert fetched is not None
    assert fetched.status is IntelligenceRunStatus.COMPLETED
    assert fetched.completed_at is not None
    assert len(fetched.category_outcomes) == 1


async def test_update_run_returns_none_for_a_missing_run(
    repository: PostgresGlobalMarketRunRepository,
) -> None:
    assert await repository.update_run(_run(run_id="does-not-exist")) is None


# --- list_runs -----------------------------------------------------------


async def test_list_runs_empty_initially(repository: PostgresGlobalMarketRunRepository) -> None:
    assert await repository.list_runs() == []


async def test_list_runs_orders_most_recent_run_date_first(
    repository: PostgresGlobalMarketRunRepository,
) -> None:
    await repository.create_run(_run(run_id="run-1", run_date=date(2026, 8, 27)))
    await repository.create_run(_run(run_id="run-2", run_date=date(2026, 8, 29)))

    runs = await repository.list_runs()

    assert [run.run_date for run in runs] == [date(2026, 8, 29), date(2026, 8, 27)]


# --- health_check -----------------------------------------------------------


async def test_health_check_true_against_reachable_database(
    repository: PostgresGlobalMarketRunRepository,
) -> None:
    assert await repository.health_check() is True


async def test_health_check_false_when_database_unreachable() -> None:
    broken_engine = create_async_engine("sqlite+aiosqlite:///nonexistent/no/such/path.db")
    session_factory = async_sessionmaker(broken_engine, expire_on_commit=False)

    repository = PostgresGlobalMarketRunRepository(session_factory)

    assert await repository.health_check() is False
