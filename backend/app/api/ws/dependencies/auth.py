"""WebSocket authentication — reuses `AuthenticationService.validate()`
directly, the exact method `app.auth.middleware.AuthenticationMiddleware`
already calls for HTTP requests. Starlette's `BaseHTTPMiddleware` never
runs for a `websocket` ASGI scope, so this resolves the same way by hand
once, at connect time — no token-verification logic is duplicated.
"""

from __future__ import annotations

from fastapi import WebSocket

from app.auth.exceptions import TokenError
from app.auth.models.authentication import AuthenticatedPrincipal
from app.auth.services.authentication import AuthenticationService

__all__ = ["authenticate_websocket"]

_BEARER_PREFIX = "Bearer "


def _extract_token(websocket: WebSocket) -> str | None:
    authorization_header = websocket.headers.get("authorization")
    if authorization_header and authorization_header.startswith(_BEARER_PREFIX):
        token = authorization_header[len(_BEARER_PREFIX) :].strip()
        if token:
            return token
    token = websocket.query_params.get("token")
    return token or None


async def authenticate_websocket(
    websocket: WebSocket, authentication_service: AuthenticationService | None
) -> AuthenticatedPrincipal | None:
    """Resolve the principal for an inbound WebSocket connection from a
    bearer token — the `Authorization` header if present, else a `token`
    query parameter (browsers' native WebSocket API cannot set custom
    headers on the handshake, so a query parameter is the conventional
    fallback). Returns `None` for any failure (no token, malformed token,
    expired token, or no `AuthenticationService` configured) — never
    raises; the caller decides how to respond to an unauthenticated
    connection attempt.
    """
    if authentication_service is None:
        return None
    token = _extract_token(websocket)
    if token is None:
        return None
    try:
        return await authentication_service.validate(token)
    except TokenError:
        return None
