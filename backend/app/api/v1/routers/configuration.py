"""Configuration endpoint — `GET /configuration`.

Exposes only non-secret configuration — see `app.api.v1.schemas.system
.ConfigurationResponse`'s own docstring for exactly why no credential can
ever reach this endpoint. Every field is read directly from already-loaded
settings objects; nothing is computed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.v1.dependencies.state import get_app_settings
from app.api.v1.schemas.common import SuccessResponse, build_success_response
from app.api.v1.schemas.system import ConfigurationResponse
from app.bootstrap import AppSettings
from app.config.models import APISettings, SchedulerSettings

__all__ = ["router"]

router = APIRouter(tags=["System"])


@router.get(
    "/configuration",
    response_model=SuccessResponse[ConfigurationResponse],
    summary="Non-secret application configuration",
    description=(
        "Non-secret configuration values only — no credential-bearing settings section is ever read by this endpoint."
    ),
)
async def get_configuration(
    request: Request, settings: AppSettings = Depends(get_app_settings)
) -> SuccessResponse[ConfigurationResponse]:
    api_settings = APISettings()
    scheduler_settings = SchedulerSettings()
    payload = ConfigurationResponse(
        environment=settings.environment,
        log_level=settings.log_level,
        api_version_prefix=api_settings.v1_prefix,
        allowed_origins=tuple(api_settings.allowed_origins),
        watchlist_max_size=settings.watchlist_max_size,
        screening_max_filters=settings.screening_max_filters,
        signal_max_conditions=settings.signal_max_conditions,
        alert_max_rules=settings.alert_max_rules,
        scheduler_enabled=scheduler_settings.enabled,
        rss_feed_count=len(settings.rss_feed_urls),
    )
    return build_success_response(payload, request)
