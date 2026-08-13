"""Request logging middleware.

Logs one structured event per completed request (method, path, status
code, request id) through `app.state.structured_logger`
(`BaseStructuredLogger`, Sprint 54) — reused, never a second logging
implementation. A no-op when `structured_logger` isn't configured on the
application (e.g. a minimal test app that skips full bootstrap).
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.operations.logging.models import LogCategory

__all__ = ["RequestLoggingMiddleware"]


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        logger = getattr(request.app.state, "structured_logger", None)
        if logger is not None:
            logger.info(
                LogCategory.APPLICATION,
                "http_request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                request_id=getattr(request.state, "request_id", None),
            )

        return response
