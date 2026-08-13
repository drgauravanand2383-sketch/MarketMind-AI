"""Abstract contract for persisting backtest requests, runs, and results.

BaseBacktestingRepository defines the persistence boundary for the
Backtesting Framework. It stores requests, run bookkeeping, and aggregate
results only — no recommendation/strategy/risk data, no replay logic, and
no business logic (duplicate-name prevention) lives here; that lives in
`app.backtesting.engine.BacktestingService`, the sole Application-layer
service. Every mutating method targeting an existing record returns
`None` when it does not exist, rather than raising — mirrors every other
repository in this codebase.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.backtesting.models import BacktestRequest, BacktestResult, BacktestRun

__all__ = ["BaseBacktestingRepository"]


class BaseBacktestingRepository(ABC):
    """Abstract base class every backtesting repository implementation must inherit."""

    @abstractmethod
    async def create_request(self, request: BacktestRequest) -> BacktestRequest:
        """Persist a new request. `request.id` is assumed unique — the
        caller (`BacktestingService`) is responsible for generating it."""
        raise NotImplementedError

    @abstractmethod
    async def get_request(self, request_id: str) -> BacktestRequest | None:
        """Retrieve a single request by id."""
        raise NotImplementedError

    @abstractmethod
    async def list_requests(self) -> list[BacktestRequest]:
        """Return every stored request."""
        raise NotImplementedError

    @abstractmethod
    async def store_run(self, run: BacktestRun) -> BacktestRun:
        """Persist a run's bookkeeping. A request may be re-run, producing
        more than one stored run over time for the same `request_id` —
        see `get_run`."""
        raise NotImplementedError

    @abstractmethod
    async def get_run(self, request_id: str) -> BacktestRun | None:
        """Retrieve the most recently stored run for `request_id`, or
        `None` if none exists."""
        raise NotImplementedError

    @abstractmethod
    async def list_runs(self) -> list[BacktestRun]:
        """Return every stored run, across every request."""
        raise NotImplementedError

    @abstractmethod
    async def store_result(self, result: BacktestResult) -> BacktestResult:
        """Persist a generated aggregate result. A request may be re-run,
        producing more than one stored result over time for the same
        `request_id` — see `get_result`."""
        raise NotImplementedError

    @abstractmethod
    async def get_result(self, request_id: str) -> BacktestResult | None:
        """Retrieve the most recently stored result for `request_id`, or
        `None` if none exists."""
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        """Report whether the underlying storage backend is reachable."""
        raise NotImplementedError
