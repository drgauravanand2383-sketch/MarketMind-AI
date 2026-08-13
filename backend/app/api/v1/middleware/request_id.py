"""Request ID middleware.

Reads an inbound `X-Request-ID` header if the caller supplied one
(useful for tracing a request across services), or generates a fresh
UUID otherwise. Sets `request.state.request_id` — read by
`app.api.v1.schemas.common.request_id_of` when building every response's
`MetadataResponse`, and by `TimingMiddleware`/`RequestLoggingMiddleware`
below — and echoes it back as the `X-Request-ID` response header.
"""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

__all__ = ["RequestIDMiddleware", "REQUEST_ID_HEADER"]

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
