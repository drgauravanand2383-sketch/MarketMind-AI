"""Exception hierarchy for the Portfolio Recommendation Engine's application layer.

Self-contained model constraints (non-positive weight, invalid/overlapping
thresholds, blank ticker, out-of-range score/confidence) are enforced by
`app.recommendations.models` itself and raise a plain
`pydantic.ValidationError` — see that module's docstring. This hierarchy
covers only what `PortfolioRecommendationService` enforces: rules that
depend on existing repository state (not found) or injected,
runtime-configurable state (duplicate request names).
"""

from __future__ import annotations

__all__ = [
    "RecommendationEngineError",
    "RecommendationRequestNotFoundError",
    "RecommendationResultNotFoundError",
    "DuplicateRequestNameError",
]


class RecommendationEngineError(Exception):
    """Base class for every error raised by the Portfolio Recommendation Engine's application layer."""

    def __init__(self, message: str, *, request_id: str | None = None) -> None:
        self.request_id = request_id
        super().__init__(message)


class RecommendationRequestNotFoundError(RecommendationEngineError):
    """Raised when no recommendation request exists for the given id."""

    def __init__(self, request_id: str) -> None:
        super().__init__(f"No recommendation request found with id {request_id!r}.", request_id=request_id)


class RecommendationResultNotFoundError(RecommendationEngineError):
    """Raised when no recommendation result exists for the given request id."""

    def __init__(self, request_id: str) -> None:
        super().__init__(
            f"No recommendation result found for request id {request_id!r}.", request_id=request_id
        )


class DuplicateRequestNameError(RecommendationEngineError):
    """Raised when creating a request with a name already in use.

    Only raised when `PortfolioRecommendationService` was constructed with
    `enforce_unique_names=True` (the default).
    """

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"A recommendation request named {name!r} already exists.")
