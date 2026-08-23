"""Translates between BacktestRequest/BacktestRun/BacktestResult and their
PostgreSQL ORM models. Purely structural mapping in both directions — no
business logic, aside from the same naive-datetime-from-SQLite
normalization `app.repositories.alerts.postgres.mapper` established
(Sprint 48) — see `_ensure_aware` there for the full rationale; repeated
here since these are independent modules with no shared base to place it in.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.backtesting.models import (
    BacktestPeriod,
    BacktestRequest,
    BacktestResult,
    BacktestRun,
    BacktestStatus,
    ReplayMode,
)
from app.repositories.backtesting.postgres.models import (
    BacktestRequestModel,
    BacktestResultModel,
    BacktestRunModel,
)

__all__ = [
    "request_to_model",
    "model_to_request",
    "run_to_model",
    "model_to_run",
    "result_to_model",
    "model_to_result",
]


def _ensure_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _ensure_aware_optional(value: datetime | None) -> datetime | None:
    return _ensure_aware(value) if value is not None else None


def request_to_model(request: BacktestRequest) -> BacktestRequestModel:
    """Map a `BacktestRequest` into a `BacktestRequestModel` ready to persist."""
    return BacktestRequestModel(
        id=request.id,
        name=request.name,
        description=request.description,
        start_date=request.start_date,
        end_date=request.end_date,
        initial_capital=request.initial_capital,
        benchmark=request.benchmark,
        strategy_ids=list(request.strategy_ids),
        replay_mode=request.replay_mode.value,
        created_at=request.created_at,
    )


def model_to_request(model: BacktestRequestModel) -> BacktestRequest:
    """Map a `BacktestRequestModel` row into a `BacktestRequest`."""
    return BacktestRequest(
        id=model.id,
        name=model.name,
        description=model.description,
        start_date=model.start_date,
        end_date=model.end_date,
        initial_capital=model.initial_capital,
        benchmark=model.benchmark,
        strategy_ids=tuple(model.strategy_ids),
        replay_mode=ReplayMode(model.replay_mode),
        created_at=_ensure_aware(model.created_at),
    )


def run_to_model(run: BacktestRun) -> BacktestRunModel:
    """Map a `BacktestRun` into a `BacktestRunModel` ready to persist."""
    return BacktestRunModel(
        request_id=run.request_id,
        started_at=run.started_at,
        completed_at=run.completed_at,
        status=run.status.value,
        processed_snapshots=run.processed_snapshots,
        results=[period.model_dump(mode="json") for period in run.results],
    )


def model_to_run(model: BacktestRunModel) -> BacktestRun:
    """Map a `BacktestRunModel` row into a `BacktestRun`."""
    return BacktestRun(
        request_id=model.request_id,
        started_at=_ensure_aware(model.started_at),
        completed_at=_ensure_aware_optional(model.completed_at),
        status=BacktestStatus(model.status),
        processed_snapshots=model.processed_snapshots,
        results=tuple(BacktestPeriod.model_validate(period) for period in model.results),
    )


def result_to_model(result: BacktestResult) -> BacktestResultModel:
    """Map a `BacktestResult` into a `BacktestResultModel` ready to persist."""
    return BacktestResultModel(
        request_id=result.request_id,
        portfolio_return=result.portfolio_return,
        benchmark_return=result.benchmark_return,
        excess_return=result.excess_return,
        max_drawdown=result.max_drawdown,
        win_rate=result.win_rate,
        total_periods=result.total_periods,
        successful_periods=result.successful_periods,
        failed_periods=result.failed_periods,
        summary=result.summary,
        generated_at=result.generated_at,
    )


def model_to_result(model: BacktestResultModel) -> BacktestResult:
    """Map a `BacktestResultModel` row into a `BacktestResult`."""
    return BacktestResult(
        request_id=model.request_id,
        portfolio_return=model.portfolio_return,
        benchmark_return=model.benchmark_return,
        excess_return=model.excess_return,
        max_drawdown=model.max_drawdown,
        win_rate=model.win_rate,
        total_periods=model.total_periods,
        successful_periods=model.successful_periods,
        failed_periods=model.failed_periods,
        summary=model.summary,
        generated_at=_ensure_aware(model.generated_at),
    )
