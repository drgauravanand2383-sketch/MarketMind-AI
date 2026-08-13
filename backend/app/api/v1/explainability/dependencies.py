"""FastAPI dependency provider for the Explainability API — resolves
`ExplainabilityService` from `request.app.state`, the exact pattern
`app.api.v1.watchlists.dependencies` already established.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.explainability.engine import ExplainabilityService

__all__ = ["get_explainability_service"]


def get_explainability_service(request: Request) -> ExplainabilityService:
    service = getattr(request.app.state, "explainability_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ExplainabilityService is not configured on this application instance.",
        )
    return service
