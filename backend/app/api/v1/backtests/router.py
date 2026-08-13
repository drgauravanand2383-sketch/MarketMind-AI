"""FastAPI router for the Backtesting API (`/api/v1/backtests`).

Every handler is a thin translation: resolve `BacktestingService` via
dependency injection, call exactly one or two of its existing methods,
wrap the result. `BacktestingError` subclasses (`BacktestRequestNotFoundError`,
`BacktestRunNotFoundError`, `BacktestResultNotFoundError`,
`DuplicateBacktestRequestNameError`, `InvalidSnapshotReferenceError`,
`MaxReplayPeriodsExceededError`) are never caught here; they propagate to
the centralized domain-exception handler already registered in Sprint
55/56 (`app.api.v1.exception_handlers.handlers`).

`{run_id}` is the `BacktestRequest.id` throughout — `BacktestRun` and
`BacktestResult` have no id of their own, each is looked up by the
request id that produced it (the repository always returns the most
recently stored one for that id).

Every endpoint requires authentication and a specific permission — see
each route's own `dependencies=[Depends(require_policy(...))]`. No inline
role/permission check exists anywhere in this module.

`create_backtest` (Sprint 59) additionally publishes `BACKTEST_STARTED`
and `BACKTEST_COMPLETED` real-time events via `EventPublisher`.
`BacktestingService.run_backtest()` computes and persists both the run
and the result in one call — it never persists an intermediate
PENDING/RUNNING `BacktestRun` — so the "started" event's `BacktestRun`
payload is built here from already-known fields (the request id and the
current time) purely to announce that the run has begun before the
(potentially slow) `run_backtest()` call executes; nothing about that
struct is computed or evaluated.
"""

from __future__ import annotations

import uuid as uuid_module
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, status

from app.api.v1.backtests.dependencies import get_backtesting_service
from app.api.v1.backtests.schemas import CreateBacktestRequest
from app.api.v1.schemas.common import SuccessResponse, build_success_response
from app.api.ws.dependencies.services import get_event_publisher
from app.api.ws.publishers.event_publisher import EventPublisher
from app.auth.dependencies.policy_guard import require_policy
from app.auth.policies import RequirePermission
from app.backtesting.engine import BacktestingService
from app.backtesting.models import BacktestResult, BacktestRun, BacktestStatus

__all__ = ["router"]

router = APIRouter(prefix="/backtests", tags=["Backtesting"])


@router.post(
    "",
    response_model=SuccessResponse[BacktestResult],
    status_code=status.HTTP_201_CREATED,
    summary="Run a backtest",
    description="Creates the BacktestRequest and immediately runs it against the supplied snapshots.",
    dependencies=[Depends(require_policy(RequirePermission("backtest:run")))],
)
async def create_backtest(
    request: Request,
    body: CreateBacktestRequest,
    service: BacktestingService = Depends(get_backtesting_service),
    event_publisher: EventPublisher = Depends(get_event_publisher),
) -> SuccessResponse[BacktestResult]:
    backtest_request = await service.create_request(
        body.name,
        body.start_date,
        body.end_date,
        body.initial_capital,
        body.benchmark,
        description=body.description,
        strategy_ids=body.strategy_ids,
        replay_mode=body.replay_mode,
    )
    started_run = BacktestRun(
        request_id=backtest_request.id, started_at=datetime.now(timezone.utc), status=BacktestStatus.PENDING
    )
    await event_publisher.publish_backtest_started(started_run)

    result = await service.run_backtest(backtest_request, body.snapshots)
    await event_publisher.publish_backtest_completed(result)
    return build_success_response(result, request)


@router.get(
    "/{run_id}",
    response_model=SuccessResponse[BacktestRun],
    summary="Get a backtest run",
    description="Status/lifecycle and raw per-period detail for a backtest run — see `BacktestingService.get_run`.",
    dependencies=[Depends(require_policy(RequirePermission("backtest:read")))],
)
async def get_backtest_run(
    request: Request,
    run_id: uuid_module.UUID,
    service: BacktestingService = Depends(get_backtesting_service),
) -> SuccessResponse[BacktestRun]:
    run = await service.get_run(str(run_id))
    return build_success_response(run, request)


@router.get(
    "/{run_id}/results",
    response_model=SuccessResponse[BacktestResult],
    summary="Get a backtest run's results",
    description="Aggregate summary metrics for a backtest run — see `BacktestingService.get_result`.",
    dependencies=[Depends(require_policy(RequirePermission("backtest:read")))],
)
async def get_backtest_results(
    request: Request,
    run_id: uuid_module.UUID,
    service: BacktestingService = Depends(get_backtesting_service),
) -> SuccessResponse[BacktestResult]:
    result = await service.get_result(str(run_id))
    return build_success_response(result, request)
