"""FastAPI dependency providers for the Signal Detection API — resolves
`SignalDetectionService` from `request.app.state`, plus the thin
in-process result cache backing `GET /signals/results/{result_id}`.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.api.v1.schemas.result_store import InMemoryResultStore
from app.signals.engine import SignalDetectionService
from app.signals.models import SignalBatchResult

__all__ = ["get_signal_detection_service", "get_signal_result_store"]


def get_signal_detection_service(request: Request) -> SignalDetectionService:
    service = getattr(request.app.state, "signal_detection_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SignalDetectionService is not configured on this application instance.",
        )
    return service


def get_signal_result_store(request: Request) -> InMemoryResultStore[tuple[str, SignalBatchResult]]:
    store = getattr(request.app.state, "signal_result_store", None)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The signal result store is not configured on this application instance.",
        )
    return store
