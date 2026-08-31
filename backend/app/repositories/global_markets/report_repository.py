"""Abstract contract for persisting `CategoryIntelligenceReport`s.

A third, independent persistence boundary alongside
`BaseGlobalMarketRunRepository` (run-level tracking) and
`BaseRankedAssetRepository` (per-asset ranked results) — see
`IntelligenceRun`'s own docstring on why these stay separate. `save_report`
is an upsert (one report per `(run_id, category)`, overwritten in place on
a retry) rather than `RankedAsset`'s replace-a-whole-category-at-once
semantics, since a report is always exactly one row, never a batch.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.global_markets.intelligence_report import CategoryIntelligenceReport
from app.global_markets.models import ReportCategory

__all__ = ["BaseIntelligenceReportRepository"]


class BaseIntelligenceReportRepository(ABC):
    """Abstract base class every `CategoryIntelligenceReport` repository implementation must inherit."""

    @abstractmethod
    async def save_report(self, report: CategoryIntelligenceReport) -> None:
        """Persist `report`, overwriting any previously stored report for
        the same `(run_id, category)` — the idempotent-retry primitive
        for this persistence boundary."""
        raise NotImplementedError

    @abstractmethod
    async def get_report(self, run_id: str, category: ReportCategory) -> CategoryIntelligenceReport | None:
        """Retrieve the stored report for `(run_id, category)`, or `None` if none exists yet."""
        raise NotImplementedError

    @abstractmethod
    async def list_reports_for_run(self, run_id: str) -> list[CategoryIntelligenceReport]:
        """Every stored report across all categories of one run."""
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        """Report whether the underlying storage backend is reachable."""
        raise NotImplementedError
