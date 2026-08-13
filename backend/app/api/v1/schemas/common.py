"""Shared HTTP-layer response envelopes for the `/api/v1` REST API.

Every successful `/api/v1` response is wrapped in `SuccessResponse[T]`;
every error response (raised `HTTPException`, an unhandled domain
exception, or a request validation failure) is wrapped in `ErrorResponse`
or `ValidationErrorResponse` — see
`app.api.v1.exception_handlers.handlers`. This is the "consistent
response format" this sprint's own Response Models section asks for: one
envelope shape for success, one (two, for the validation-specific case)
for failure, used everywhere in this API.

No business logic lives here — these are pure HTTP-layer presentation
models, independent of every domain package's own Pydantic models.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Generic, TypeVar

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "MetadataResponse",
    "SuccessResponse",
    "ErrorResponse",
    "ValidationErrorResponse",
    "PaginatedResponse",
]

T = TypeVar("T")

API_VERSION = "v1"


class MetadataResponse(BaseModel):
    """Per-request metadata attached to every `/api/v1` response envelope."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    timestamp: datetime
    api_version: str = API_VERSION


class SuccessResponse(BaseModel, Generic[T]):
    """The envelope for every successful `/api/v1` response."""

    model_config = ConfigDict(extra="forbid")

    data: T
    meta: MetadataResponse


class ErrorResponse(BaseModel):
    """The envelope for every error `/api/v1` response — an
    `HTTPException`, an unhandled domain exception, or an internal error.
    `error` is a short, stable machine-readable code (e.g.
    `"not_found"`, `"internal_error"`); `message` is the human-readable
    detail."""

    model_config = ConfigDict(extra="forbid")

    error: str
    message: str
    meta: MetadataResponse


class ValidationErrorFieldError(BaseModel):
    """One field-level validation failure, as reported by FastAPI's own
    `RequestValidationError` (itself built from pydantic's error list)."""

    model_config = ConfigDict(extra="forbid")

    location: tuple[str | int, ...]
    message: str
    type: str


class ValidationErrorResponse(BaseModel):
    """The envelope for a request that failed schema validation (HTTP 422)."""

    model_config = ConfigDict(extra="forbid")

    error: str = "validation_error"
    message: str = "Request validation failed."
    details: tuple[ValidationErrorFieldError, ...] = Field(default_factory=tuple)
    meta: MetadataResponse


class PaginatedResponse(BaseModel, Generic[T]):
    """The envelope for a paginated `/api/v1` list response. No endpoint
    in this sprint returns a paginated list yet (every Sprint 55 endpoint
    is a single-object status/introspection response) — this exists as
    forward-looking, ready-to-use infrastructure for the list endpoints a
    future sprint adds (this sprint's own "Future versions must be
    extensible" requirement)."""

    model_config = ConfigDict(extra="forbid")

    data: tuple[T, ...]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    meta: MetadataResponse


def build_metadata(request_id: str, *, now: datetime | None = None) -> MetadataResponse:
    return MetadataResponse(request_id=request_id, timestamp=now or datetime.now(timezone.utc))


def request_id_of(request: Request) -> str:
    """The current request's id, as set by `RequestIDMiddleware`. Falls
    back to a freshly generated id if the middleware isn't installed
    (e.g. a handler exercised directly in a unit test without the full
    middleware stack) — every response still gets a valid, unique id."""
    return getattr(request.state, "request_id", None) or str(uuid.uuid4())


def build_success_response(data: T, request: Request) -> SuccessResponse[T]:
    """Wrap `data` in the standard `SuccessResponse` envelope, populating
    `meta` from the current request."""
    return SuccessResponse(data=data, meta=build_metadata(request_id_of(request)))
