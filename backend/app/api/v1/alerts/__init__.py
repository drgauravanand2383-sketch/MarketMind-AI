"""Alert API (`/api/v1/alerts`, Sprint 58): exposes
`app.alerts.engine.AlertService` — every endpoint delegates directly to
an existing method; no business logic is duplicated."""

from app.api.v1.alerts.router import router

__all__ = ["router"]
