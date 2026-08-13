"""FastAPI dependency providers for the Screening API — resolves
`ScreeningEngine` from `request.app.state`, plus the thin in-process
result cache backing `GET /screening/results/{result_id}`.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.api.v1.schemas.result_store import InMemoryResultStore
from app.screening.engine import ScreeningEngine
from app.screening.models import ScreenResult

__all__ = ["get_screening_engine", "get_screening_result_store"]


def get_screening_engine(request: Request) -> ScreeningEngine:
    engine = getattr(request.app.state, "screening_engine", None)
    if engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ScreeningEngine is not configured on this application instance.",
        )
    return engine


def get_screening_result_store(request: Request) -> InMemoryResultStore[tuple[str, list[ScreenResult]]]:
    store = getattr(request.app.state, "screening_result_store", None)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The screening result store is not configured on this application instance.",
        )
    return store
