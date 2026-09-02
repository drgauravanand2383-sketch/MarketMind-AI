"""Version endpoint — `GET /version`.

Reports static version identifiers and the deployed environment. No
computation, no external call — every field is a constant or a single
already-loaded settings value.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.v1.dependencies.state import get_app_settings
from app.api.v1.schemas.common import SuccessResponse, build_success_response
from app.api.v1.schemas.system import VersionResponse
from app.bootstrap import AppSettings

__all__ = ["router", "API_VERSION", "APPLICATION_VERSION"]

router = APIRouter(tags=["System"])

API_VERSION = "v1"
# Kept in sync with `backend/pyproject.toml`'s own `[project].version`.
APPLICATION_VERSION = "1.2.3"


@router.get(
    "/version",
    response_model=SuccessResponse[VersionResponse],
    summary="API and application version",
    description="Static version identifiers for this API and the deployed application.",
)
async def get_version(
    request: Request, settings: AppSettings = Depends(get_app_settings)
) -> SuccessResponse[VersionResponse]:
    payload = VersionResponse(
        api_version=API_VERSION, application_version=APPLICATION_VERSION, environment=settings.environment
    )
    return build_success_response(payload, request)
