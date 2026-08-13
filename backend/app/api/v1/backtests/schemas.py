"""HTTP-layer request schemas for the Backtesting API.

Response bodies reuse `app.backtesting.models` directly (`BacktestRun`,
`BacktestResult`) — already fully-typed Pydantic domain models. The
request body has no matching domain model (`BacktestingService.create_request()`
takes individual primitive arguments, and `run_backtest()` separately
needs the caller-supplied snapshot list) — `HistoricalSnapshot` itself
is reused directly as the nested `snapshots` item type.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.backtesting.models import HistoricalSnapshot, ReplayMode

__all__ = ["CreateBacktestRequest"]


class CreateBacktestRequest(BaseModel):
    """Request body for `POST /api/v1/backtests` — creates the
    `BacktestRequest` and immediately runs it against the supplied
    snapshots in one call."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, examples=["Q1 2026 Momentum Backtest"])
    description: str = ""
    start_date: date
    end_date: date
    initial_capital: float = Field(gt=0, examples=[100000.0])
    benchmark: str = Field(min_length=1, examples=["SPY"])
    strategy_ids: tuple[str, ...] = ()
    replay_mode: ReplayMode = ReplayMode.DAILY
    snapshots: list[HistoricalSnapshot] = Field(default_factory=list)
