"""Tests for the Backtesting Postgres mapper: purely structural
round-trips, plus the naive-datetime normalization `_ensure_aware`
performs (mirrors the Alert/Recommendation/Strategy/Risk Postgres
mappers' own regression tests)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.backtesting.models import (
    BacktestPeriod,
    BacktestRequest,
    BacktestResult,
    BacktestRun,
    BacktestStatus,
    ReplayMode,
)
from app.repositories.backtesting.postgres.mapper import (
    model_to_request,
    model_to_result,
    model_to_run,
    request_to_model,
    result_to_model,
    run_to_model,
)
from app.repositories.backtesting.postgres.models import (
    BacktestRequestModel,
    BacktestResultModel,
    BacktestRunModel,
)

NOW = datetime(2026, 8, 7, tzinfo=UTC)


def test_request_round_trips() -> None:
    request = BacktestRequest(
        id="r1", name="Value", description="desc", start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
        initial_capital=100000.0, benchmark="SPY", strategy_ids=("s1", "s2"), replay_mode=ReplayMode.WEEKLY,
        created_at=NOW,
    )

    model = request_to_model(request)
    restored = model_to_request(model)

    assert restored == request


def test_request_with_no_strategy_ids_round_trips() -> None:
    request = BacktestRequest(
        id="r1", name="Value", start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
        initial_capital=1000.0, benchmark="SPY", created_at=NOW,
    )

    model = request_to_model(request)
    restored = model_to_request(model)

    assert restored.strategy_ids == ()


def test_run_with_periods_round_trips() -> None:
    period = BacktestPeriod(
        timestamp=NOW, portfolio_value=105000.0, benchmark_value=102.0, return_percent=5.0, notes="x"
    )
    run = BacktestRun(
        request_id="r1", started_at=NOW, completed_at=NOW, status=BacktestStatus.COMPLETED,
        processed_snapshots=1, results=(period,),
    )

    model = run_to_model(run)
    restored = model_to_run(model)

    assert restored == run


def test_run_with_no_completed_at_round_trips() -> None:
    run = BacktestRun(request_id="r1", started_at=NOW, status=BacktestStatus.RUNNING)

    model = run_to_model(run)
    restored = model_to_run(model)

    assert restored.completed_at is None
    assert restored.results == ()


def test_result_round_trips() -> None:
    result = BacktestResult(
        request_id="r1", portfolio_return=5.0, benchmark_return=3.0, excess_return=2.0, max_drawdown=1.5,
        win_rate=60.0, total_periods=10, successful_periods=6, failed_periods=4, summary="x", generated_at=NOW,
    )

    model = result_to_model(result)
    restored = model_to_result(model)

    assert restored == result


def test_model_to_request_normalizes_naive_datetime_to_utc() -> None:
    model = BacktestRequestModel(
        id="r1", name="X", description="", start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
        initial_capital=1000.0, benchmark="SPY", strategy_ids=[], replay_mode="DAILY",
        created_at=datetime(2026, 1, 1),  # naive, as SQLite round-trips it
    )

    restored = model_to_request(model)

    assert restored.created_at.tzinfo is not None


def test_model_to_run_normalizes_naive_datetimes_to_utc() -> None:
    model = BacktestRunModel(
        request_id="r1", started_at=datetime(2026, 1, 1), completed_at=datetime(2026, 1, 1),
        status="COMPLETED", processed_snapshots=0, results=[],
    )

    restored = model_to_run(model)

    assert restored.started_at.tzinfo is not None
    assert restored.completed_at is not None
    assert restored.completed_at.tzinfo is not None


def test_model_to_run_handles_none_completed_at() -> None:
    model = BacktestRunModel(
        request_id="r1", started_at=datetime(2026, 1, 1), completed_at=None,
        status="RUNNING", processed_snapshots=0, results=[],
    )

    restored = model_to_run(model)

    assert restored.completed_at is None


def test_model_to_result_normalizes_naive_datetime_to_utc() -> None:
    model = BacktestResultModel(
        request_id="r1", portfolio_return=0.0, benchmark_return=0.0, excess_return=0.0, max_drawdown=0.0,
        win_rate=0.0, total_periods=0, successful_periods=0, failed_periods=0, summary="x",
        generated_at=datetime(2026, 1, 1),  # naive
    )

    restored = model_to_result(model)

    assert restored.generated_at.tzinfo is not None
