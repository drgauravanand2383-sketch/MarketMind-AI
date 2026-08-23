"""Domain models for Initial Portfolio Analysis (v1.2 Priority 8).

A newly created watchlist has no Risk/Recommendation state until something
actually calls `RiskAnalyticsService.assess_portfolio()`/
`PortfolioRecommendationService.generate_recommendations()` for it — see
`app.services.initial_analysis.service` module docstring for the full
root-cause analysis. `InitialAnalysisState` is the honest, always-real
status of that one-time bootstrap job for one portfolio; it is never a
stand-in for the `RiskAssessment`/`RecommendationResult` themselves (both
already exist, unchanged, in `app.risk.models`/`app.recommendations.models`).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

__all__ = ["InitialAnalysisStatus", "InitialAnalysisState"]


class InitialAnalysisStatus(StrEnum):
    """Where one portfolio's initial-analysis job currently stands.

    `ANALYZING`: dispatched, not yet complete (or currently retrying).
    `READY`: complete — a Recommendation and Risk assessment now exist,
        computed from full market-data coverage across every tracked
        company (`app.risk.models.MarketDataCoverageStatus.FULL`).
    `PARTIAL`: complete, but computed from incomplete market-data coverage
        (some or all companies had no resolvable/fetchable quote) — the
        result is real, never fabricated, just built from thinner evidence
        than `READY`; see `RiskAssessment.market_data_coverage` for exactly
        which companies were covered.
    `UNAVAILABLE`: nothing to analyze — the watchlist has zero companies.
        Never set for "market data was unavailable"; that is `PARTIAL`.
    `ERROR`: the job raised an unexpected exception before a result could
        be stored. `detail` carries the failure reason. Safe to retry.
    """

    ANALYZING = "ANALYZING"
    READY = "READY"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"


class InitialAnalysisState(BaseModel):
    """The current status of one portfolio's initial-analysis job."""

    model_config = ConfigDict(extra="forbid")

    portfolio_id: str
    status: InitialAnalysisStatus
    detail: str
    recommendation_request_id: str | None = None
    risk_request_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
