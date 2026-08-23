"""Health & readiness endpoints — `GET /health`, `GET /ready`.

Every handler here calls only `app.operations.health.HealthCheckService`
(Sprint 54), already constructed by bootstrap and resolved via
dependency injection — no health/readiness logic is duplicated here.

`get_health` (Sprint 59) additionally publishes a `HEALTH_STATUS_CHANGED`
real-time event whenever the computed `state` differs from the last call
— tracked in `request.app.state.last_health_state`, pure bookkeeping, not
a background job: the check only ever runs in response to a real inbound
`GET /health` request, never on a timer.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.v1.dependencies.state import get_health_check_service, get_repositories_map, get_services_map
from app.api.v1.schemas.common import SuccessResponse, build_success_response
from app.api.ws.publishers.event_publisher import EventPublisher
from app.operations.health.models import ApplicationHealth, ReadinessStatus
from app.operations.health.service import HealthCheckService

__all__ = ["router"]

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=SuccessResponse[ApplicationHealth],
    summary="Application health",
    description=(
        "Aggregate health of every backend repository and service, reusing each "
        "repository's own `health_check()` — never recomputed here."
    ),
    responses={
        200: {
            "description": "Aggregate health computed successfully (the application "
            "itself may still report an UNHEALTHY/DEGRADED component within the body)."
        }
    },
)
async def get_health(
    request: Request,
    health_service: HealthCheckService = Depends(get_health_check_service),
    repositories: dict[str, Any] = Depends(get_repositories_map),
    services: dict[str, object | None] = Depends(get_services_map),
) -> SuccessResponse[ApplicationHealth]:
    health = await health_service.check_application(repositories, services)

    # Best-effort only: a health probe must never fail or slow down
    # because the (optional) real-time event framework isn't configured
    # — unlike every other publish call, this does not use
    # `Depends(get_event_publisher)`, which would 503 the whole endpoint.
    event_publisher: EventPublisher | None = getattr(request.app.state, "event_publisher", None)
    if event_publisher is not None:
        last_state = getattr(request.app.state, "last_health_state", None)
        if last_state != health.state:
            request.app.state.last_health_state = health.state
            await event_publisher.publish_health_status_changed(health)

    return build_success_response(health, request)


@router.get(
    "/ready",
    response_model=SuccessResponse[ReadinessStatus],
    summary="Readiness",
    description=(
        "Whether this application instance is ready to serve traffic. Returns HTTP 503 "
        "(with `data.ready=false` and `data.blocking_issues` populated in the body) when "
        "any required repository or service is unhealthy — the conventional readiness-probe "
        "contract most orchestrators/load balancers expect."
    ),
    responses={
        200: {"description": "Ready to serve traffic."},
        503: {"description": "Not ready — see `data.blocking_issues`."},
    },
)
async def get_ready(
    request: Request,
    response: Response,
    health_service: HealthCheckService = Depends(get_health_check_service),
    repositories: dict[str, Any] = Depends(get_repositories_map),
    services: dict[str, object | None] = Depends(get_services_map),
) -> SuccessResponse[ReadinessStatus]:
    readiness = await health_service.check_readiness(repositories, services)
    if not readiness.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return build_success_response(readiness, request)
