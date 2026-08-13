"""FastAPI router for the Strategy Evaluation API (`/api/v1/strategies`).

Every handler is a thin translation: resolve `StrategyEvaluationService`
via dependency injection, call exactly one of its existing methods, wrap
the result. `StrategyEngineError` subclasses are never caught here; they
propagate to the centralized domain-exception handler already registered
in Sprint 55/56.

Evaluating a strategy needs an already-computed `RecommendationResult` —
`get_recommendation_service` (reused from `app.api.v1.portfolio.dependencies`)
resolves it. `StrategyEvaluationService` has no `create_request`-style
helper of its own (unlike Risk/Recommendation), so the router builds the
`StrategyEvaluationRequest` itself before calling `evaluate_recommendations`.

Literal-path `/evaluate` and `/results/{result_id}` are registered before
`/{strategy_id}` — see `app/api/v1/portfolio/router.py`'s own docstring
for why registration order matters to FastAPI's route matching.
"""

from __future__ import annotations

import uuid as uuid_module
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, status

from app.api.v1.portfolio.dependencies import get_recommendation_service
from app.api.v1.schemas.common import PaginatedResponse, SuccessResponse, build_success_response
from app.api.v1.schemas.pagination import PaginationParams, build_paginated_response, paginate_items, pagination_params
from app.api.v1.strategies.dependencies import get_strategy_service
from app.api.ws.dependencies.services import get_event_publisher
from app.api.ws.publishers.event_publisher import EventPublisher
from app.api.v1.strategies.schemas import CreateStrategyRequest, EvaluateStrategyRequest, UpdateStrategyRequest
from app.auth.dependencies.policy_guard import require_policy
from app.auth.policies import RequirePermission
from app.recommendations.engine import PortfolioRecommendationService
from app.strategy.engine import StrategyEvaluationService
from app.strategy.models import InvestmentStrategy, StrategyEvaluationRequest, StrategyEvaluationResult

__all__ = ["router"]

router = APIRouter(prefix="/strategies", tags=["Strategy Evaluation"])

_SORTABLE_FIELDS = frozenset({"name", "created_at", "updated_at"})


def _sort_key(strategy: InvestmentStrategy, field: str) -> object:
    if field == "name":
        return strategy.name.lower()
    return getattr(strategy, field)


@router.get(
    "",
    response_model=PaginatedResponse[InvestmentStrategy],
    summary="List strategies",
    description="Paginated, sortable list of every investment strategy.",
    dependencies=[Depends(require_policy(RequirePermission("strategy:read")))],
)
async def list_strategies(
    request: Request,
    pagination: PaginationParams = Depends(pagination_params),
    service: StrategyEvaluationService = Depends(get_strategy_service),
) -> PaginatedResponse[InvestmentStrategy]:
    strategies = await service.list_strategies()
    page_items, total = paginate_items(strategies, pagination, sortable_fields=_SORTABLE_FIELDS, key_fn=_sort_key)
    return build_paginated_response(page_items, total, pagination, request)


@router.post(
    "",
    response_model=SuccessResponse[InvestmentStrategy],
    status_code=status.HTTP_201_CREATED,
    summary="Create a strategy",
    description="Create a new named investment strategy with the given weightings and rules.",
    dependencies=[Depends(require_policy(RequirePermission("strategy:update")))],
)
async def create_strategy(
    request: Request,
    body: CreateStrategyRequest,
    service: StrategyEvaluationService = Depends(get_strategy_service),
) -> SuccessResponse[InvestmentStrategy]:
    strategy = await service.create_strategy(
        body.name,
        description=body.description,
        strategy_type=body.strategy_type,
        enabled=body.enabled,
        weightings=body.weightings,
        rules=body.rules,
    )
    return build_success_response(strategy, request)


@router.post(
    "/evaluate",
    response_model=SuccessResponse[StrategyEvaluationResult],
    status_code=status.HTTP_201_CREATED,
    summary="Evaluate strategies against a recommendation result",
    description="Evaluates every enabled strategy in `strategy_ids` (or every strategy, if empty) "
    "against the given RecommendationResult.",
    dependencies=[Depends(require_policy(RequirePermission("strategy:evaluate")))],
)
async def evaluate_strategies(
    request: Request,
    body: EvaluateStrategyRequest,
    service: StrategyEvaluationService = Depends(get_strategy_service),
    recommendation_service: PortfolioRecommendationService = Depends(get_recommendation_service),
    event_publisher: EventPublisher = Depends(get_event_publisher),
) -> SuccessResponse[StrategyEvaluationResult]:
    recommendation_result = await recommendation_service.get_result(body.recommendation_result_id)
    if body.strategy_ids:
        strategies = [await service.get_strategy(strategy_id) for strategy_id in body.strategy_ids]
    else:
        strategies = await service.list_strategies()

    evaluation_request = StrategyEvaluationRequest(
        id=str(uuid_module.uuid4()),
        strategy_ids=tuple(strategy.id for strategy in strategies),
        recommendation_result_id=body.recommendation_result_id,
        created_at=datetime.now(timezone.utc),
    )
    result = await service.evaluate_recommendations(evaluation_request, recommendation_result, strategies)
    await event_publisher.publish_strategy_evaluation_completed(result)
    return build_success_response(result, request)


@router.get(
    "/results/{result_id}",
    response_model=SuccessResponse[StrategyEvaluationResult],
    summary="Get a strategy evaluation result",
    description="`result_id` is the evaluation request's id — see `StrategyEvaluationService.get_evaluation`.",
    dependencies=[Depends(require_policy(RequirePermission("strategy:read")))],
)
async def get_strategy_evaluation(
    request: Request,
    result_id: uuid_module.UUID,
    service: StrategyEvaluationService = Depends(get_strategy_service),
) -> SuccessResponse[StrategyEvaluationResult]:
    result = await service.get_evaluation(str(result_id))
    return build_success_response(result, request)


@router.patch(
    "/{strategy_id}",
    response_model=SuccessResponse[InvestmentStrategy],
    summary="Update a strategy",
    description="`StrategyEvaluationService.update_strategy` is a whole-object replace — the router "
    "fetches the existing strategy, applies only the fields set in the request body, then replaces it.",
    dependencies=[Depends(require_policy(RequirePermission("strategy:update")))],
)
async def update_strategy(
    request: Request,
    strategy_id: uuid_module.UUID,
    body: UpdateStrategyRequest,
    service: StrategyEvaluationService = Depends(get_strategy_service),
) -> SuccessResponse[InvestmentStrategy]:
    existing = await service.get_strategy(str(strategy_id))
    updated = existing.model_copy(update=body.model_dump(exclude_unset=True))
    strategy = await service.update_strategy(updated)
    return build_success_response(strategy, request)


@router.delete(
    "/{strategy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a strategy",
    description="Permanently delete an investment strategy.",
    dependencies=[Depends(require_policy(RequirePermission("strategy:update")))],
)
async def delete_strategy(
    strategy_id: uuid_module.UUID,
    service: StrategyEvaluationService = Depends(get_strategy_service),
) -> None:
    await service.delete_strategy(str(strategy_id))
