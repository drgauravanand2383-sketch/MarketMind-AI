"""The `/api/v1` aggregate router — includes every Sprint 55-60
sub-router, plus (Frontend Milestone 1) `app.api.v1.auth`, the first REST
exposure of the Authentication & Authorization Framework (Sprint 56)
built specifically because no login/refresh/logout endpoint existed
anywhere before it — a purely additive, non-breaking addition per
`docs/release/API_VERSIONING_POLICY.md`. Future versions (`/api/v2`, ...)
are a sibling package (`app.api.v2.router`), never a modification of this
one.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.alerts import router as alerts_router
from app.api.v1.auth import router as auth_router
from app.api.v1.backtests import router as backtests_router
from app.api.v1.explainability import router as explainability_router
from app.api.v1.portfolio import router as portfolio_router
from app.api.v1.research import router as research_router
from app.api.v1.routers.capabilities import router as capabilities_router
from app.api.v1.routers.configuration import router as configuration_router
from app.api.v1.routers.health import router as health_router
from app.api.v1.routers.services import router as services_router
from app.api.v1.routers.version import router as version_router
from app.api.v1.screening import router as screening_router
from app.api.v1.signals import router as signals_router
from app.api.v1.strategies import router as strategies_router
from app.api.v1.watchlists import router as watchlists_router

__all__ = ["router"]

router = APIRouter()
router.include_router(auth_router)
router.include_router(health_router)
router.include_router(version_router)
router.include_router(configuration_router)
router.include_router(capabilities_router)
router.include_router(services_router)
router.include_router(watchlists_router)
router.include_router(portfolio_router)
router.include_router(research_router)
router.include_router(screening_router)
router.include_router(signals_router)
router.include_router(alerts_router)
router.include_router(strategies_router)
router.include_router(backtests_router)
router.include_router(explainability_router)
