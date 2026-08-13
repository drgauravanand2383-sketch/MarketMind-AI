"""Tests for PostgresBacktestingRepository.

Run against an in-memory SQLite database via aiosqlite, exercising the
repository's own CRUD/health-check behavior directly (not through
BacktestingService) — no business rules (duplicate-name prevention,
replay execution) are enforced at this layer.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.backtesting.models import (
    BacktestPeriod,
    BacktestRequest,
    BacktestResult,
    BacktestRun,
    BacktestStatus,
    ReplayMode,
)
from app.repositories.backtesting.postgres.models import Base
from app.repositories.backtesting.postgres.repository import PostgresBacktestingRepository

NOW = datetime(2026, 8, 7, tzinfo=timezone.utc)


@pytest.fixture
async def repository() -> AsyncIterator[PostgresBacktestingRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PostgresBacktestingRepository(session_factory)
    finally:
        await engine.dispose()


def _request(request_id: str = "r1", name: str = "Value", **overrides: object) -> BacktestRequest:
    defaults: dict[str, object] = {
        "id": request_id, "name": name, "start_date": date(2026, 1, 1), "end_date": date(2026, 1, 31),
        "initial_capital": 100000.0, "benchmark": "SPY", "created_at": NOW,
    }
    defaults.update(overrides)
    return BacktestRequest(**defaults)


def _run(request_id: str = "r1", started_at: datetime = NOW, **overrides: object) -> BacktestRun:
    defaults: dict[str, object] = {
        "request_id": request_id, "started_at": started_at, "status": BacktestStatus.COMPLETED,
    }
    defaults.update(overrides)
    return BacktestRun(**defaults)


def _result(request_id: str = "r1", generated_at: datetime = NOW, **overrides: object) -> BacktestResult:
    defaults: dict[str, object] = {
        "request_id": request_id, "generated_at": generated_at, "portfolio_return": 0.0, "benchmark_return": 0.0,
        "excess_return": 0.0, "max_drawdown": 0.0, "win_rate": 0.0, "total_periods": 0, "successful_periods": 0,
        "failed_periods": 0, "summary": "x",
    }
    defaults.update(overrides)
    return BacktestResult(**defaults)


# --- create_request / get_request -----------------------------------------------------------


async def test_create_request_then_get_returns_it(repository: PostgresBacktestingRepository) -> None:
    await repository.create_request(_request())

    fetched = await repository.get_request("r1")

    assert fetched is not None
    assert fetched.name == "Value"


async def test_get_request_missing_returns_none(repository: PostgresBacktestingRepository) -> None:
    assert await repository.get_request("does-not-exist") is None


async def test_create_request_persists_all_fields(repository: PostgresBacktestingRepository) -> None:
    request = _request(strategy_ids=("s1", "s2"), replay_mode=ReplayMode.MONTHLY)

    await repository.create_request(request)

    fetched = await repository.get_request("r1")
    assert fetched is not None
    assert fetched.strategy_ids == ("s1", "s2")
    assert fetched.replay_mode == ReplayMode.MONTHLY


# --- list_requests -----------------------------------------------------------


async def test_list_requests_empty_initially(repository: PostgresBacktestingRepository) -> None:
    assert await repository.list_requests() == []


async def test_list_requests_returns_all(repository: PostgresBacktestingRepository) -> None:
    await repository.create_request(_request("r1", "A"))
    await repository.create_request(_request("r2", "B"))

    requests = await repository.list_requests()

    assert {r.name for r in requests} == {"A", "B"}


# --- store_run / get_run -----------------------------------------------------------


async def test_store_run_then_get_returns_it(repository: PostgresBacktestingRepository) -> None:
    await repository.store_run(_run())

    fetched = await repository.get_run("r1")

    assert fetched is not None
    assert fetched.request_id == "r1"


async def test_get_run_missing_returns_none(repository: PostgresBacktestingRepository) -> None:
    assert await repository.get_run("does-not-exist") is None


async def test_get_run_returns_most_recent_when_multiple_stored(
    repository: PostgresBacktestingRepository,
) -> None:
    await repository.store_run(_run(started_at=NOW, status=BacktestStatus.FAILED))
    await repository.store_run(_run(started_at=NOW + timedelta(minutes=5), status=BacktestStatus.COMPLETED))

    latest = await repository.get_run("r1")

    assert latest is not None
    assert latest.status == BacktestStatus.COMPLETED


async def test_store_run_persists_periods(repository: PostgresBacktestingRepository) -> None:
    period = BacktestPeriod(timestamp=NOW, portfolio_value=105000.0, return_percent=5.0)
    run = _run(processed_snapshots=1, results=(period,))

    await repository.store_run(run)

    fetched = await repository.get_run("r1")
    assert fetched is not None
    assert fetched.results[0].portfolio_value == 105000.0


# --- list_runs -----------------------------------------------------------


async def test_list_runs_empty_initially(repository: PostgresBacktestingRepository) -> None:
    assert await repository.list_runs() == []


async def test_list_runs_returns_all_across_requests(repository: PostgresBacktestingRepository) -> None:
    await repository.store_run(_run("r1"))
    await repository.store_run(_run("r2"))

    runs = await repository.list_runs()

    assert {r.request_id for r in runs} == {"r1", "r2"}


# --- store_result / get_result -----------------------------------------------------------


async def test_store_result_then_get_returns_it(repository: PostgresBacktestingRepository) -> None:
    await repository.store_result(_result())

    fetched = await repository.get_result("r1")

    assert fetched is not None
    assert fetched.request_id == "r1"


async def test_get_result_missing_returns_none(repository: PostgresBacktestingRepository) -> None:
    assert await repository.get_result("does-not-exist") is None


async def test_get_result_returns_most_recent_when_multiple_stored(
    repository: PostgresBacktestingRepository,
) -> None:
    await repository.store_result(_result(generated_at=NOW, portfolio_return=1.0))
    await repository.store_result(_result(generated_at=NOW + timedelta(minutes=5), portfolio_return=99.0))

    latest = await repository.get_result("r1")

    assert latest is not None
    assert latest.portfolio_return == 99.0


# --- health_check -----------------------------------------------------------


async def test_health_check_true_against_reachable_database(repository: PostgresBacktestingRepository) -> None:
    assert await repository.health_check() is True


async def test_health_check_false_when_database_unreachable() -> None:
    broken_engine = create_async_engine("sqlite+aiosqlite:///nonexistent/no/such/path.db")
    session_factory = async_sessionmaker(broken_engine, expire_on_commit=False)

    repository = PostgresBacktestingRepository(session_factory)

    assert await repository.health_check() is False
