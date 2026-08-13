"""Abstract contract for persisting recommendation requests and results.

BaseRecommendationRepository defines the persistence boundary for the
Portfolio Recommendation Engine. It stores requests and generated
recommendation results only — no market data, no re-derivation of
evidence, and no business logic (duplicate-name prevention) lives here;
that lives in `app.recommendations.engine.PortfolioRecommendationService`,
the sole Application-layer service. Every mutating method targeting an
existing record returns `None` when it does not exist, rather than
raising — mirrors every other repository in this codebase.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.recommendations.models import RecommendationRequest, RecommendationResult

__all__ = ["BaseRecommendationRepository"]


class BaseRecommendationRepository(ABC):
    """Abstract base class every recommendation repository implementation must inherit."""

    @abstractmethod
    async def create_request(self, request: RecommendationRequest) -> RecommendationRequest:
        """Persist a new request. `request.id` is assumed unique — the
        caller (`PortfolioRecommendationService`) is responsible for
        generating it."""
        raise NotImplementedError

    @abstractmethod
    async def get_request(self, request_id: str) -> RecommendationRequest | None:
        """Retrieve a single request by id."""
        raise NotImplementedError

    @abstractmethod
    async def list_requests(self) -> list[RecommendationRequest]:
        """Return every stored request."""
        raise NotImplementedError

    @abstractmethod
    async def store_result(self, result: RecommendationResult) -> RecommendationResult:
        """Persist a generated result. A request may be re-run, producing
        more than one stored result over time for the same `request_id` —
        see `get_result`."""
        raise NotImplementedError

    @abstractmethod
    async def get_result(self, request_id: str) -> RecommendationResult | None:
        """Retrieve the most recently stored result for `request_id`, or
        `None` if none exists."""
        raise NotImplementedError

    @abstractmethod
    async def list_results(self) -> list[RecommendationResult]:
        """Return every stored result, across every request."""
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        """Report whether the underlying storage backend is reachable."""
        raise NotImplementedError
