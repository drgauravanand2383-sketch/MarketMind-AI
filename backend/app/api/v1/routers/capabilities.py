"""Capabilities endpoint — `GET /capabilities`.

A coarse-grained feature-flag view: which major backend capability areas
this deployment currently supports. Every investment-engine flag is
derived from whether bootstrap actually constructed that engine's
service — never inferred or guessed. Capabilities this codebase does not
implement (per every explicit constraint from Sprint 44 onward) are
always `False`, never a placeholder implying partial support.

`live_market_data` (Milestone 13): unlike the other three names in
`_ALWAYS_UNAVAILABLE`, this one is no longer permanently hardcoded false
— see `_live_market_data_available` below. `broker_integration`/
`notifications`/`authentication` remain exactly as before; this endpoint
is otherwise untouched.
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
    "broker_integration",
    "notifications",
    "authentication",
)


def _live_market_data_available(request: Request) -> bool:
    """Milestone 13: `True` only when a real (non-mock) MarketDataProvider
    was actually constructed at startup (`app.state.market_data_provider_is_live`,
    set by `app.bootstrap.build_market_data_provider`) — never merely
    "is *a* provider configured," since `market_data_provider` itself is
    always non-None (Mock or real). Missing entirely (e.g. `bare_client`
    fixtures that skip full bootstrap) reports `False`, the same
    fail-closed default every other capability flag already uses.
    """
    return bool(getattr(request.app.state, "market_data_provider_is_live", False))


@router.get(
    "/capabilities",
    response_model=SuccessResponse[CapabilitiesResponse],
    summary="Backend capability flags",
    description="Which major backend capability areas this deployment currently supports.",
)
async def get_capabilities(
    request: Request, services: dict[str, object | None] = Depends(get_services_map)
) -> SuccessResponse[CapabilitiesResponse]:
    capabilities: dict[str, bool] = {
        capability: services.get(service_name) is not None
        for service_name, capability in _SERVICE_TO_CAPABILITY
    }
    capabilities["live_market_data"] = _live_market_data_available(request)
    capabilities.update({name: False for name in _ALWAYS_UNAVAILABLE})
    return build_success_response(CapabilitiesResponse(capabilities=capabilities), request)
