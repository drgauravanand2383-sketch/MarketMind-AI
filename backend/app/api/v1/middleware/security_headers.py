"""Security headers middleware (Sprint 60).

Adds the standard defensive response headers to every response.
`Content-Security-Policy` and `Strict-Transport-Security` are
configurable and **disabled by default** — see
`app.config.models.SecurityHeadersSettings`'s own docstring for why a
blind default would break `/docs`/`/redoc` (CSP) or be actively wrong
over plain HTTP (HSTS, "do not assume HTTPS in development"). Every
other header here is safe to always send.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.config.models import SecurityHeadersSettings

__all__ = ["SecurityHeadersMiddleware"]


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, settings: SecurityHeadersSettings | None = None) -> None:
        super().__init__(app)
        self._settings = settings or SecurityHeadersSettings()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        response.headers.setdefault("X-Content-Type-Options", self._settings.x_content_type_options)
        response.headers.setdefault("X-Frame-Options", self._settings.x_frame_options)
        response.headers.setdefault("Referrer-Policy", self._settings.referrer_policy)
        response.headers.setdefault("Permissions-Policy", self._settings.permissions_policy)

        if self._settings.content_security_policy:
            response.headers.setdefault("Content-Security-Policy", self._settings.content_security_policy)

        if self._settings.hsts_enabled:
            directive = f"max-age={self._settings.hsts_max_age_seconds}"
            if self._settings.hsts_include_subdomains:
                directive += "; includeSubDomains"
            response.headers.setdefault("Strict-Transport-Security", directive)

        return response
