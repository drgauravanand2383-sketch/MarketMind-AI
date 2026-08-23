"""FastAPI dependency providers for the Signal Detection API — resolves
`SignalDetectionService` from `request.app.state`, plus the thin
in-process result cache backing `GET /signals/results/{result_id}`.
"""

from __future__ import annotations

from fastapi import Request

from app.api.dependencies.state import resolve_app_state
from app.api.v1.schemas.result_store import InMemoryResultStore
from app.signals.engine import SignalDetectionService
from app.signals.models import SignalBatchResult

__all__ = ["get_signal_detection_service", "get_signal_result_store"]


def get_signal_detection_service(request: Request) -> SignalDetectionService:
    return resolve_app_state(
        request, "signal_detection_service", SignalDetectionService, label="SignalDetectionService"
    )


def get_signal_result_store(request: Request) -> InMemoryResultStore[tuple[str, SignalBatchResult]]:
    return resolve_app_state(
        request,
        "signal_result_store",
        InMemoryResultStore[tuple[str, SignalBatchResult]],
        label="The signal result store",
    )
