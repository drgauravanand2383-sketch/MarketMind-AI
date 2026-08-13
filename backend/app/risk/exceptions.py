"""Exception hierarchy for the Risk Analytics Engine's application layer.

Self-contained model constraints (non-positive weight, invalid/overlapping
thresholds, blank portfolio_id, out-of-range score/weight) are enforced by
`app.risk.models` itself and raise a plain `pydantic.ValidationError` —
see that module's docstring. This hierarchy covers only what
`RiskAnalyticsService` enforces: rules that depend on existing repository
state (not found) or injected, runtime-configurable state (duplicate
request names).
"""

from __future__ import annotations

__all__ = [
    "RiskAnalyticsError",
    "RiskAssessmentRequestNotFoundError",
    "RiskAssessmentNotFoundError",
    "DuplicateRiskRequestNameError",
]


class RiskAnalyticsError(Exception):
    """Base class for every error raised by the Risk Analytics Engine's application layer."""

    def __init__(self, message: str, *, request_id: str | None = None) -> None:
        self.request_id = request_id
        super().__init__(message)


class RiskAssessmentRequestNotFoundError(RiskAnalyticsError):
    """Raised when no risk assessment request exists for the given id."""

    def __init__(self, request_id: str) -> None:
        super().__init__(f"No risk assessment request found with id {request_id!r}.", request_id=request_id)


class RiskAssessmentNotFoundError(RiskAnalyticsError):
    """Raised when no risk assessment exists for the given request id."""

    def __init__(self, request_id: str) -> None:
        super().__init__(f"No risk assessment found for request id {request_id!r}.", request_id=request_id)


class DuplicateRiskRequestNameError(RiskAnalyticsError):
    """Raised when creating a request with a name already in use.

    Only raised when `RiskAnalyticsService` was constructed with
    `enforce_unique_names=True` (the default).
    """

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"A risk assessment request named {name!r} already exists.")
