"""Abstract contract for persisting explainability requests and results.

BaseExplainabilityRepository defines the persistence boundary for the
Explainability & Performance Attribution Engine. It stores requests and
generated results only — no recommendation/strategy/risk/backtest data,
no explanation logic, and no business logic (duplicate-name prevention)
lives here; that lives in `app.explainability.engine.ExplainabilityService`,
the sole Application-layer service. Every mutating method targeting an
existing record returns `None` when it does not exist, rather than
raising — mirrors every other repository in this codebase.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.explainability.models import ExplainabilityRequest, ExplainabilityResult

__all__ = ["BaseExplainabilityRepository"]


class BaseExplainabilityRepository(ABC):
    """Abstract base class every explainability repository implementation must inherit."""

    @abstractmethod
    async def create_request(self, request: ExplainabilityRequest) -> ExplainabilityRequest:
        """Persist a new request. `request.id` is assumed unique — the
        caller (`ExplainabilityService`) is responsible for generating it."""
        raise NotImplementedError

    @abstractmethod
    async def get_request(self, request_id: str) -> ExplainabilityRequest | None:
        """Retrieve a single request by id."""
        raise NotImplementedError

    @abstractmethod
    async def list_requests(self) -> list[ExplainabilityRequest]:
        """Return every stored request."""
        raise NotImplementedError

    @abstractmethod
    async def store_result(self, result: ExplainabilityResult) -> ExplainabilityResult:
        """Persist a generated result. A request may be re-explained,
        producing more than one stored result over time for the same
        `request_id` — see `get_result`."""
        raise NotImplementedError

    @abstractmethod
    async def get_result(self, request_id: str) -> ExplainabilityResult | None:
        """Retrieve the most recently stored result for `request_id`, or
        `None` if none exists."""
        raise NotImplementedError

    @abstractmethod
    async def list_results(self) -> list[ExplainabilityResult]:
        """Return every stored result, across every request."""
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        """Report whether the underlying storage backend is reachable."""
        raise NotImplementedError
