"""REST API Foundation (`/api/v1`, Sprint 55).

Exposes the completed backend (Screening through Explainability,
Sprints 44-53, plus the Sprint 54 operational infrastructure) through a
versioned, read-only HTTP API. No business logic lives in this package —
every route resolves an already-constructed service via dependency
injection (`app.api.v1.dependencies`) and calls only that service's own
existing methods.
"""

from app.api.v1.router import router

__all__ = ["router"]
