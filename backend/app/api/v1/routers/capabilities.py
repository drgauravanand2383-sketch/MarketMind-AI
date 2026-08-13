"""Capabilities endpoint — `GET /capabilities`.

A coarse-grained feature-flag view: which major backend capability areas
this deployment currently supports. Every investment-engine flag is
derived from whether bootstrap actually constructed that engine's
service — never inferred or guessed. Capabilities this codebase does not
implement (per every explicit constraint from Sprint 44 onward) are
always `False`, never a placeholder implying partial support.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.v1.dependencies.state import get_services_map
from app.api.v1.schemas.common import SuccessResponse, build_success_response
from app.api.v1.schemas.system import CapabilitiesResponse

__all__ = ["router"]

router = APIRouter(tags=["System"])

_SERVICE_TO_CAPABILITY: tuple[tuple[str, str], ...] = (
    ("watchlist_service", "watchlist"),
    ("screening_engine", "screening"),
    ("signal_detection_service", "signal_detection"),
    ("alert_service", "alerts"),
    ("recommendation_service", "recommendations"),
    ("strategy_service", "strategy_evaluation"),
    ("risk_service", "risk_analytics"),
    ("backtesting_service", "backtesting"),
    ("explainability_service", "explainability"),
)

# Never implemented in this codebase, by explicit constraint in every
# sprint from 44 through 55 — always reported unavailable.
_ALWAYS_UNAVAILABLE: tuple[str, ...] = (
    "live_market_data",
    "broker_integration",
    "notifications",
    "authentication",
)


@router.get(
    "/capabilities",
    response_model=SuccessResponse[CapabilitiesResponse],
    summary="Backend capability flags",
    description="Which major backend capability areas this deployment currently supports.",
)
async def get_capabilities(
    request: Request, services: dict = Depends(get_services_map)
) -> SuccessResponse[CapabilitiesResponse]:
    capabilities: dict[str, bool] = {
        capability: services.get(service_name) is not None
        for service_name, capability in _SERVICE_TO_CAPABILITY
    }
    capabilities.update({name: False for name in _ALWAYS_UNAVAILABLE})
    return build_success_response(CapabilitiesResponse(capabilities=capabilities), request)
