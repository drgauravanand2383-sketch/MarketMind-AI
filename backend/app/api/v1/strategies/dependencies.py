"""FastAPI dependency provider for the Strategy Evaluation API — resolves
`StrategyEvaluationService` from `request.app.state`. `get_recommendation_service`
is reused directly from `app.api.v1.portfolio.dependencies` rather than
duplicated — evaluating a strategy needs an already-computed
`RecommendationResult`, fetched via that same service.
"""

from __future__ import annotations

from fastapi import Request

from app.api.dependencies.state import resolve_app_state
from app.strategy.engine import StrategyEvaluationService

__all__ = ["get_strategy_service"]


def get_strategy_service(request: Request) -> StrategyEvaluationService:
    return resolve_app_state(request, "strategy_service", StrategyEvaluationService, label="StrategyEvaluationService")
