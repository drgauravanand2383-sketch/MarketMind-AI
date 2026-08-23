"""Services endpoint — `GET /services`.

A fine-grained service inventory: every service `app.bootstrap` wires,
and whether it was actually constructed. Reuses
`HealthCheckService.check_services()` (Sprint 54) directly — the exact
same construction-status check `/health` itself uses — rather than
duplicating that logic here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.v1.dependencies.state import get_health_check_service, get_services_map
from app.api.v1.schemas.common import SuccessResponse, build_success_response
from app.api.v1.schemas.system import ServiceEntry, ServicesResponse
from app.operations.health.models import HealthState
from app.operations.health.service import HealthCheckService

__all__ = ["router"]

router = APIRouter(tags=["System"])


@router.get(
    "/services",
    response_model=SuccessResponse[ServicesResponse],
    summary="Service inventory",
    description="Every backend service this deployment wires, and whether it was successfully constructed.",
)
async def get_services(
    request: Request,
    health_service: HealthCheckService = Depends(get_health_check_service),
    services: dict[str, object | None] = Depends(get_services_map),
) -> SuccessResponse[ServicesResponse]:
    service_health = health_service.check_services(services)
    entries = tuple(
        ServiceEntry(name=entry.name, available=entry.state == HealthState.HEALTHY) for entry in service_health
    )
    return build_success_response(ServicesResponse(services=entries), request)
