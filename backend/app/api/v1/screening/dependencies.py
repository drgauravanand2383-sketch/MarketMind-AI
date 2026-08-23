"""FastAPI dependency providers for the Screening API — resolves
`ScreeningEngine` from `request.app.state`, plus the thin in-process
result cache backing `GET /screening/results/{result_id}`.
"""

from __future__ import annotations

from fastapi import Request

from app.api.dependencies.state import resolve_app_state
from app.api.v1.schemas.result_store import InMemoryResultStore
from app.screening.engine import ScreeningEngine
from app.screening.models import ScreenResult

__all__ = ["get_screening_engine", "get_screening_result_store"]


def get_screening_engine(request: Request) -> ScreeningEngine:
    return resolve_app_state(request, "screening_engine", ScreeningEngine, label="ScreeningEngine")


def get_screening_result_store(request: Request) -> InMemoryResultStore[tuple[str, list[ScreenResult]]]:
    return resolve_app_state(
        request,
        "screening_result_store",
        InMemoryResultStore[tuple[str, list[ScreenResult]]],
        label="The screening result store",
    )
