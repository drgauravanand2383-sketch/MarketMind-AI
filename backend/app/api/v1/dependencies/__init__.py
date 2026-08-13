"""FastAPI dependency providers for the `/api/v1` REST API. Every
provider resolves an already-configured component from `request.app
.state` — nothing here constructs a repository, service, or provider."""

from app.api.v1.dependencies.state import (
    REPOSITORY_NAMES,
    SERVICE_NAMES,
    get_app_settings,
    get_configuration_validation_service,
    get_health_check_service,
    get_repositories_map,
    get_services_map,
    get_startup_validation_service,
)

__all__ = [
    "REPOSITORY_NAMES",
    "SERVICE_NAMES",
    "get_app_settings",
    "get_health_check_service",
    "get_configuration_validation_service",
    "get_startup_validation_service",
    "get_repositories_map",
    "get_services_map",
]
