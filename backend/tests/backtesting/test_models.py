"""Tests for Backtesting Framework domain models: validation rules,
tz-aware normalization, and structural defaults."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from app.backtesting.models import (
    BacktestPeriod,
    BacktestRequest,
    BacktestResult,
    BacktestRun,
    BacktestStatus,
    HistoricalSnapshot,
    ReplayMode,
)

NOW = datetime(2026, 8, 7, tzinfo=UTC)


def _request(**overrides: object) -> BacktestRequest:
    defaults: dict[str, object] = {
        "id": "r1",
        "name": "My Backtest",
        "start_date": date(2026, 1, 1),
        "end_date": date(2026, 1, 31),
        "initial_capital": 100000.0,
        "benchmark": "SPY",
        "created_at": NOW,
    }
    defaults.update(overrides)
    return BacktestRequest(**defaults)


# --- ReplayMode / BacktestStatus -----------------------------------------------------------


def test_replay_mode_supports_all_four_modes() -> None:
    assert {mode.value for mode in ReplayMode} == {"DAILY", "WEEKLY", "MONTHLY", "CUSTOM"}


def test_backtest_status_supports_full_lifecycle() -> None:
    assert {status.value for status in BacktestStatus} == {"PENDING", "RUNNING", "COMPLETED", "FAILED"}


# --- BacktestRequest -----------------------------------------------------------


def test_request_accepts_valid_fields() -> None:
    request = _request()
    assert request.name == "My Backtest"
    assert request.replay_mode == ReplayMode.DAILY
    assert request.strategy_ids == ()


def test_request_rejects_start_date_after_end_date() -> None:
    with pytest.raises(ValidationError):
        _request(start_date=date(2026, 2, 1), end_date=date(2026, 1, 1))


def test_request_allows_equal_start_and_end_date() -> None:
    request = _request(start_date=date(2026, 1, 1), end_date=date(2026, 1, 1))
    assert request.start_date == request.end_date


def test_request_rejects_non_positive_initial_capital() -> None:
    with pytest.raises(ValidationError):
        _request(initial_capital=0.0)
    with pytest.raises(ValidationError):
        _request(initial_capital=-100.0)


def test_request_rejects_blank_name() -> None:
    with pytest.raises(ValidationError):
        _request(name="")


def test_request_rejects_blank_benchmark() -> None:
    with pytest.raises(ValidationError):
        _request(benchmark="")


def test_request_rejects_blank_id() -> None:
    with pytest.raises(ValidationError):
        _request(id="")


def test_request_is_frozen() -> None:
    request = _request()
    with pytest.raises(ValidationError):
        request.name = "New Name"  # type: ignore[misc]


def test_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        _request(unexpected_field="x")


def test_request_accepts_configured_strategy_ids_and_replay_mode() -> None:
    request = _request(strategy_ids=("s1", "s2"), replay_mode=ReplayMode.WEEKLY)
    assert request.strategy_ids == ("s1", "s2")
    assert request.replay_mode == ReplayMode.WEEKLY


# --- HistoricalSnapshot -----------------------------------------------------------


def test_snapshot_accepts_minimal_fields() -> None:
    snapshot = HistoricalSnapshot(timestamp=NOW, recommendation_result_id="rec-1")
    assert snapshot.strategy_evaluation_id is None
    assert snapshot.risk_assessment_id is None
    assert snapshot.benchmark_value is None


def test_snapshot_rejects_blank_recommendation_result_id() -> None:
    with pytest.raises(ValidationError):
        HistoricalSnapshot(timestamp=NOW, recommendation_result_id="")


def test_snapshot_normalizes_naive_timestamp_to_utc() -> None:
    snapshot = HistoricalSnapshot(timestamp=datetime(2026, 1, 1), recommendation_result_id="rec-1")
    assert snapshot.timestamp.tzinfo is not None


def test_snapshot_preserves_already_aware_timestamp() -> None:
    aware = datetime(2026, 1, 1, tzinfo=UTC)
    snapshot = HistoricalSnapshot(timestamp=aware, recommendation_result_id="rec-1")
    assert snapshot.timestamp == aware


def test_snapshot_accepts_all_optional_fields() -> None:
    snapshot = HistoricalSnapshot(
        timestamp=NOW,
        recommendation_result_id="rec-1",
        strategy_evaluation_id="strat-1",
        risk_assessment_id="risk-1",
        benchmark_value=450.23,
    )
    assert snapshot.strategy_evaluation_id == "strat-1"
    assert snapshot.risk_assessment_id == "risk-1"
    assert snapshot.benchmark_value == 450.23


# --- BacktestPeriod -----------------------------------------------------------


def test_period_accepts_valid_fields() -> None:
    period = BacktestPeriod(timestamp=NOW, portfolio_value=105000.0, return_percent=5.0)
    assert period.benchmark_value is None
    assert period.notes == ""


# --- BacktestRun -----------------------------------------------------------


def test_run_defaults_to_zero_processed_snapshots_and_empty_results() -> None:
    run = BacktestRun(request_id="r1", started_at=NOW, status=BacktestStatus.RUNNING)
    assert run.processed_snapshots == 0
    assert run.results == ()
    assert run.completed_at is None


def test_run_rejects_negative_processed_snapshots() -> None:
    with pytest.raises(ValidationError):
        BacktestRun(request_id="r1", started_at=NOW, status=BacktestStatus.RUNNING, processed_snapshots=-1)


def test_run_accepts_completed_status_with_results() -> None:
    period = BacktestPeriod(timestamp=NOW, portfolio_value=100.0, return_percent=0.0)
    run = BacktestRun(
        request_id="r1", started_at=NOW, completed_at=NOW, status=BacktestStatus.COMPLETED,
        processed_snapshots=1, results=(period,),
    )
    assert run.results == (period,)


# --- BacktestResult -----------------------------------------------------------


def _result(**overrides: object) -> BacktestResult:
    defaults: dict[str, object] = {
        "request_id": "r1",
        "portfolio_return": 5.0,
        "benchmark_return": 3.0,
        "excess_return": 2.0,
        "max_drawdown": 1.5,
        "win_rate": 60.0,
        "total_periods": 10,
        "successful_periods": 6,
        "failed_periods": 4,
        "summary": "x",
        "generated_at": NOW,
    }
    defaults.update(overrides)
    return BacktestResult(**defaults)


def test_result_accepts_valid_fields() -> None:
    result = _result()
    assert result.total_periods == 10


def test_result_rejects_win_rate_outside_zero_to_hundred() -> None:
    with pytest.raises(ValidationError):
        _result(win_rate=101.0)
    with pytest.raises(ValidationError):
        _result(win_rate=-1.0)


def test_result_rejects_negative_max_drawdown() -> None:
    with pytest.raises(ValidationError):
        _result(max_drawdown=-1.0)


def test_result_rejects_negative_period_counts() -> None:
    with pytest.raises(ValidationError):
        _result(total_periods=-1)
    with pytest.raises(ValidationError):
        _result(successful_periods=-1)
    with pytest.raises(ValidationError):
        _result(failed_periods=-1)


def test_result_allows_negative_return_metrics() -> None:
    """Returns/drawdown-adjacent metrics like portfolio_return, benchmark_return,
    and excess_return can legitimately be negative (a losing backtest)."""
    result = _result(portfolio_return=-10.0, benchmark_return=-5.0, excess_return=-5.0)
    assert result.portfolio_return == -10.0
