"""Tests for BacktestingService's request/run/result management: create,
get, list, duplicate-name prevention, and not-found errors."""

from __future__ import annotations

from datetime import date

import pytest

from app.backtesting.engine import BacktestingService
from app.backtesting.exceptions import (
    BacktestRequestNotFoundError,
    BacktestResultNotFoundError,
    BacktestRunNotFoundError,
    DuplicateBacktestRequestNameError,
)
from app.backtesting.models import ReplayMode

# --- create_request -----------------------------------------------------------


async def test_create_request_returns_a_request_with_a_generated_id(service: BacktestingService) -> None:
    request = await service.create_request("Q3 Backtest", date(2026, 1, 1), date(2026, 1, 31), 100000.0, "SPY")
    assert request.id
    assert request.name == "Q3 Backtest"
    assert request.initial_capital == 100000.0
    assert request.benchmark == "SPY"


async def test_create_request_accepts_configurable_replay_mode_and_strategy_ids(
    service: BacktestingService,
) -> None:
    request = await service.create_request(
        "Weekly",
        date(2026, 1, 1),
        date(2026, 1, 31),
        100000.0,
        "SPY",
        strategy_ids=("s1", "s2"),
        replay_mode=ReplayMode.WEEKLY,
    )
    assert request.replay_mode == ReplayMode.WEEKLY
    assert request.strategy_ids == ("s1", "s2")


async def test_create_request_duplicate_name_raises(service: BacktestingService) -> None:
    await service.create_request("Q3 Backtest", date(2026, 1, 1), date(2026, 1, 31), 100000.0, "SPY")

    with pytest.raises(DuplicateBacktestRequestNameError):
        await service.create_request("Q3 Backtest", date(2026, 2, 1), date(2026, 2, 28), 50000.0, "QQQ")


async def test_create_request_duplicate_name_allowed_when_not_enforced(
    backtesting_repository, recommendation_service, strategy_service, risk_service
) -> None:
    lenient_service = BacktestingService(
        backtesting_repository, recommendation_service, strategy_service, risk_service, enforce_unique_names=False
    )
    await lenient_service.create_request("Dup", date(2026, 1, 1), date(2026, 1, 31), 100000.0, "SPY")

    second = await lenient_service.create_request("Dup", date(2026, 2, 1), date(2026, 2, 28), 50000.0, "QQQ")

    assert second.name == "Dup"


# --- get_request / list_requests -----------------------------------------------------------


async def test_get_request_unknown_id_raises(service: BacktestingService) -> None:
    with pytest.raises(BacktestRequestNotFoundError):
        await service.get_request("does-not-exist")


async def test_get_request_returns_created_request(service: BacktestingService) -> None:
    created = await service.create_request("Q3 Backtest", date(2026, 1, 1), date(2026, 1, 31), 100000.0, "SPY")

    fetched = await service.get_request(created.id)

    assert fetched == created


async def test_list_requests_empty_initially(service: BacktestingService) -> None:
    assert await service.list_requests() == []


async def test_list_requests_returns_every_created_request(service: BacktestingService) -> None:
    await service.create_request("A", date(2026, 1, 1), date(2026, 1, 31), 1000.0, "SPY")
    await service.create_request("B", date(2026, 1, 1), date(2026, 1, 31), 1000.0, "SPY")

    names = {r.name for r in await service.list_requests()}

    assert names == {"A", "B"}


# --- get_run / list_runs -----------------------------------------------------------


async def test_get_run_unknown_request_id_raises(service: BacktestingService) -> None:
    with pytest.raises(BacktestRunNotFoundError):
        await service.get_run("does-not-exist")


async def test_list_runs_empty_initially(service: BacktestingService) -> None:
    assert await service.list_runs() == []


# --- get_result -----------------------------------------------------------


async def test_get_result_unknown_request_id_raises(service: BacktestingService) -> None:
    with pytest.raises(BacktestResultNotFoundError):
        await service.get_result("does-not-exist")
