"""BacktestingService: the Backtesting Framework's Application layer.

Deterministically replays already-computed `RecommendationResult`/
`StrategyEvaluationResult`/`RiskAssessment` output across a caller-supplied
sequence of `HistoricalSnapshot`s — never fetches live market data, never
executes a trade, never simulates an order book, never models slippage or
commissions, never optimizes a portfolio, and never runs a Monte Carlo
simulation. Combines request/run/result management (delegated to an
injected `BaseBacktestingRepository`) with replay execution (pure,
deterministic given its inputs — no randomness, no wall-clock dependency
beyond the injected `now_fn` used purely for bookkeeping timestamps).

Reuse discipline — read-only invocation, not re-computation: unlike every
evaluation engine since Sprint 48 (which only ever *consumes* an
already-computed object the caller hands it directly), this service is
constructed with the actual `PortfolioRecommendationService`,
`StrategyEvaluationService`, and `RiskAnalyticsService` instances injected,
and calls only their read-only `get_result`/`get_evaluation`/
`get_assessment` methods to resolve each snapshot's referenced ids. It
never calls `generate_recommendations`/`evaluate_recommendations`/
`assess_portfolio` — replay only ever looks up results those engines
already computed and persisted at some earlier point; it never re-runs
their scoring. See `app.backtesting.models`'s own module docstring for the
full rationale.

Portfolio value proxy — the exact formula: nothing reachable by this
framework carries a real historical price, position size, or trade fill
(forbidden/unavailable — see `app.backtesting.models`). For each replayed
period, up to three already-computed 0-100 "component scores" are
gathered from whichever of the three reused engines' results are present:

  - `recommendation_component` = the mean `overall_score` across the
    resolved `RecommendationResult.recommendations` (`None` if empty).
  - `strategy_component` = when `BacktestRequest.strategy_ids` is
    non-empty, the mean `alignment_score` of whichever `StrategyMatch`
    entries in the resolved `StrategyEvaluationResult.strategy_matches`
    belong to one of those ids (`None` if none match); otherwise, that
    result's own `overall_alignment`. `None` if no strategy evaluation was
    resolved for this snapshot (`strategy_evaluation_id` was absent).
  - `risk_component` = `100 - RiskAssessment.overall_risk_score` (inverted
    so higher consistently means "better", matching the other two
    components' polarity). `None` if no risk assessment was resolved.

`period_score` is the plain average of whichever components are available
for that period (mirrors the documented, flagged "average of available
components" blend `app.recommendations.engine`/`app.strategy.engine`
already established), falling back to the *previous* period's score (flat,
0% change) when a period has no resolvable component at all, or `50.0`
(a neutral midpoint) for a scoreless first period.

`portfolio_value = initial_capital * (period_score / 100)` — this is a
transparent, deterministic function of already-computed analytical
quality scores, standing in for a real valuation this framework has no
data to compute; it is NOT a simulated dollar P&L. `return_percent` for a
period is the percent change in `portfolio_value` from the immediately
preceding period (0.0 for the first period — no prior baseline).
`benchmark_value` is carried through directly from each snapshot's own
caller-supplied value (see `app.backtesting.models`), never derived.

Metric formulas (see `_compute_result` below): `portfolio_return`/
`benchmark_return` are the standard cumulative percent change from the
first to the last period's value; `excess_return = portfolio_return -
benchmark_return`; `max_drawdown` is the standard running-peak-to-trough
maximum percentage decline; `win_rate` is the percentage of periods with
a strictly positive `return_percent`.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from app.backtesting.exceptions import (
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
from app.recommendations.engine import PortfolioRecommendationService
from app.recommendations.exceptions import RecommendationResultNotFoundError
from app.recommendations.models import RecommendationResult
from app.risk.engine import RiskAnalyticsService
from app.risk.exceptions import RiskAssessmentNotFoundError
from app.risk.models import RiskAssessment
from app.strategy.engine import StrategyEvaluationService
from app.strategy.exceptions import StrategyEvaluationNotFoundError
from app.strategy.models import StrategyEvaluationResult

if TYPE_CHECKING:
    from app.repositories.backtesting.repository import BaseBacktestingRepository

__all__ = ["BacktestingService"]

DEFAULT_MAX_PERIODS = 1000

_ResolvedSnapshot = tuple[RecommendationResult, "StrategyEvaluationResult | None", "RiskAssessment | None"]


def _default_now() -> datetime:
    return datetime.now(UTC)


class BacktestingService:
    def __init__(
        self,
        repository: BaseBacktestingRepository,
        recommendation_service: PortfolioRecommendationService,
        strategy_service: StrategyEvaluationService,
        risk_service: RiskAnalyticsService,
        *,
        enforce_unique_names: bool = True,
        max_periods: int = DEFAULT_MAX_PERIODS,
        now_fn: Callable[[], datetime] = _default_now,
    ) -> None:
        self._repository = repository
        self._recommendation_service = recommendation_service
        self._strategy_service = strategy_service
        self._risk_service = risk_service
        self._enforce_unique_names = enforce_unique_names
        self._max_periods = max_periods
        self._now_fn = now_fn

    # --- Request management -----------------------------------------------------------

    async def create_request(
        self,
        name: str,
        start_date: date,
        end_date: date,
        initial_capital: float,
        benchmark: str,
        *,
        description: str = "",
        strategy_ids: tuple[str, ...] = (),
        replay_mode: ReplayMode = ReplayMode.DAILY,
    ) -> BacktestRequest:
        """Create a new backtest request.

        Raises:
            DuplicateBacktestRequestNameError: `name` is already in use
                (only when `enforce_unique_names=True`, the default).
        """
        await self._check_unique_name(name)
        request = BacktestRequest(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            benchmark=benchmark,
            strategy_ids=tuple(strategy_ids),
            replay_mode=replay_mode,
            created_at=self._now_fn(),
        )
        return await self._repository.create_request(request)

    async def get_request(self, request_id: str) -> BacktestRequest:
        """Raises `BacktestRequestNotFoundError` if no request exists for `request_id`."""
        request = await self._repository.get_request(request_id)
        if request is None:
            raise BacktestRequestNotFoundError(request_id)
        return request

    async def list_requests(self) -> list[BacktestRequest]:
        return await self._repository.list_requests()

    async def get_run(self, request_id: str) -> BacktestRun:
        """Raises `BacktestRunNotFoundError` if no run exists for `request_id`."""
        run = await self._repository.get_run(request_id)
        if run is None:
            raise BacktestRunNotFoundError(request_id)
        return run

    async def list_runs(self) -> list[BacktestRun]:
        return await self._repository.list_runs()

    async def get_result(self, request_id: str) -> BacktestResult:
        """Raises `BacktestResultNotFoundError` if no result exists for `request_id`."""
        result = await self._repository.get_result(request_id)
        if result is None:
            raise BacktestResultNotFoundError(request_id)
        return result

    async def _check_unique_name(self, name: str) -> None:
        if not self._enforce_unique_names:
            return
        for existing in await self._repository.list_requests():
            if existing.name == name:
                raise DuplicateBacktestRequestNameError(name)

    # --- Replay -----------------------------------------------------------

    def select_snapshots(
        self, snapshots: list[HistoricalSnapshot], mode: ReplayMode
    ) -> list[HistoricalSnapshot]:
        """Order `snapshots` chronologically and, for `WEEKLY`/`MONTHLY`
        modes, downsample to one representative (the chronologically last)
        snapshot per calendar week/month. `DAILY`/`CUSTOM` pass every
        snapshot through unchanged (beyond chronological ordering) — see
        this module's own docstring for why. Guarantees the deterministic
        ordering this sprint's own Replay Rules require, regardless of the
        order `snapshots` was supplied in.
        """
        return _select_snapshots_for_mode(snapshots, mode)

    async def run_backtest(
        self, request: BacktestRequest, snapshots: list[HistoricalSnapshot]
    ) -> BacktestResult:
        """Replay `snapshots` against `request`'s configuration, persist
        both the full per-period `BacktestRun` and the aggregate
        `BacktestResult`, and return the aggregate result.

        Raises:
            MaxReplayPeriodsExceededError: `len(snapshots)` exceeds the
                configured `max_periods`.
            InvalidSnapshotReferenceError: a snapshot references a
                recommendation/strategy/risk request id that could not be
                resolved via the injected services. A `FAILED`
                `BacktestRun` is persisted before this is raised.
        """
        if len(snapshots) > self._max_periods:
            raise MaxReplayPeriodsExceededError(request.id, len(snapshots), self._max_periods)

        started_at = self._now_fn()
        selected = self.select_snapshots(snapshots, request.replay_mode)

        try:
            resolved = [await self._resolve_snapshot(snapshot) for snapshot in selected]
        except (
            RecommendationResultNotFoundError,
            StrategyEvaluationNotFoundError,
            RiskAssessmentNotFoundError,
        ) as exc:
            failed_run = BacktestRun(
                request_id=request.id,
                started_at=started_at,
                completed_at=self._now_fn(),
                status=BacktestStatus.FAILED,
                processed_snapshots=0,
                results=(),
            )
            await self._repository.store_run(failed_run)
            raise InvalidSnapshotReferenceError(request.id, str(exc)) from exc

        periods = _build_periods(selected, resolved, request.initial_capital, request.strategy_ids)

        run = BacktestRun(
            request_id=request.id,
            started_at=started_at,
            completed_at=self._now_fn(),
            status=BacktestStatus.COMPLETED,
            processed_snapshots=len(selected),
            results=tuple(periods),
        )
        await self._repository.store_run(run)

        result = _compute_result(request.id, periods, self._now_fn())
        await self._repository.store_result(result)
        return result

    async def _resolve_snapshot(self, snapshot: HistoricalSnapshot) -> _ResolvedSnapshot:
        recommendation_result = await self._recommendation_service.get_result(
            snapshot.recommendation_result_id
        )
        strategy_evaluation_result = (
            await self._strategy_service.get_evaluation(snapshot.strategy_evaluation_id)
            if snapshot.strategy_evaluation_id is not None
            else None
        )
        risk_assessment = (
            await self._risk_service.get_assessment(snapshot.risk_assessment_id)
            if snapshot.risk_assessment_id is not None
            else None
        )
        return recommendation_result, strategy_evaluation_result, risk_assessment


def _select_snapshots_for_mode(
    snapshots: list[HistoricalSnapshot], mode: ReplayMode
) -> list[HistoricalSnapshot]:
    ordered = sorted(snapshots, key=lambda snapshot: snapshot.timestamp)
    if mode in (ReplayMode.DAILY, ReplayMode.CUSTOM):
        return ordered

    key_fn: Callable[[HistoricalSnapshot], tuple[int, int]]
    if mode == ReplayMode.WEEKLY:

        def key_fn(snapshot: HistoricalSnapshot) -> tuple[int, int]:
            return snapshot.timestamp.isocalendar()[:2]
    else:  # ReplayMode.MONTHLY

        def key_fn(snapshot: HistoricalSnapshot) -> tuple[int, int]:
            return (snapshot.timestamp.year, snapshot.timestamp.month)

    grouped: dict[tuple[int, int], HistoricalSnapshot] = {}
    for snapshot in ordered:
        grouped[key_fn(snapshot)] = snapshot  # ascending iteration -> last-in-period wins
    return list(grouped.values())


def _period_component_scores(
    recommendation_result: RecommendationResult,
    strategy_evaluation_result: StrategyEvaluationResult | None,
    risk_assessment: RiskAssessment | None,
    strategy_ids: tuple[str, ...],
) -> tuple[float | None, float | None, float | None]:
    candidates = recommendation_result.recommendations
    recommendation_component = (
        round(sum(c.overall_score for c in candidates) / len(candidates), 4) if candidates else None
    )

    strategy_component: float | None = None
    if strategy_evaluation_result is not None:
        if strategy_ids:
            matches = [
                match
                for match in strategy_evaluation_result.strategy_matches
                if match.strategy_id in strategy_ids
            ]
            if matches:
                strategy_component = round(
                    sum(match.alignment_score for match in matches) / len(matches), 4
                )
        else:
            strategy_component = strategy_evaluation_result.overall_alignment

    risk_component = 100.0 - risk_assessment.overall_risk_score if risk_assessment is not None else None

    return recommendation_component, strategy_component, risk_component


def _blend_period_score(components: tuple[float | None, ...], previous_score: float | None) -> float:
    available = [component for component in components if component is not None]
    if available:
        return round(sum(available) / len(available), 4)
    return previous_score if previous_score is not None else 50.0


def _build_periods(
    snapshots: list[HistoricalSnapshot],
    resolved: list[_ResolvedSnapshot],
    initial_capital: float,
    strategy_ids: tuple[str, ...],
) -> list[BacktestPeriod]:
    periods: list[BacktestPeriod] = []
    previous_value: float | None = None
    previous_score: float | None = None

    for snapshot, (recommendation_result, strategy_evaluation_result, risk_assessment) in zip(
        snapshots, resolved, strict=True
    ):
        recommendation_component, strategy_component, risk_component = _period_component_scores(
            recommendation_result, strategy_evaluation_result, risk_assessment, strategy_ids
        )
        score = _blend_period_score(
            (recommendation_component, strategy_component, risk_component), previous_score
        )
        value = round(initial_capital * (score / 100.0), 2)
        return_percent = (
            0.0
            if previous_value is None
            else (round((value - previous_value) / previous_value * 100, 4) if previous_value != 0 else 0.0)
        )

        periods.append(
            BacktestPeriod(
                timestamp=snapshot.timestamp,
                portfolio_value=value,
                benchmark_value=snapshot.benchmark_value,
                return_percent=return_percent,
                notes=(
                    f"period_score={score} (recommendation={recommendation_component}, "
                    f"strategy={strategy_component}, risk_inverted={risk_component})"
                ),
            )
        )
        previous_value = value
        previous_score = score

    return periods


def _cumulative_return(values: list[float]) -> float:
    if len(values) < 2 or values[0] == 0:
        return 0.0
    return round((values[-1] - values[0]) / values[0] * 100, 4)


def _max_drawdown(values: list[float]) -> float:
    if not values:
        return 0.0
    peak = values[0]
    max_drawdown = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            drawdown = (peak - value) / peak * 100
            max_drawdown = max(max_drawdown, drawdown)
    return round(max_drawdown, 4)


def _compute_result(request_id: str, periods: list[BacktestPeriod], generated_at: datetime) -> BacktestResult:
    total_periods = len(periods)
    if total_periods == 0:
        return BacktestResult(
            request_id=request_id,
            portfolio_return=0.0,
            benchmark_return=0.0,
            excess_return=0.0,
            max_drawdown=0.0,
            win_rate=0.0,
            total_periods=0,
            successful_periods=0,
            failed_periods=0,
            summary="No periods were processed.",
            generated_at=generated_at,
        )

    portfolio_values = [period.portfolio_value for period in periods]
    portfolio_return = _cumulative_return(portfolio_values)

    benchmark_values = [period.benchmark_value for period in periods if period.benchmark_value is not None]
    benchmark_return = _cumulative_return(benchmark_values) if len(benchmark_values) >= 2 else 0.0

    excess_return = round(portfolio_return - benchmark_return, 4)
    max_drawdown = _max_drawdown(portfolio_values)

    successful_periods = sum(1 for period in periods if period.return_percent > 0)
    failed_periods = total_periods - successful_periods
    win_rate = round((successful_periods / total_periods) * 100, 2)

    summary = (
        f"Portfolio return {portfolio_return}% vs benchmark {benchmark_return}% "
        f"(excess {excess_return}%) across {total_periods} period(s); "
        f"win rate {win_rate}%, max drawdown {max_drawdown}%."
    )

    return BacktestResult(
        request_id=request_id,
        portfolio_return=portfolio_return,
        benchmark_return=benchmark_return,
        excess_return=excess_return,
        max_drawdown=max_drawdown,
        win_rate=win_rate,
        total_periods=total_periods,
        successful_periods=successful_periods,
        failed_periods=failed_periods,
        summary=summary,
        generated_at=generated_at,
    )
