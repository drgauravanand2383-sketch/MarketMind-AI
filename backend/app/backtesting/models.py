"""Domain models for the Backtesting Framework.

Deterministically replays already-generated `app.recommendations.models
.RecommendationResult` (Sprint 49), `app.strategy.models
.StrategyEvaluationResult` (Sprint 50), and `app.risk.models.RiskAssessment`
(Sprint 51) output across a caller-supplied sequence of historical
snapshots. This framework never fetches live market data, never executes
a trade, never simulates an order book, never models slippage or
commissions, never optimizes a portfolio, and never runs a Monte Carlo
simulation.

Design note — a genuinely different reuse pattern from every evaluation
engine since Sprint 48: Screening/Signals/Alerts/Recommendations/Strategy/
Risk each *consume* an already-computed object handed to them directly by
the caller and never call back into the engine that produced it. This
sprint's own capabilities ("Invoke existing recommendation outputs",
"Invoke existing strategy evaluations", "Invoke existing risk
assessments") and its "Existing snapshot references" validation
requirement describe the opposite: `HistoricalSnapshot` carries *request
ids* (`recommendation_result_id`, `strategy_evaluation_id`,
`risk_assessment_id`), and `app.backtesting.engine.BacktestingService` is
constructed with the three already-built services
(`PortfolioRecommendationService`, `StrategyEvaluationService`,
`RiskAnalyticsService`) injected directly, calling their own read-only
`get_result`/`get_evaluation`/`get_assessment` methods (never their
generate/evaluate/assess methods) to resolve each snapshot's referenced,
already-persisted result. This is "reuse existing services through
dependency injection only" read literally: replay's entire job is to look
up and stitch together results those three engines already computed and
stored at some earlier point — not to re-run any of their scoring. A
dangling reference (an id nothing was ever stored under) surfaces
naturally as the referenced service's own `*NotFoundError`, which is
exactly what "Existing snapshot references" validation means here: this
framework has no independent way to check a reference's validity except
by resolving it.

Design note — no real portfolio value, price, or P&L data anywhere in
this pipeline: like `app.risk.models` (Sprint 51) before it, nothing
reachable by this framework carries a dollar position size, a real
historical price, or a trade fill. `BacktestPeriod.portfolio_value` is
therefore a deterministic *proxy*, not a real valuation — see
`app.backtesting.engine`'s own docstring for the exact, fully-documented
formula built only from the three reused engines' already-computed 0-100
scores. `HistoricalSnapshot.benchmark_value` is the one exception: no
source for a benchmark's historical value exists anywhere in this
pipeline either (and fetching one is forbidden), so it is accepted as a
directly-supplied, caller-provided value — the same resolution
`CandidateEvidence.planning_score` (Sprint 49) used for a component with
no derivable source at all.

Design note — additive fields, flagged per this codebase's established
precedent:
  - `BacktestStatus`: `BacktestRun.status` is a named field with no enum
    defined anywhere in the sprint's own "Support:" sections (unlike
    `ReplayMode`, which is explicitly enumerated). A run's lifecycle needs
    *some* typed status; `PENDING`/`RUNNING`/`COMPLETED`/`FAILED` mirrors
    the shape of every other status enum in this codebase (e.g.
    `app.alerts.models.AlertStatus`, Sprint 48).
  - `BacktestResult.request_id`/`generated_at`: the repository's
    `store_result()`/`get_result()` pair (a *separate* pair from
    `store_run()`/`get_run()`) needs a key to store and retrieve by, and
    (since "Repeated identical runs produce identical outputs" implies a
    request can be re-run) a timestamp to resolve "most recent" when more
    than one result has been stored for the same request — exactly the
    same two fields every other engine's own result model in this series
    already carries (`RecommendationResult.request_id`/`generated_at`,
    `StrategyEvaluationResult.request_id`/`evaluated_at`,
    `RiskAssessment.request_id`/`generated_at`); `BacktestResult`
    conspicuously had neither in its literal field list.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "ReplayMode",
    "BacktestStatus",
    "BacktestRequest",
    "HistoricalSnapshot",
    "BacktestPeriod",
    "BacktestRun",
    "BacktestResult",
]


class ReplayMode(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    CUSTOM = "CUSTOM"


class BacktestStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class BacktestRequest(BaseModel):
    """A request to run one backtest, referencing (never resolving/fetching
    — see module docstring) whichever historical snapshots inform it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    start_date: date
    end_date: date
    initial_capital: float = Field(gt=0)
    benchmark: str = Field(min_length=1)
    strategy_ids: tuple[str, ...] = Field(default_factory=tuple)
    replay_mode: ReplayMode = ReplayMode.DAILY
    created_at: datetime

    @model_validator(mode="after")
    def _validate_date_range(self) -> BacktestRequest:
        if self.start_date > self.end_date:
            raise ValueError("start_date must not be after end_date.")
        return self


class HistoricalSnapshot(BaseModel):
    """One point in replay time: references to the already-computed,
    already-persisted recommendation/strategy/risk results in effect at
    `timestamp` (resolved via the injected services — see module
    docstring), plus the historical benchmark value at that same moment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    timestamp: datetime
    recommendation_result_id: str = Field(min_length=1)
    strategy_evaluation_id: str | None = None
    risk_assessment_id: str | None = None
    benchmark_value: float | None = None

    @field_validator("timestamp")
    @classmethod
    def _ensure_timezone_aware(cls, value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class BacktestPeriod(BaseModel):
    """One replayed period's outcome — see `app.backtesting.engine` for
    exactly how `portfolio_value`/`return_percent` are derived."""

    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    portfolio_value: float
    benchmark_value: float | None = None
    return_percent: float
    notes: str = ""


class BacktestRun(BaseModel):
    """One execution's bookkeeping: lifecycle status, timing, and the raw
    per-period breakdown. See `BacktestResult` for the aggregate summary
    metrics computed from `results`."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    started_at: datetime
    completed_at: datetime | None = None
    status: BacktestStatus
    processed_snapshots: int = Field(default=0, ge=0)
    results: tuple[BacktestPeriod, ...] = Field(default_factory=tuple)


class BacktestResult(BaseModel):
    """The aggregate summary metrics of one `BacktestingService
    .run_backtest()` run — see `app.backtesting.engine` for exactly how
    each metric is calculated."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    portfolio_return: float
    benchmark_return: float
    excess_return: float
    max_drawdown: float = Field(ge=0)
    win_rate: float = Field(ge=0, le=100)
    total_periods: int = Field(ge=0)
    successful_periods: int = Field(ge=0)
    failed_periods: int = Field(ge=0)
    summary: str
    generated_at: datetime
