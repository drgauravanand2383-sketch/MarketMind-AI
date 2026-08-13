"""Signal Detection API (`/api/v1/signals`, Sprint 58): exposes
`app.signals.engine.SignalDetectionService` — every endpoint delegates
directly to an existing method; no business logic is duplicated. A thin
in-process cache (see `app.api.v1.schemas.result_store`) backs
`GET /results/{result_id}`, since the service itself has no persistence."""

from app.api.v1.signals.router import router

__all__ = ["router"]
