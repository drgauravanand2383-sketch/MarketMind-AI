"""Schemas for GlobalMarketsResearchAgent (AGT-006)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.global_markets.models import MarketSessionContext, ReportCategory
from app.global_markets.ranked_asset import RankedAsset

__all__ = ["GlobalMarketsResearchRequest"]


class GlobalMarketsResearchRequest(BaseModel):
    """Input to `GlobalMarketsResearchAgent.run()` — one main category's
    already-ranked, already-persisted assets plus the market context they
    were resolved under. The agent never fetches or ranks anything itself."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    category: ReportCategory
    market_session_context: MarketSessionContext
    ranked_assets: tuple[RankedAsset, ...] = Field(min_length=1)
