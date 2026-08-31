"""Schemas for PennyMicrocapIntelligenceAgent (AGT-007)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.global_markets.models import MarketSessionContext, ReportCategory
from app.global_markets.ranked_asset import RankedAsset

__all__ = ["PennyMicrocapIntelligenceRequest"]


class PennyMicrocapIntelligenceRequest(BaseModel):
    """Input to `PennyMicrocapIntelligenceAgent.run()` — one penny/micro-cap
    category's already-ranked, already-persisted, already-eligibility-filtered
    assets plus the market context they were resolved under. The agent
    never fetches, ranks, or eligibility-filters anything itself."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    category: ReportCategory
    market_session_context: MarketSessionContext
    ranked_assets: tuple[RankedAsset, ...] = Field(min_length=1)
