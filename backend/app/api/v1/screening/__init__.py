"""Screening API (`/api/v1/screening`, Sprint 58): exposes
`app.screening.engine.ScreeningEngine` — every endpoint delegates
directly to an existing method; no business logic is duplicated. A thin
in-process cache (see `app.api.v1.schemas.result_store`) backs
`GET /results/{result_id}`, since the engine itself has no persistence."""

from app.api.v1.screening.router import router

__all__ = ["router"]
