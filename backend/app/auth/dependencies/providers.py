"""FastAPI dependency providers for the Authentication & Authorization
Framework — resolves already-configured components from `request.app
.state`, the exact pattern `app.api.intelligence.dependencies` and
`app.api.v1.dependencies.state` already established. Nothing here
constructs a service; every provider only wires an already-built
component to a caller. `app/api/` consumes these directly (`Depends(...)`)
rather than duplicating them — "Authentication must remain independent
from the API layer" means the *logic* lives here, not that the API layer
reimplements its own lookup.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.auth.models.authentication import AuthenticatedPrincipal
from app.auth.policies.evaluator import PolicyEvaluator
from app.auth.services.authentication import AuthenticationService
from app.auth.services.authorization import AuthorizationService

__all__ = [
    "get_authentication_service",
    "get_authorization_service",
    "get_policy_evaluator",
    "get_current_principal",
]


def _resolve(request: Request, name: str, *, label: str) -> object:
    component = getattr(request.app.state, name, None)
    if component is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{label} is not configured on this application instance.",
        )
    return component


def get_authentication_service(request: Request) -> AuthenticationService:
    return _resolve(request, "authentication_service", label="AuthenticationService")  # type: ignore[return-value]


def get_authorization_service(request: Request) -> AuthorizationService:
    return _resolve(request, "authorization_service", label="AuthorizationService")  # type: ignore[return-value]


def get_policy_evaluator(request: Request) -> PolicyEvaluator:
    return _resolve(request, "policy_evaluator", label="PolicyEvaluator")  # type: ignore[return-value]


def get_current_principal(request: Request) -> AuthenticatedPrincipal | None:
    """The principal `AuthenticationMiddleware` resolved for this
    request, or `None` if unauthenticated (no token, an invalid token, or
    the middleware isn't installed) — never raises; a missing principal
    is a normal, expected outcome, not a misconfiguration."""
    return getattr(request.state, "principal", None)
