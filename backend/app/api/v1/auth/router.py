"""FastAPI router for the Auth API (`/api/v1/auth`).

Exposes the already-built `AuthenticationService` (Sprint 56) over REST
for the first time — identified as a genuine gap while building the
frontend's Milestone 1 ("consume the existing JWT API"): the framework
existed, but no REST endpoint ever called it. Every handler is a thin
translation: resolve `AuthenticationService` via dependency injection,
call exactly one of its existing methods, wrap the result. No new
authentication logic.

**Deliberately unlike every other `/api/v1` router**, authentication
failures are caught explicitly here rather than left to the centralized
`handle_domain_error` — `AuthError` is intentionally *not* registered in
that handler's base-class tuple. `handle_domain_error`'s naming-convention
status inference (`*NotFoundError` -> 404, `Duplicate*` -> 409, else ->
400) was designed for domain validation errors; `InvalidCredentialsError`/
`UserNotActiveError`/`TokenError` are authentication failures, which are
semantically `401` — a distinction the shared convention doesn't make.
Catching them here keeps that shared, frozen infrastructure
(`app.api.v1.exception_handlers.handlers`) completely untouched.

No registration/role-management endpoint is exposed here — out of scope
for what the frontend's first milestone needs (login/refresh/logout).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.v1.auth.schemas import LogoutRequest, RefreshTokenRequest
from app.api.v1.schemas.common import SuccessResponse, build_success_response
from app.auth.dependencies.policy_guard import require_policy
from app.auth.dependencies.providers import get_authentication_service
from app.auth.exceptions import InvalidCredentialsError, TokenError, UserNotActiveError
from app.auth.models.authentication import AuthenticationRequest, AuthenticationResponse
from app.auth.policies import RequireAuthenticated
from app.auth.services.authentication import AuthenticationService

__all__ = ["router"]

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/login",
    response_model=SuccessResponse[AuthenticationResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Log in",
    description="Exchange a username/email and password for an access/refresh token pair.",
)
async def login(
    request: Request,
    body: AuthenticationRequest,
    auth_service: AuthenticationService = Depends(get_authentication_service),
) -> SuccessResponse[AuthenticationResponse]:
    try:
        result = await auth_service.authenticate(body.username, body.password)
    except (InvalidCredentialsError, UserNotActiveError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return build_success_response(result, request)


@router.post(
    "/refresh",
    response_model=SuccessResponse[AuthenticationResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Refresh an access token",
    description="Exchange a still-valid refresh token for a fresh access/refresh token pair.",
)
async def refresh(
    request: Request,
    body: RefreshTokenRequest,
    auth_service: AuthenticationService = Depends(get_authentication_service),
) -> SuccessResponse[AuthenticationResponse]:
    try:
        result = await auth_service.refresh(body.refresh_token)
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return build_success_response(result, request)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Log out",
    description="Revoke a refresh token, ending that session. The still-valid access token is "
    "short-lived and simply expires — see this router's own module docstring.",
    dependencies=[Depends(require_policy(RequireAuthenticated()))],
)
async def logout(
    body: LogoutRequest,
    auth_service: AuthenticationService = Depends(get_authentication_service),
) -> None:
    try:
        await auth_service.revoke(body.refresh_token)
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
