"""Middleware for the `/api/v1` REST API: Request ID, Timing, structured
request logging, CORS, and response compression. No authentication
middleware — explicitly out of scope for this sprint."""

from app.api.v1.middleware.logging import RequestLoggingMiddleware
from app.api.v1.middleware.registration import register_middleware
from app.api.v1.middleware.request_id import REQUEST_ID_HEADER, RequestIDMiddleware
from app.api.v1.middleware.timing import PROCESS_TIME_HEADER, TimingMiddleware

__all__ = [
    "register_middleware",
    "RequestIDMiddleware",
    "REQUEST_ID_HEADER",
    "TimingMiddleware",
    "PROCESS_TIME_HEADER",
    "RequestLoggingMiddleware",
]
