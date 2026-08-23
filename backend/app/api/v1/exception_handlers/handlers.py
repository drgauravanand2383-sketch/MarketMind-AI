"""Centralized exception handling — converts domain exceptions and
framework-level errors into one consistent HTTP response format
(`ErrorResponse`/`ValidationErrorResponse`, `app.api.v1.schemas.common`).

Four handler functions, registered once each in `register_exception_handlers`:

- `handle_http_exception` — `StarletteHTTPException` (covers every
  `HTTPException` raised anywhere, e.g. the 503s in
  `app.api.v1.dependencies.state`, plus FastAPI/Starlette's own 404 for
  an unknown route and 405 for an unsupported method).
- `handle_validation_error` — `RequestValidationError` (a request body/
  query/path parameter failed schema validation) -> 422.
- `handle_domain_error` — registered once per domain package's own base
  exception class (`RiskAnalyticsError`, `BacktestingError`,
  `ExplainabilityError`, `RecommendationEngineError`, `StrategyEngineError`,
  `ScreeningError`, `SignalError`, `AlertEngineError`,
  `WatchlistServiceError`). No sprint-44-through-53 engine's own
  exception hierarchy is modified or re-derived to share a base class —
  this handler is registered against each package's already-existing
  base independently, and infers an HTTP status from the concrete
  exception class's own name (a convention already consistent across
  every one of these packages: a `*NotFoundError` subclass -> 404, a
  `Duplicate*Error` subclass -> 409, anything else -> 400) rather than
  hand-mapping every individual subclass.
- `handle_unhandled_exception` — the last-resort catch-all for anything
  else -> 500, logged via the structured logger (Sprint 54) before
  responding, and never leaks the raw exception message to the client.

`app.api.v1.schemas.result_store.ResultNotFoundError` (Sprint 58) is
registered separately, below `_DOMAIN_ERROR_BASE_CLASSES` — it is an
API-layer-only lookup-miss for `InMemoryResultStore`, not a domain
package's own exception, so it is kept out of that tuple to leave the
"nine domain exception base classes" invariant accurate; it shares
`handle_domain_error` purely for a consistent `*NotFoundError` -> 404
response shape.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.alerts.exceptions import AlertEngineError
from app.api.v1.schemas.common import (
    ErrorResponse,
    ValidationErrorFieldError,
    ValidationErrorResponse,
    build_metadata,
    request_id_of,
)
from app.api.v1.schemas.result_store import ResultNotFoundError
from app.backtesting.exceptions import BacktestingError
from app.explainability.exceptions import ExplainabilityError
from app.operations.logging.logger import BaseStructuredLogger
from app.operations.logging.models import LogCategory
from app.recommendations.exceptions import RecommendationEngineError
from app.risk.exceptions import RiskAnalyticsError
from app.screening.exceptions import ScreeningError
from app.signals.exceptions import SignalError
from app.strategy.exceptions import StrategyEngineError
from app.watchlist.exceptions import WatchlistServiceError

__all__ = ["register_exception_handlers"]

# Registered once each, all pointing at the same `handle_domain_error`.
_DOMAIN_ERROR_BASE_CLASSES: tuple[type[Exception], ...] = (
    AlertEngineError,
    BacktestingError,
    ExplainabilityError,
    RecommendationEngineError,
    RiskAnalyticsError,
    ScreeningError,
    SignalError,
    StrategyEngineError,
    WatchlistServiceError,
)


def _structured_logger(request: Request) -> BaseStructuredLogger | None:
    return getattr(request.app.state, "structured_logger", None)


def _error_response(request: Request, *, status_code: int, error: str, message: str) -> JSONResponse:
    body = ErrorResponse(error=error, message=message, meta=build_metadata(request_id_of(request)))
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Covers every raised `HTTPException` plus FastAPI/Starlette's own
    404 (unknown route) and 405 (unsupported method)."""
    error_code = {
        status.HTTP_404_NOT_FOUND: "not_found",
        status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
        status.HTTP_503_SERVICE_UNAVAILABLE: "service_unavailable",
    }.get(exc.status_code, "http_error")
    return _error_response(request, status_code=exc.status_code, error=error_code, message=str(exc.detail))


async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = tuple(
        ValidationErrorFieldError(
            location=tuple(str(part) for part in error["loc"]), message=error["msg"], type=error["type"]
        )
        for error in exc.errors()
    )
    body = ValidationErrorResponse(details=details, meta=build_metadata(request_id_of(request)))
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=body.model_dump(mode="json"))


def _infer_status_code(exc: Exception) -> int:
    name = type(exc).__name__
    if name.endswith("NotFoundError"):
        return status.HTTP_404_NOT_FOUND
    if name.startswith("Duplicate") or "AlreadyExists" in name or "AlreadyRegistered" in name:
        return status.HTTP_409_CONFLICT
    return status.HTTP_400_BAD_REQUEST


async def handle_domain_error(request: Request, exc: Exception) -> JSONResponse:
    status_code = _infer_status_code(exc)
    error_code = {
        status.HTTP_404_NOT_FOUND: "not_found",
        status.HTTP_409_CONFLICT: "conflict",
    }.get(status_code, "domain_error")
    return _error_response(request, status_code=status_code, error=error_code, message=str(exc))


async def handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    logger = _structured_logger(request)
    if logger is not None:
        logger.error(
            LogCategory.APPLICATION,
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            exception_type=type(exc).__name__,
        )
    return _error_response(
        request,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error="internal_error",
        message="An unexpected error occurred.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register every handler above on `app`. Call once, from `app.main.create_app`."""
    # Starlette's own `add_exception_handler` stub types the handler
    # parameter as accepting the base `Exception` regardless of which
    # exception class is registered against — real runtime dispatch only
    # ever calls a registered handler with an instance of its own
    # registered class, so narrowing `exc` to `StarletteHTTPException`/
    # `RequestValidationError` here is correct and deliberate, not a bug.
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, handle_validation_error)  # type: ignore[arg-type]
    for exception_class in _DOMAIN_ERROR_BASE_CLASSES:
        app.add_exception_handler(exception_class, handle_domain_error)
    app.add_exception_handler(ResultNotFoundError, handle_domain_error)
    app.add_exception_handler(Exception, handle_unhandled_exception)
