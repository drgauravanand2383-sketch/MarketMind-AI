"""FastAPI dependency provider for the Strategy Evaluation API — resolves
`StrategyEvaluationService` from `request.app.state`. `get_recommendation_service`
is reused directly from `app.api.v1.portfolio.dependencies` rather than
duplicated — evaluating a strategy needs an already-computed
`RecommendationResult`, fetched via that same service.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.strategy.engine import StrategyEvaluationService

__all__ = ["get_strategy_service"]


def get_strategy_service(request: Request) -> StrategyEvaluationService:
    service = getattr(request.app.state, "strategy_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="StrategyEvaluationService is not configured on this application instance.",
        )
    return service
