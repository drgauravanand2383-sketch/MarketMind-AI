"""Schemas for the Market Data Refresh workflow (Milestone 13)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.services.market_snapshot.models import MarketSnapshotResult

__all__ = ["MarketDataRefreshResult"]


class MarketDataRefreshResult(BaseModel):
    """The output of `MarketDataRefreshWorkflow.execute()` — one summary
    per scheduled (or manually triggered) refresh run."""

    model_config = ConfigDict(extra="forbid")

    execution_id: str
    started_at: datetime
    completed_at: datetime
    entities_requested: int
    fresh_count: int
    stale_count: int
    unavailable_count: int
    results: list[MarketSnapshotResult] = Field(default_factory=list)
