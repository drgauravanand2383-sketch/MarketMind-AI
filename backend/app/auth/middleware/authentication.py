"""AuthenticationMiddleware: resolves an inbound bearer token,
authenticates the request, and attaches the result to
`request.state.principal`.

Deliberately does *not* authorize — a missing, malformed, expired, or
otherwise invalid token leaves `request.state.principal = None` and the
request proceeds; it is never rejected here. Authorization is strictly
policy-based (`app.auth.policies`), applied wherever a specific route or
capability actually requires it — this middleware's only job is
resolving *who, if anyone, is making this request*, once, before
anything downstream needs to ask.

Depends only on `app.auth.services.authentication.AuthenticationService`
(read from `request.app.state.authentication_service`) — never a
concrete provider — keeping this middleware provider-agnostic exactly
like the service it calls. A `None` service (not configured on this
application instance) degrades to the same "no principal" outcome as a
missing header, never a 500.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.auth.exceptions import TokenError
from app.auth.models.authentication import AuthenticatedPrincipal

__all__ = ["AuthenticationMiddleware", "BEARER_PREFIX"]

BEARER_PREFIX = "Bearer "


class AuthenticationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.principal = await self._resolve_principal(request)
        return await call_next(request)

    async def _resolve_principal(self, request: Request) -> AuthenticatedPrincipal | None:
        authorization_header = request.headers.get("Authorization")
        if not authorization_header or not authorization_header.startswith(BEARER_PREFIX):
            return None

        authentication_service = getattr(request.app.state, "authentication_service", None)
        if authentication_service is None:
            return None

        token = authorization_header[len(BEARER_PREFIX) :].strip()
        if not token:
            return None

        try:
            return await authentication_service.validate(token)
        except TokenError:
            return None
