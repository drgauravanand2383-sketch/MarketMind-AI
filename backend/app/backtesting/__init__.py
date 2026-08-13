"""Backtesting Framework: deterministically replays already-generated
Recommendation, Strategy Evaluation, and Risk Analytics output across
historical snapshots, providing analytical insight only.

No live market data fetch, no trade execution, no order book simulation,
no slippage/commission modeling, no portfolio optimization, and no Monte
Carlo simulation exist anywhere in this package.
"""

from __future__ import annotations

from app.backtesting.exceptions import (
    BacktestingError,
    BacktestRequestNotFoundError,
    BacktestResultNotFoundError,
    BacktestRunNotFoundError,
    DuplicateBacktestRequestNameError,
    InvalidSnapshotReferenceError,
    MaxReplayPeriodsExceededError,
)
from app.backtesting.models import (
    BacktestPeriod,
    BacktestRequest,
    BacktestResult,
    BacktestRun,
    BacktestStatus,
    HistoricalSnapshot,
    ReplayMode,
)
from app.backtesting.engine import BacktestingService

__all__ = [
    "BacktestingService",
    "ReplayMode",
    "BacktestStatus",
    "BacktestRequest",
    "HistoricalSnapshot",
    "BacktestPeriod",
    "BacktestRun",
    "BacktestResult",
    "BacktestingError",
    "BacktestRequestNotFoundError",
    "BacktestRunNotFoundError",
    "BacktestResultNotFoundError",
    "DuplicateBacktestRequestNameError",
    "InvalidSnapshotReferenceError",
    "MaxReplayPeriodsExceededError",
]
