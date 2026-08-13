"""Timing middleware.

Measures wall-clock request duration and sets the `X-Process-Time`
response header (seconds, as a string). When
`app.state.metrics_recorder`/`app.state.profiler` (Sprint 54) are
configured on the application, also records the duration through them —
reused, not duplicated: this middleware never implements its own
metrics/profiling storage.
"""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.operations.metrics.models import METRIC_SERVICE_CALLS

__all__ = ["TimingMiddleware", "PROCESS_TIME_HEADER"]

PROCESS_TIME_HEADER = "X-Process-Time"


class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        started_at = time.perf_counter()
        response = await call_next(request)
        duration_seconds = time.perf_counter() - started_at
        response.headers[PROCESS_TIME_HEADER] = f"{duration_seconds:.6f}"

        profiler = getattr(request.app.state, "profiler", None)
        if profiler is not None:
            profiler.record(f"http.{request.method}.{request.url.path}", duration_seconds)

        metrics_recorder = getattr(request.app.state, "metrics_recorder", None)
        if metrics_recorder is not None:
            metrics_recorder.increment(
                METRIC_SERVICE_CALLS, method=request.method, path=request.url.path,
                status_code=str(response.status_code),
            )
            metrics_recorder.record_duration(
                "http_request_duration_seconds", duration_seconds, method=request.method, path=request.url.path,
            )

        return response
