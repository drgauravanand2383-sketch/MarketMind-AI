"""Exception hierarchy for the Explainability & Performance Attribution
Engine's application layer.

Self-contained model constraints (non-positive weight, blank identifiers)
are enforced by `app.explainability.models` itself and raise a plain
`pydantic.ValidationError` — see that module's docstring. This hierarchy
covers only what `ExplainabilityService` enforces: rules that depend on
existing repository state (not found), injected, runtime-configurable
state (duplicate request names), or resolution of a request's referenced
ids against the injected recommendation/strategy/risk/backtesting
services (invalid reference).
"""

from __future__ import annotations

__all__ = [
    "ExplainabilityError",
    "ExplainabilityRequestNotFoundError",
    "ExplainabilityResultNotFoundError",
    "DuplicateExplainabilityRequestNameError",
    "InvalidReferenceError",
]


class ExplainabilityError(Exception):
    """Base class for every error raised by the Explainability &
    Performance Attribution Engine's application layer."""

    def __init__(self, message: str, *, request_id: str | None = None) -> None:
        self.request_id = request_id
        super().__init__(message)


class ExplainabilityRequestNotFoundError(ExplainabilityError):
    """Raised when no explainability request exists for the given id."""

    def __init__(self, request_id: str) -> None:
        super().__init__(f"No explainability request found with id {request_id!r}.", request_id=request_id)


class ExplainabilityResultNotFoundError(ExplainabilityError):
    """Raised when no explainability result exists for the given request id."""

    def __init__(self, request_id: str) -> None:
        super().__init__(f"No explainability result found for request id {request_id!r}.", request_id=request_id)


class DuplicateExplainabilityRequestNameError(ExplainabilityError):
    """Raised when creating a request with a name already in use.

    Only raised when `ExplainabilityService` was constructed with
    `enforce_unique_names=True` (the default).
    """

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"An explainability request named {name!r} already exists.")


class InvalidReferenceError(ExplainabilityError):
    """Raised when an `ExplainabilityRequest` references a
    recommendation/strategy/risk/backtest request id that the
    corresponding injected service could not resolve."""

    def __init__(self, request_id: str, reason: str) -> None:
        super().__init__(
            f"Explainability request {request_id!r} references an unresolvable result: {reason}",
            request_id=request_id,
        )
