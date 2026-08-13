"""Registers every middleware this sprint defines, plus CORS, response
compression, (Sprint 56) authentication, and (Sprint 60) security
headers, on the application. Call once, from `app.main.create_app`.

`AuthenticationMiddleware` (`app.auth.middleware`) is owned by the
Authentication & Authorization Framework, not this package — this module
only imports and registers it, the same way it already reuses
`app.config.models.APISettings` rather than redefining CORS
configuration. It never rejects a request itself (see its own
docstring); registering it here does not change how any existing,
unprotected route behaves.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from app.api.v1.middleware.logging import RequestLoggingMiddleware
from app.api.v1.middleware.request_id import RequestIDMiddleware
from app.api.v1.middleware.security_headers import SecurityHeadersMiddleware
from app.api.v1.middleware.timing import TimingMiddleware
from app.auth.middleware import AuthenticationMiddleware
from app.config.models import APISettings, SecurityHeadersSettings

__all__ = ["register_middleware"]

_MINIMUM_COMPRESSION_SIZE_BYTES = 1024


def register_middleware(
    app: FastAPI,
    *,
    api_settings: APISettings | None = None,
    security_headers_settings: SecurityHeadersSettings | None = None,
) -> None:
    settings = api_settings or APISettings()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=_MINIMUM_COMPRESSION_SIZE_BYTES)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(TimingMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, settings=security_headers_settings or SecurityHeadersSettings())
    app.add_middleware(AuthenticationMiddleware)
