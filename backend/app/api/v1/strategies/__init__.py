"""Strategy Evaluation API (`/api/v1/strategies`, Sprint 58): exposes
`app.strategy.engine.StrategyEvaluationService` — every endpoint
delegates directly to an existing method; no business logic is duplicated."""

from app.api.v1.strategies.router import router

__all__ = ["router"]
