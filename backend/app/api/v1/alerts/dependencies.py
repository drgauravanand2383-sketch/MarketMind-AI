"""FastAPI dependency provider for the Alert API — resolves `AlertService`
from `request.app.state`, the exact pattern
`app.api.v1.watchlists.dependencies` already established.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.alerts.engine import AlertService

__all__ = ["get_alert_service"]


def get_alert_service(request: Request) -> AlertService:
    service = getattr(request.app.state, "alert_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AlertService is not configured on this application instance.",
        )
    return service
