"""FastAPI dependency providers resolving already-configured components
from `request.app.state` — the exact same pattern
`app.api.intelligence.dependencies` already established: every provider
here resolves a component `app.bootstrap.bootstrap_application_state`
already constructed, raising 503 if it isn't configured on this
application instance. No component is ever constructed here — this
module only wires already-built components to HTTP handlers.

`resolve_app_state` itself lives in `app.api.dependencies.state`, not
here — see that module's own docstring for why (importing anything under
`app.api.v1.*` triggers `app/api/v1/__init__.py`'s eager import of the
entire `/api/v1` router tree, which several other callers of
`resolve_app_state` outside this package cannot safely trigger as a side
effect of their own imports). Re-exported here anyway so existing
`from app.api.v1.dependencies.state import resolve_app_state` references
(if any remain) keep working.

`get_repositories_map`/`get_services_map` enumerate the same
repository/service `app.state` attribute names
`app.operations.validation.startup.DEFAULT_REQUIRED_COMPONENTS` already
names (Sprint 54) — reused as the two constant tuples below rather than
re-derived by string-matching attribute names, which would be more
fragile for no benefit.
"""

from __future__ import annotations

from fastapi import Request

from app.api.dependencies.state import resolve_app_state
from app.bootstrap import AppSettings
from app.operations.health.service import HealthCheckService
from app.operations.validation.configuration import ConfigurationValidationService
from app.operations.validation.startup import StartupValidationService

__all__ = [
    "REPOSITORY_NAMES",
    "SERVICE_NAMES",
    "resolve_app_state",
    "get_app_settings",
    "get_health_check_service",
    "get_configuration_validation_service",
    "get_startup_validation_service",
    "get_repositories_map",
    "get_services_map",
]

REPOSITORY_NAMES: tuple[str, ...] = (
    "watchlist_repository",
    "screening_repository",
    "signal_repository",
    "alert_rule_repository",
    "alert_repository",
    "recommendation_repository",
    "strategy_repository",
    "risk_repository",
    "backtesting_repository",
    "explainability_repository",
)

SERVICE_NAMES: tuple[str, ...] = (
    "watchlist_service",
    "screening_engine",
    "market_data_provider",
    "normalization_service",
    "signal_detection_service",
    "alert_service",
    "recommendation_service",
    "strategy_service",
    "risk_service",
    "backtesting_service",
    "explainability_service",
)


def get_app_settings(request: Request) -> AppSettings:
    """Resolve the shared `AppSettings` configured at application startup."""
    return resolve_app_state(request, "settings", AppSettings, label="AppSettings")


def get_health_check_service(request: Request) -> HealthCheckService:
    """Resolve the shared `HealthCheckService` (Sprint 54) configured at application startup."""
    return resolve_app_state(request, "health_check_service", HealthCheckService, label="HealthCheckService")


def get_configuration_validation_service(request: Request) -> ConfigurationValidationService:
    """Resolve the shared `ConfigurationValidationService` (Sprint 54) configured at application startup."""
    return resolve_app_state(
        request,
        "configuration_validation_service",
        ConfigurationValidationService,
        label="ConfigurationValidationService",
    )


def get_startup_validation_service(request: Request) -> StartupValidationService:
    """Resolve the shared `StartupValidationService` (Sprint 54) configured at application startup."""
    return resolve_app_state(
        request, "startup_validation_service", StartupValidationService, label="StartupValidationService"
    )


def get_repositories_map(request: Request) -> dict[str, object | None]:
    """Every repository `app.bootstrap` wires, by its `app.state` attribute name."""
    return {name: getattr(request.app.state, name, None) for name in REPOSITORY_NAMES}


def get_services_map(request: Request) -> dict[str, object | None]:
    """Every service `app.bootstrap` wires, by its `app.state` attribute name."""
    return {name: getattr(request.app.state, name, None) for name in SERVICE_NAMES}
