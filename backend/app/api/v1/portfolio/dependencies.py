"""FastAPI dependency providers for the Portfolio API.

`get_watchlist_service` and `get_portfolio_intelligence_agent` are reused
directly from their existing modules rather than duplicated here — see
`app.api.v1.watchlists.dependencies` and `app.api.intelligence.dependencies`.
Only the two providers with no existing home (`RiskAnalyticsService`,
`PortfolioRecommendationService`) are defined here, following the exact
same `request.app.state` lookup pattern.
"""

from __future__ import annotations

from fastapi import Request

from app.api.dependencies.state import resolve_app_state
from app.recommendations.engine import PortfolioRecommendationService
from app.risk.engine import RiskAnalyticsService
from app.services.initial_analysis.service import InitialPortfolioAnalysisService
from app.services.portfolio_market_snapshot.service import PortfolioMarketSnapshotService

__all__ = [
    "get_risk_service",
    "get_recommendation_service",
    "get_portfolio_market_snapshot_service",
    "get_initial_analysis_service",
]


def get_risk_service(request: Request) -> RiskAnalyticsService:
    return resolve_app_state(request, "risk_service", RiskAnalyticsService, label="RiskAnalyticsService")


def get_recommendation_service(request: Request) -> PortfolioRecommendationService:
    return resolve_app_state(
        request, "recommendation_service", PortfolioRecommendationService, label="PortfolioRecommendationService"
    )


def get_portfolio_market_snapshot_service(request: Request) -> PortfolioMarketSnapshotService:
    return resolve_app_state(
        request,
        "portfolio_market_snapshot_service",
        PortfolioMarketSnapshotService,
        label="PortfolioMarketSnapshotService",
    )


def get_initial_analysis_service(request: Request) -> InitialPortfolioAnalysisService:
    return resolve_app_state(
        request, "initial_analysis_service", InitialPortfolioAnalysisService, label="InitialPortfolioAnalysisService"
    )
