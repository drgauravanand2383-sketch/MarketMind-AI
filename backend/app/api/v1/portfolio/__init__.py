"""Portfolio API (`/api/v1/portfolio`, Sprint 57): by product decision,
"portfolio" has no domain entity of its own — a `portfolio_id` is a
`watchlist_id`. Every endpoint delegates to `WatchlistService`,
`PortfolioIntelligenceAgent`, `RiskAnalyticsService`, or
`PortfolioRecommendationService`; no business logic is duplicated."""

from app.api.v1.portfolio.router import router

__all__ = ["router"]
