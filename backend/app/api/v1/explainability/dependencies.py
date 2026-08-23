"""FastAPI dependency provider for the Explainability API — resolves
`ExplainabilityService` from `request.app.state`, the exact pattern
`app.api.v1.watchlists.dependencies` already established.
"""

from __future__ import annotations

from fastapi import Request

from app.api.dependencies.state import resolve_app_state
from app.explainability.engine import ExplainabilityService

__all__ = ["get_explainability_service"]


def get_explainability_service(request: Request) -> ExplainabilityService:
    return resolve_app_state(request, "explainability_service", ExplainabilityService, label="ExplainabilityService")
