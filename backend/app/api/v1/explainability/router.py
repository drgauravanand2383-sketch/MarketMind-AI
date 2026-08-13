"""FastAPI router for the Explainability API (`/api/v1/explainability`).

Every handler is a thin translation: resolve `ExplainabilityService` via
dependency injection, call exactly one or two of its existing methods,
wrap the result. `ExplainabilityError` subclasses are never caught here;
they propagate to the centralized domain-exception handler already
registered in Sprint 55/56.

`ExplainabilityResult` has no id of its own — it's keyed by the
`ExplainabilityRequest.id` that produced it (a request can be re-explained;
`get_result` returns the most recently stored result for that id).

Every endpoint requires authentication and a specific permission — see
each route's own `dependencies=[Depends(require_policy(...))]`.
"""

from __future__ import annotations

import uuid as uuid_module

from fastapi import APIRouter, Depends, Request, status

from app.api.v1.explainability.dependencies import get_explainability_service
from app.api.v1.explainability.schemas import GenerateExplanationRequest
from app.api.v1.schemas.common import SuccessResponse, build_success_response
from app.api.ws.dependencies.services import get_event_publisher
from app.api.ws.publishers.event_publisher import EventPublisher
from app.auth.dependencies.policy_guard import require_policy
from app.auth.policies import RequirePermission
from app.explainability.engine import ExplainabilityService
from app.explainability.models import ExplainabilityResult

__all__ = ["router"]

router = APIRouter(prefix="/explainability", tags=["Explainability"])


@router.post(
    "",
    response_model=SuccessResponse[ExplainabilityResult],
    status_code=status.HTTP_201_CREATED,
    summary="Generate an explanation",
    description="Creates the ExplainabilityRequest and immediately generates its explanation.",
    dependencies=[Depends(require_policy(RequirePermission("explainability:generate")))],
)
async def create_explanation(
    request: Request,
    body: GenerateExplanationRequest,
    service: ExplainabilityService = Depends(get_explainability_service),
    event_publisher: EventPublisher = Depends(get_event_publisher),
) -> SuccessResponse[ExplainabilityResult]:
    explainability_request = await service.create_request(
        body.name,
        body.recommendation_result_id,
        strategy_evaluation_id=body.strategy_evaluation_id,
        risk_assessment_id=body.risk_assessment_id,
        backtest_run_id=body.backtest_run_id,
    )
    result = await service.explain(explainability_request)
    await event_publisher.publish_explainability_completed(result)
    return build_success_response(result, request)


@router.get(
    "/{request_id}",
    response_model=SuccessResponse[ExplainabilityResult],
    summary="Get an explanation",
    description="The most-recently-generated explanation for this request id — see `ExplainabilityService.get_result`.",
    dependencies=[Depends(require_policy(RequirePermission("explainability:read")))],
)
async def get_explanation(
    request: Request,
    request_id: uuid_module.UUID,
    service: ExplainabilityService = Depends(get_explainability_service),
) -> SuccessResponse[ExplainabilityResult]:
    result = await service.get_result(str(request_id))
    return build_success_response(result, request)
