"""Individual `/api/v1` sub-routers, one module per functional area.
Aggregated into a single router by `app.api.v1.router`."""

from app.api.v1.routers.capabilities import router as capabilities_router
from app.api.v1.routers.configuration import router as configuration_router
from app.api.v1.routers.health import router as health_router
from app.api.v1.routers.services import router as services_router
from app.api.v1.routers.version import router as version_router

__all__ = [
    "health_router",
    "version_router",
    "configuration_router",
    "capabilities_router",
    "services_router",
]
