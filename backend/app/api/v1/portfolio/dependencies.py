"""FastAPI dependency providers for the Portfolio API.

`get_watchlist_service` and `get_portfolio_intelligence_agent` are reused
directly from their existing modules rather than duplicated here — see
`app.api.v1.watchlists.dependencies` and `app.api.intelligence.dependencies`.
Only the two providers with no existing home (`RiskAnalyticsService`,
`PortfolioRecommendationService`) are defined here, following the exact
same `request.app.state` lookup pattern.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.recommendations.engine import PortfolioRecommendationService
from app.risk.engine import RiskAnalyticsService

__all__ = ["get_risk_service", "get_recommendation_service"]


def get_risk_service(request: Request) -> RiskAnalyticsService:
    service = getattr(request.app.state, "risk_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RiskAnalyticsService is not configured on this application instance.",
        )
    return service


def get_recommendation_service(request: Request) -> PortfolioRecommendationService:
    service = getattr(request.app.state, "recommendation_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PortfolioRecommendationService is not configured on this application instance.",
        )
    return service
