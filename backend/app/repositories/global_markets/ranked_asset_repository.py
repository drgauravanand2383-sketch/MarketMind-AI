"""Abstract contract for persisting per-asset `RankedAsset` results.

Separate from `BaseGlobalMarketRunRepository` (which stores only
run-level tracking) — see `IntelligenceRun`'s own docstring on why
per-asset ranked results are a distinct persistence boundary. Replace,
not append/upsert-by-id, is the primitive: `RankedAsset` carries no
identity of its own beyond `(run_id, category, ticker)`, and "retry of
only failed components" (an explicit reliability requirement) means one
category's rows must be fully replaceable without touching any other
category's rows in the same run.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.global_markets.models import ReportCategory
from app.global_markets.ranked_asset import RankedAsset

__all__ = ["BaseRankedAssetRepository"]


class BaseRankedAssetRepository(ABC):
    """Abstract base class every `RankedAsset` repository implementation must inherit."""

    @abstractmethod
    async def replace_ranked_assets(
        self, run_id: str, category: ReportCategory, assets: tuple[RankedAsset, ...]
    ) -> None:
        """Atomically replace every previously stored `RankedAsset` row for
        `(run_id, category)` with `assets` — the idempotent-retry
        primitive: retrying one failed category never leaves duplicate or
        stale rows behind, and never touches another category's rows."""
        raise NotImplementedError

    @abstractmethod
    async def list_ranked_assets(self, run_id: str, category: ReportCategory) -> list[RankedAsset]:
        """Every ranked asset for one category of one run, ordered by rank ascending."""
        raise NotImplementedError

    @abstractmethod
    async def list_ranked_assets_for_run(self, run_id: str) -> list[RankedAsset]:
        """Every ranked asset across all categories of one run."""
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        """Report whether the underlying storage backend is reachable."""
        raise NotImplementedError
