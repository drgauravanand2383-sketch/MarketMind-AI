"""Abstract contract for persisting Global Market Intelligence runs.

`BaseGlobalMarketRunRepository` stores `IntelligenceRun` rows only — no
market data, no ranking logic, no business rules (idempotency/dedup for
"no duplicate report for the same run/date" lives in
`app.workflows.global_markets.pipeline.GlobalMarketIntelligenceWorkflow`,
enforced structurally here via a database-level uniqueness constraint on
`run_date`, mirroring `app.repositories.watchlist.postgres.models`'s own
`UniqueConstraint` precedent — see
`app.repositories.global_markets.postgres.models`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from app.global_markets.models import IntelligenceRun

__all__ = ["BaseGlobalMarketRunRepository", "DuplicateIntelligenceRunError"]


class DuplicateIntelligenceRunError(Exception):
    """Raised when `create_run` is called for a `run_date` that already has a stored run."""

    def __init__(self, run_date: date) -> None:
        self.run_date = run_date
        super().__init__(f"An intelligence run already exists for run_date {run_date!r}")


class BaseGlobalMarketRunRepository(ABC):
    """Abstract base class every Global Market Intelligence run repository implementation must inherit."""

    @abstractmethod
    async def create_run(self, run: IntelligenceRun) -> IntelligenceRun:
        """Persist a new run. `run.id` is assumed unique — the caller is
        responsible for generating it.

        Raises:
            DuplicateIntelligenceRunError: If a run already exists for `run.run_date`.
        """
        raise NotImplementedError

    @abstractmethod
    async def update_run(self, run: IntelligenceRun) -> IntelligenceRun | None:
        """Overwrite the stored run sharing `run.id` with `run`'s current
        state (e.g. as category outcomes complete over the run's
        lifetime). Returns `None` if no run with that id exists."""
        raise NotImplementedError

    @abstractmethod
    async def get_run(self, run_id: str) -> IntelligenceRun | None:
        """Retrieve a single run by id."""
        raise NotImplementedError

    @abstractmethod
    async def get_run_by_date(self, run_date: date) -> IntelligenceRun | None:
        """Retrieve the run for `run_date`, or `None` if none exists yet."""
        raise NotImplementedError

    @abstractmethod
    async def list_runs(self) -> list[IntelligenceRun]:
        """Return every stored run, most recent `run_date` first."""
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        """Report whether the underlying storage backend is reachable."""
        raise NotImplementedError
