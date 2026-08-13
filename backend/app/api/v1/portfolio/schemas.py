"""HTTP-layer request schemas for the Portfolio API.

Per product decision, "portfolio" has no domain entity of its own — a
`portfolio_id` *is* a `watchlist_id` (see `app.watchlist.models.Watchlist`).
Every response body here reuses an existing domain model directly
(`Watchlist`, `WatchlistStatistics`, `PortfolioIntelligenceReport`,
`RiskAssessment`, `RecommendationResult`) — only the POST
/portfolio/recommendations request has no matching domain model (creating a
`RecommendationRequest` takes primitive arguments plus client-supplied
evidence), so it gets a dedicated schema here.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.recommendations.models import CandidateEvidence

__all__ = ["GenerateRecommendationsRequest"]


class GenerateRecommendationsRequest(BaseModel):
    """Request body for `POST /api/v1/portfolio/recommendations`.

    Assembling per-ticker evidence from raw tickers would require new
    cross-engine orchestration logic this sprint must not introduce, so the
    caller supplies `evidence` directly — the router only calls
    `PortfolioRecommendationService.create_request()` then
    `.generate_recommendations()`.
    """

    model_config = ConfigDict(extra="forbid")

    portfolio_id: uuid.UUID = Field(examples=["9c1e2b1a-3f4d-4a5e-8b6c-7d8e9f0a1b2c"])
    evidence: list[CandidateEvidence] = Field(
        default_factory=list, examples=[[{"ticker": "AAPL", "sector": "Technology"}]]
    )
    max_recommendations: int = Field(default=10, ge=1, examples=[10])
    minimum_score: float = Field(default=0.0, ge=0.0, le=100.0, examples=[50.0])
