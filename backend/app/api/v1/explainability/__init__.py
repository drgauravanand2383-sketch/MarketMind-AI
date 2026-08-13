"""Explainability API (`/api/v1/explainability`, Sprint 58): exposes
`app.explainability.engine.ExplainabilityService` — every endpoint
delegates directly to an existing method; no business logic is duplicated."""

from app.api.v1.explainability.router import router

__all__ = ["router"]
