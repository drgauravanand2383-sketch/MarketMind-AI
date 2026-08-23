"""Integration tests for BacktestingService.run_backtest: full replay
orchestration against real (in-memory) injected Recommendation/Strategy/
Risk services, metric calculations, persistence, validation, determinism,
and edge cases."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.backtesting.engine import BacktestingService
from app.backtesting.exceptions import InvalidSnapshotReferenceError, MaxReplayPeriodsExceededError
from app.backtesting.models import BacktestStatus, HistoricalSnapshot, ReplayMode
from tests.backtesting.conftest import (
    NOW,
    make_candidate,
    make_recommendation_result,
    make_risk_assessment,
    make_strategy_evaluation_result,
    make_strategy_match,
)


async def _request(service: BacktestingService, **overrides: object):
    defaults: dict[str, object] = {
        "name": "Backtest",
        "start_date": date(2026, 1, 1),
        "end_date": date(2026, 1, 31),
        "initial_capital": 100000.0,
        "benchmark": "SPY",
    }
    defaults.update(overrides)
    return await service.create_request(**defaults)  # type: ignore[arg-type]


def _snapshot(timestamp: datetime, rec_id: str, **overrides: object) -> HistoricalSnapshot:
    return HistoricalSnapshot(timestamp=timestamp, recommendation_result_id=rec_id, **overrides)


# --- Basic orchestration -----------------------------------------------------------


async def test_run_backtest_returns_and_persists_result(
    service: BacktestingService, recommendation_repository
) -> None:
    await recommendation_repository.store_result(
        make_recommendation_result("rec-1", (make_candidate("A", 70.0),))
    )
    request = await _request(service)
    snapshots = [_snapshot(NOW, "rec-1")]

    result = await service.run_backtest(request, snapshots)

    assert result.request_id == request.id
    fetched = await service.get_result(request.id)
    assert fetched == result


async def test_run_backtest_persists_a_completed_run_with_periods(
    service: BacktestingService, recommendation_repository
) -> None:
    await recommendation_repository.store_result(
        make_recommendation_result("rec-1", (make_candidate("A", 70.0),))
    )
    request = await _request(service)
    snapshots = [_snapshot(NOW, "rec-1")]

    await service.run_backtest(request, snapshots)

    run = await service.get_run(request.id)
    assert run.status == BacktestStatus.COMPLETED
    assert run.processed_snapshots == 1
    assert len(run.results) == 1


# --- Metric calculations -----------------------------------------------------------


async def test_portfolio_return_reflects_score_improvement_across_periods(
    service: BacktestingService, recommendation_repository
) -> None:
    await recommendation_repository.store_result(make_recommendation_result("rec-low", (make_candidate("A", 20.0),)))
    await recommendation_repository.store_result(make_recommendation_result("rec-high", (make_candidate("A", 80.0),)))
    request = await _request(service)
    snapshots = [
        _snapshot(NOW - timedelta(days=1), "rec-low"),
        _snapshot(NOW, "rec-high"),
    ]

    result = await service.run_backtest(request, snapshots)

    assert result.portfolio_return > 0
    assert result.successful_periods == 1
    assert result.failed_periods == 1
    assert result.win_rate == 50.0


async def test_portfolio_return_reflects_score_decline_across_periods(
    service: BacktestingService, recommendation_repository
) -> None:
    await recommendation_repository.store_result(make_recommendation_result("rec-high", (make_candidate("A", 80.0),)))
    await recommendation_repository.store_result(make_recommendation_result("rec-low", (make_candidate("A", 20.0),)))
    request = await _request(service)
    snapshots = [
        _snapshot(NOW - timedelta(days=1), "rec-high"),
        _snapshot(NOW, "rec-low"),
    ]

    result = await service.run_backtest(request, snapshots)

    assert result.portfolio_return < 0


async def test_benchmark_return_computed_from_supplied_benchmark_values(
    service: BacktestingService, recommendation_repository
) -> None:
    await recommendation_repository.store_result(make_recommendation_result("rec-1", (make_candidate("A", 50.0),)))
    request = await _request(service)
    snapshots = [
        _snapshot(NOW - timedelta(days=1), "rec-1", benchmark_value=100.0),
        _snapshot(NOW, "rec-1", benchmark_value=110.0),
    ]

    result = await service.run_backtest(request, snapshots)

    assert result.benchmark_return == 10.0


async def test_benchmark_return_defaults_to_zero_without_benchmark_data(
    service: BacktestingService, recommendation_repository
) -> None:
    await recommendation_repository.store_result(make_recommendation_result("rec-1", (make_candidate("A", 50.0),)))
    request = await _request(service)
    snapshots = [_snapshot(NOW - timedelta(days=1), "rec-1"), _snapshot(NOW, "rec-1")]

    result = await service.run_backtest(request, snapshots)

    assert result.benchmark_return == 0.0


async def test_excess_return_is_portfolio_return_minus_benchmark_return(
    service: BacktestingService, recommendation_repository
) -> None:
    await recommendation_repository.store_result(make_recommendation_result("rec-low", (make_candidate("A", 20.0),)))
    await recommendation_repository.store_result(make_recommendation_result("rec-high", (make_candidate("A", 80.0),)))
    request = await _request(service)
    snapshots = [
        _snapshot(NOW - timedelta(days=1), "rec-low", benchmark_value=100.0),
        _snapshot(NOW, "rec-high", benchmark_value=105.0),
    ]

    result = await service.run_backtest(request, snapshots)

    assert result.excess_return == round(result.portfolio_return - result.benchmark_return, 4)


async def test_max_drawdown_detects_peak_to_trough_decline(
    service: BacktestingService, recommendation_repository
) -> None:
    await recommendation_repository.store_result(make_recommendation_result("rec-mid", (make_candidate("A", 50.0),)))
    await recommendation_repository.store_result(make_recommendation_result("rec-peak", (make_candidate("A", 100.0),)))
    await recommendation_repository.store_result(make_recommendation_result("rec-trough", (make_candidate("A", 10.0),)))
    request = await _request(service)
    snapshots = [
        _snapshot(NOW - timedelta(days=2), "rec-mid"),
        _snapshot(NOW - timedelta(days=1), "rec-peak"),
        _snapshot(NOW, "rec-trough"),
    ]

    result = await service.run_backtest(request, snapshots)

    assert result.max_drawdown > 0
    # peak value = initial_capital * 1.0, trough value = initial_capital * 0.10 -> 90% drawdown
    assert result.max_drawdown == pytest.approx(90.0, abs=0.01)


async def test_single_period_has_zero_return_and_zero_drawdown(
    service: BacktestingService, recommendation_repository
) -> None:
    await recommendation_repository.store_result(make_recommendation_result("rec-1", (make_candidate("A", 70.0),)))
    request = await _request(service)

    result = await service.run_backtest(request, [_snapshot(NOW, "rec-1")])

    assert result.portfolio_return == 0.0
    assert result.max_drawdown == 0.0
    assert result.total_periods == 1
    assert result.successful_periods == 0  # first period's return is exactly 0.0, not > 0
    assert result.win_rate == 0.0


async def test_empty_snapshots_produces_degenerate_zero_result(service: BacktestingService) -> None:
    request = await _request(service)

    result = await service.run_backtest(request, [])

    assert result.total_periods == 0
    assert result.portfolio_return == 0.0
    assert result.win_rate == 0.0
    run = await service.get_run(request.id)
    assert run.status == BacktestStatus.COMPLETED
    assert run.processed_snapshots == 0


# --- Strategy / Risk component contribution -----------------------------------------------------------


async def test_strategy_component_uses_overall_alignment_when_no_strategy_ids_configured(
    service: BacktestingService, recommendation_repository, strategy_repository
) -> None:
    await recommendation_repository.store_result(make_recommendation_result("rec-1", (make_candidate("A", 0.0),)))
    await strategy_repository.store_evaluation(
        make_strategy_evaluation_result("strat-eval-1", overall_alignment=100.0)
    )
    request = await _request(service, strategy_ids=())
    snapshot = _snapshot(NOW, "rec-1", strategy_evaluation_id="strat-eval-1")

    await service.run_backtest(request, [snapshot])

    run = await service.get_run(request.id)
    # blended average of recommendation_component(0) and strategy_component(100) = 50
    assert run.results[0].portfolio_value == pytest.approx(100000.0 * 0.5, abs=0.01)


async def test_strategy_component_filters_to_configured_strategy_ids(
    service: BacktestingService, recommendation_repository, strategy_repository
) -> None:
    await recommendation_repository.store_result(make_recommendation_result("rec-1", ()))
    await strategy_repository.store_evaluation(
        make_strategy_evaluation_result(
            "strat-eval-1",
            matches=(make_strategy_match("s1", 100.0), make_strategy_match("s2", 0.0)),
            overall_alignment=50.0,
        )
    )
    request = await _request(service, strategy_ids=("s1",))
    snapshot = _snapshot(NOW, "rec-1", strategy_evaluation_id="strat-eval-1")

    await service.run_backtest(request, [snapshot])

    run = await service.get_run(request.id)
    # recommendation_component is None (no candidates); only strategy_component(s1=100) is available
    assert run.results[0].portfolio_value == pytest.approx(100000.0 * 1.0, abs=0.01)


async def test_risk_component_is_inverted_overall_risk_score(
    service: BacktestingService, recommendation_repository, risk_repository
) -> None:
    await recommendation_repository.store_result(make_recommendation_result("rec-1", ()))
    await risk_repository.store_assessment(make_risk_assessment("risk-1", overall_risk_score=30.0))
    request = await _request(service)
    snapshot = _snapshot(NOW, "rec-1", risk_assessment_id="risk-1")

    await service.run_backtest(request, [snapshot])

    run = await service.get_run(request.id)
    # recommendation_component is None; only risk_component (100 - 30 = 70) is available
    assert run.results[0].portfolio_value == pytest.approx(100000.0 * 0.70, abs=0.01)


async def test_snapshot_without_strategy_or_risk_ids_uses_recommendation_only(
    service: BacktestingService, recommendation_repository
) -> None:
    await recommendation_repository.store_result(make_recommendation_result("rec-1", (make_candidate("A", 40.0),)))
    request = await _request(service)

    await service.run_backtest(request, [_snapshot(NOW, "rec-1")])

    run = await service.get_run(request.id)
    assert run.results[0].portfolio_value == pytest.approx(100000.0 * 0.40, abs=0.01)


async def test_period_with_no_candidates_and_no_other_data_carries_forward_previous_score(
    service: BacktestingService, recommendation_repository
) -> None:
    await recommendation_repository.store_result(make_recommendation_result("rec-1", (make_candidate("A", 60.0),)))
    await recommendation_repository.store_result(make_recommendation_result("rec-empty", ()))
    request = await _request(service)
    snapshots = [_snapshot(NOW - timedelta(days=1), "rec-1"), _snapshot(NOW, "rec-empty")]

    result = await service.run_backtest(request, snapshots)

    run = await service.get_run(request.id)
    # second period has no components at all -> carries forward first period's value (0% change)
    assert run.results[1].portfolio_value == run.results[0].portfolio_value
    assert result.portfolio_return == 0.0


# --- Validation -----------------------------------------------------------


async def test_max_replay_periods_exceeded_raises(
    backtesting_repository, recommendation_service, strategy_service, risk_service, recommendation_repository
) -> None:
    tiny_service = BacktestingService(
        backtesting_repository, recommendation_service, strategy_service, risk_service, max_periods=1
    )
    await recommendation_repository.store_result(make_recommendation_result("rec-1", (make_candidate("A"),)))
    request = await _request(tiny_service)
    snapshots = [_snapshot(NOW - timedelta(days=1), "rec-1"), _snapshot(NOW, "rec-1")]

    with pytest.raises(MaxReplayPeriodsExceededError):
        await tiny_service.run_backtest(request, snapshots)


async def test_invalid_recommendation_reference_raises_and_persists_failed_run(
    service: BacktestingService,
) -> None:
    request = await _request(service)
    snapshots = [_snapshot(NOW, "does-not-exist")]

    with pytest.raises(InvalidSnapshotReferenceError):
        await service.run_backtest(request, snapshots)

    run = await service.get_run(request.id)
    assert run.status == BacktestStatus.FAILED
    assert run.processed_snapshots == 0


async def test_invalid_strategy_reference_raises(
    service: BacktestingService, recommendation_repository
) -> None:
    await recommendation_repository.store_result(make_recommendation_result("rec-1", (make_candidate("A"),)))
    request = await _request(service)
    snapshot = _snapshot(NOW, "rec-1", strategy_evaluation_id="does-not-exist")

    with pytest.raises(InvalidSnapshotReferenceError):
        await service.run_backtest(request, [snapshot])


async def test_invalid_risk_reference_raises(service: BacktestingService, recommendation_repository) -> None:
    await recommendation_repository.store_result(make_recommendation_result("rec-1", (make_candidate("A"),)))
    request = await _request(service)
    snapshot = _snapshot(NOW, "rec-1", risk_assessment_id="does-not-exist")

    with pytest.raises(InvalidSnapshotReferenceError):
        await service.run_backtest(request, [snapshot])


# --- Determinism -----------------------------------------------------------


async def test_repeated_identical_runs_produce_identical_outputs(
    backtesting_repository, recommendation_service, strategy_service, risk_service, recommendation_repository
) -> None:
    clock = {"t": NOW}
    clocked_service = BacktestingService(
        backtesting_repository, recommendation_service, strategy_service, risk_service, now_fn=lambda: clock["t"]
    )
    await recommendation_repository.store_result(make_recommendation_result("rec-low", (make_candidate("A", 30.0),)))
    await recommendation_repository.store_result(make_recommendation_result("rec-high", (make_candidate("A", 90.0),)))
    request = await _request(clocked_service, name="Deterministic")
    snapshots = [
        _snapshot(NOW - timedelta(days=1), "rec-low", benchmark_value=100.0),
        _snapshot(NOW, "rec-high", benchmark_value=95.0),
    ]

    first = await clocked_service.run_backtest(request, snapshots)
    clock["t"] = NOW + timedelta(hours=1)
    second = await clocked_service.run_backtest(request, snapshots)

    assert first.portfolio_return == second.portfolio_return
    assert first.benchmark_return == second.benchmark_return
    assert first.excess_return == second.excess_return
    assert first.max_drawdown == second.max_drawdown
    assert first.win_rate == second.win_rate
    assert first.total_periods == second.total_periods


async def test_ordering_is_deterministic_regardless_of_snapshot_input_order(
    service: BacktestingService, recommendation_repository
) -> None:
    await recommendation_repository.store_result(make_recommendation_result("rec-a", (make_candidate("A", 30.0),)))
    await recommendation_repository.store_result(make_recommendation_result("rec-b", (make_candidate("A", 90.0),)))
    forward = [_snapshot(NOW - timedelta(days=1), "rec-a"), _snapshot(NOW, "rec-b")]
    backward = list(reversed(forward))

    request_forward = await _request(service, name="Forward")
    result_forward = await service.run_backtest(request_forward, forward)

    request_backward = await _request(service, name="Backward")
    result_backward = await service.run_backtest(request_backward, backward)

    assert result_forward.portfolio_return == result_backward.portfolio_return


# --- Large datasets -----------------------------------------------------------


async def test_large_historical_dataset_processes_successfully(
    backtesting_repository, recommendation_service, strategy_service, risk_service, recommendation_repository
) -> None:
    large_service = BacktestingService(
        backtesting_repository, recommendation_service, strategy_service, risk_service, max_periods=500
    )
    for i in range(200):
        await recommendation_repository.store_result(
            make_recommendation_result(f"rec-{i}", (make_candidate("A", float(i % 101)),))
        )
    request = await _request(large_service, name="Large")
    snapshots = [
        _snapshot(NOW - timedelta(days=200 - i), f"rec-{i}") for i in range(200)
    ]

    result = await large_service.run_backtest(request, snapshots)

    assert result.total_periods == 200
    assert 0 <= result.win_rate <= 100
    assert result.max_drawdown >= 0


async def test_weekly_replay_mode_reduces_processed_snapshot_count(
    service: BacktestingService, recommendation_repository
) -> None:
    await recommendation_repository.store_result(make_recommendation_result("rec-1", (make_candidate("A", 50.0),)))
    request = await _request(service, name="Weekly", replay_mode=ReplayMode.WEEKLY)
    # 14 consecutive daily snapshots span exactly 2 ISO weeks
    snapshots = [_snapshot(NOW - timedelta(days=offset), "rec-1") for offset in range(14)]

    result = await service.run_backtest(request, snapshots)

    assert result.total_periods <= 3
