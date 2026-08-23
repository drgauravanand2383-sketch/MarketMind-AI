"""Tests for BacktestingService.select_snapshots: replay-mode-driven
ordering and downsampling of historical snapshots."""

from __future__ import annotations

from datetime import UTC, datetime

from app.backtesting.engine import BacktestingService
from app.backtesting.models import HistoricalSnapshot, ReplayMode


def _snapshot(timestamp: datetime, rec_id: str = "rec-1") -> HistoricalSnapshot:
    return HistoricalSnapshot(timestamp=timestamp, recommendation_result_id=rec_id)


# --- DAILY / CUSTOM: pass-through, chronologically ordered -----------------------------------------------------------


def test_daily_mode_returns_every_snapshot_unchanged(service: BacktestingService) -> None:
    snapshots = [
        _snapshot(datetime(2026, 1, 1, tzinfo=UTC)),
        _snapshot(datetime(2026, 1, 2, tzinfo=UTC)),
        _snapshot(datetime(2026, 1, 3, tzinfo=UTC)),
    ]

    selected = service.select_snapshots(snapshots, ReplayMode.DAILY)

    assert len(selected) == 3


def test_custom_mode_returns_every_snapshot_unchanged(service: BacktestingService) -> None:
    snapshots = [
        _snapshot(datetime(2026, 1, 1, tzinfo=UTC)),
        _snapshot(datetime(2026, 1, 5, tzinfo=UTC)),
    ]

    selected = service.select_snapshots(snapshots, ReplayMode.CUSTOM)

    assert len(selected) == 2


def test_daily_mode_sorts_out_of_order_input_chronologically(service: BacktestingService) -> None:
    out_of_order = [
        _snapshot(datetime(2026, 1, 3, tzinfo=UTC)),
        _snapshot(datetime(2026, 1, 1, tzinfo=UTC)),
        _snapshot(datetime(2026, 1, 2, tzinfo=UTC)),
    ]

    selected = service.select_snapshots(out_of_order, ReplayMode.DAILY)

    assert [s.timestamp.day for s in selected] == [1, 2, 3]


# --- WEEKLY -----------------------------------------------------------


def test_weekly_mode_groups_by_iso_week_keeping_the_last_snapshot(service: BacktestingService) -> None:
    snapshots = [
        _snapshot(datetime(2026, 1, 5, tzinfo=UTC)),  # Mon, ISO week 2
        _snapshot(datetime(2026, 1, 7, tzinfo=UTC)),  # Wed, ISO week 2
        _snapshot(datetime(2026, 1, 12, tzinfo=UTC)),  # Mon, ISO week 3
    ]

    selected = service.select_snapshots(snapshots, ReplayMode.WEEKLY)

    assert len(selected) == 2
    assert selected[0].timestamp == datetime(2026, 1, 7, tzinfo=UTC)
    assert selected[1].timestamp == datetime(2026, 1, 12, tzinfo=UTC)


def test_weekly_mode_with_one_snapshot_per_week_keeps_all(service: BacktestingService) -> None:
    snapshots = [
        _snapshot(datetime(2026, 1, 5, tzinfo=UTC)),
        _snapshot(datetime(2026, 1, 12, tzinfo=UTC)),
        _snapshot(datetime(2026, 1, 19, tzinfo=UTC)),
    ]

    selected = service.select_snapshots(snapshots, ReplayMode.WEEKLY)

    assert len(selected) == 3


# --- MONTHLY -----------------------------------------------------------


def test_monthly_mode_groups_by_calendar_month_keeping_the_last_snapshot(service: BacktestingService) -> None:
    snapshots = [
        _snapshot(datetime(2026, 1, 5, tzinfo=UTC)),
        _snapshot(datetime(2026, 1, 25, tzinfo=UTC)),
        _snapshot(datetime(2026, 2, 10, tzinfo=UTC)),
    ]

    selected = service.select_snapshots(snapshots, ReplayMode.MONTHLY)

    assert len(selected) == 2
    assert selected[0].timestamp == datetime(2026, 1, 25, tzinfo=UTC)
    assert selected[1].timestamp == datetime(2026, 2, 10, tzinfo=UTC)


def test_monthly_mode_output_is_chronologically_ordered_regardless_of_input_order(
    service: BacktestingService,
) -> None:
    out_of_order = [
        _snapshot(datetime(2026, 3, 1, tzinfo=UTC)),
        _snapshot(datetime(2026, 1, 1, tzinfo=UTC)),
        _snapshot(datetime(2026, 2, 1, tzinfo=UTC)),
    ]

    selected = service.select_snapshots(out_of_order, ReplayMode.MONTHLY)

    assert [s.timestamp.month for s in selected] == [1, 2, 3]


# --- Determinism -----------------------------------------------------------


def test_selection_is_deterministic_regardless_of_input_order(service: BacktestingService) -> None:
    forward = [
        _snapshot(datetime(2026, 1, 1, tzinfo=UTC)),
        _snapshot(datetime(2026, 1, 8, tzinfo=UTC)),
        _snapshot(datetime(2026, 1, 15, tzinfo=UTC)),
    ]
    reversed_input = list(reversed(forward))

    selected_forward = service.select_snapshots(forward, ReplayMode.WEEKLY)
    selected_reversed = service.select_snapshots(reversed_input, ReplayMode.WEEKLY)

    assert [s.timestamp for s in selected_forward] == [s.timestamp for s in selected_reversed]


def test_empty_snapshot_list_returns_empty(service: BacktestingService) -> None:
    assert service.select_snapshots([], ReplayMode.DAILY) == []
    assert service.select_snapshots([], ReplayMode.WEEKLY) == []
