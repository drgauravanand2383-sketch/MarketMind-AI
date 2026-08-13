"""Abstract contract for persisting risk assessment requests and results.

BaseRiskAnalyticsRepository defines the persistence boundary for the Risk
Analytics Engine. It stores requests and generated assessments only — no
market data, no re-derivation of recommendations/strategy evaluations, and
no business logic (duplicate-name prevention) lives here; that lives in
`app.risk.engine.RiskAnalyticsService`, the sole Application-layer
service. Every mutating method targeting an existing record returns
`None` when it does not exist, rather than raising — mirrors every other
repository in this codebase.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.risk.models import RiskAssessment, RiskAssessmentRequest

__all__ = ["BaseRiskAnalyticsRepository"]


class BaseRiskAnalyticsRepository(ABC):
    """Abstract base class every risk analytics repository implementation must inherit."""

    @abstractmethod
    async def create_request(self, request: RiskAssessmentRequest) -> RiskAssessmentRequest:
        """Persist a new request. `request.id` is assumed unique — the
        caller (`RiskAnalyticsService`) is responsible for generating it."""
        raise NotImplementedError

    @abstractmethod
    async def get_request(self, request_id: str) -> RiskAssessmentRequest | None:
        """Retrieve a single request by id."""
        raise NotImplementedError

    @abstractmethod
    async def list_requests(self) -> list[RiskAssessmentRequest]:
        """Return every stored request."""
        raise NotImplementedError

    @abstractmethod
    async def store_assessment(self, assessment: RiskAssessment) -> RiskAssessment:
        """Persist a generated assessment. A request may be re-assessed,
        producing more than one stored assessment over time for the same
        `request_id` — see `get_assessment`."""
        raise NotImplementedError

    @abstractmethod
    async def get_assessment(self, request_id: str) -> RiskAssessment | None:
        """Retrieve the most recently stored assessment for `request_id`,
        or `None` if none exists."""
        raise NotImplementedError

    @abstractmethod
    async def list_assessments(self) -> list[RiskAssessment]:
        """Return every stored assessment, across every request."""
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        """Report whether the underlying storage backend is reachable."""
        raise NotImplementedError
