"""FastAPI router for the Alert API (`/api/v1/alerts`).

Every handler is a thin translation: resolve `AlertService` via
dependency injection, call exactly one of its existing methods, wrap the
result. `AlertEngineError` subclasses (`AlertNotFoundError`,
`AlertRuleNotFoundError`) are never caught here; they propagate to the
centralized domain-exception handler already registered in Sprint 55/56.

Literal-path `/evaluate` is registered before `/{alert_id}` — see
`app/api/v1/portfolio/router.py`'s own docstring for why registration
order matters to FastAPI's route matching.

`evaluate_alerts` (Sprint 59) additionally publishes an `ALERT_GENERATED`
real-time event for each newly generated alert, via `EventPublisher` —
this is the only trigger point for that event type, since publishing is
never done from a background job (see `app.api.ws`'s own docstring).
"""

from __future__ import annotations

import uuid as uuid_module

from fastapi import APIRouter, Depends, Request, status

from app.alerts.engine import AlertService
from app.alerts.models import Alert, AlertBatch, AlertStatus
from app.api.v1.alerts.dependencies import get_alert_service
from app.api.v1.alerts.schemas import EvaluateAlertsRequest
from app.api.v1.schemas.common import PaginatedResponse, SuccessResponse, build_success_response
from app.api.v1.schemas.pagination import PaginationParams, build_paginated_response, paginate_items, pagination_params
from app.api.ws.dependencies.services import get_event_publisher
from app.api.ws.publishers.event_publisher import EventPublisher
from app.auth.dependencies.policy_guard import require_policy
from app.auth.policies import RequirePermission

__all__ = ["router"]

router = APIRouter(prefix="/alerts", tags=["Alerts"])

_SORTABLE_FIELDS = frozenset({"created_at", "priority", "status", "ticker"})


@router.get(
    "",
    response_model=PaginatedResponse[Alert],
    summary="List alerts",
    description="Paginated, sortable list of every generated alert.",
    dependencies=[Depends(require_policy(RequirePermission("alerts:read")))],
)
async def list_alerts(
    request: Request,
    pagination: PaginationParams = Depends(pagination_params),
    service: AlertService = Depends(get_alert_service),
) -> PaginatedResponse[Alert]:
    alerts = await service.list_alerts()
    page_items, total = paginate_items(alerts, pagination, sortable_fields=_SORTABLE_FIELDS)
    return build_paginated_response(page_items, total, pagination, request)


@router.post(
    "/evaluate",
    response_model=SuccessResponse[AlertBatch],
    status_code=status.HTTP_201_CREATED,
    summary="Evaluate signals against alert rules",
    description="Evaluates every supplied SignalResult against `rule_ids` (or every enabled rule, if empty).",
    dependencies=[Depends(require_policy(RequirePermission("alerts:evaluate")))],
)
async def evaluate_alerts(
    request: Request,
    body: EvaluateAlertsRequest,
    service: AlertService = Depends(get_alert_service),
    event_publisher: EventPublisher = Depends(get_event_publisher),
) -> SuccessResponse[AlertBatch]:
    if body.rule_ids:
        rules = [await service.get_rule(rule_id) for rule_id in body.rule_ids]
    else:
        rules = await service.list_rules()
    batch = await service.evaluate_batch(body.signals, rules)
    for alert in batch.alerts:
        if alert.status == AlertStatus.GENERATED:
            await event_publisher.publish_alert_generated(alert)
    return build_success_response(batch, request)


@router.get(
    "/{alert_id}",
    response_model=SuccessResponse[Alert],
    summary="Get an alert",
    description="Fetch a single previously generated alert by id.",
    dependencies=[Depends(require_policy(RequirePermission("alerts:read")))],
)
async def get_alert(
    request: Request,
    alert_id: uuid_module.UUID,
    service: AlertService = Depends(get_alert_service),
) -> SuccessResponse[Alert]:
    alert = await service.get_alert(str(alert_id))
    return build_success_response(alert, request)
