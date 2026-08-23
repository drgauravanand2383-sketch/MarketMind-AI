"""FastAPI dependency provider for the Alert API — resolves `AlertService`
from `request.app.state`, the exact pattern
`app.api.v1.watchlists.dependencies` already established.
"""

from __future__ import annotations

from fastapi import Request

from app.alerts.engine import AlertService
from app.api.dependencies.state import resolve_app_state

__all__ = ["get_alert_service"]


def get_alert_service(request: Request) -> AlertService:
    return resolve_app_state(request, "alert_service", AlertService, label="AlertService")
