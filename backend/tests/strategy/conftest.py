"""Shared helpers for Strategy Evaluation Engine tests."""

from __future__ import annotations

from datetime import datetime, timezone

from app.recommendations.models import RecommendationCandidate, RecommendationResult, RecommendationSummary, RecommendationType
from app.strategy.models import InvestmentStrategy, StrategyRule, StrategyWeighting

NOW = datetime(2026, 8, 10, tzinfo=timezone.utc)


def make_rule(
    rule_id: str = "r1",
    field: str = "overall_score",
    operator: str = "GREATER_THAN",
    value: object = 50,
    weight: float = 1.0,
    enabled: bool = True,
) -> StrategyRule:
    return StrategyRule(id=rule_id, field=field, operator=operator, value=value, weight=weight, enabled=enabled)


def make_strategy(
    strategy_id: str = "s1",
    name: str = "Test Strategy",
    rules: tuple[StrategyRule, ...] = (),
    weightings: StrategyWeighting = StrategyWeighting(),
    **overrides: object,
) -> InvestmentStrategy:
    defaults: dict[str, object] = {
        "id": strategy_id,
        "name": name,
        "created_at": NOW,
        "updated_at": NOW,
        "rules": rules,
        "weightings": weightings,
    }
    defaults.update(overrides)
    return InvestmentStrategy(**defaults)


def make_candidate(
    ticker: str = "AAPL",
    overall_score: float = 50.0,
    confidence: float = 80.0,
    recommendation: RecommendationType = RecommendationType.HOLD,
    **overrides: object,
) -> RecommendationCandidate:
    defaults: dict[str, object] = {
        "ticker": ticker,
        "overall_score": overall_score,
        "confidence": confidence,
        "recommendation": recommendation,
        "reasoning": "x",
        "created_at": NOW,
    }
    defaults.update(overrides)
    return RecommendationCandidate(**defaults)


def make_recommendation_result(
    candidates: tuple[RecommendationCandidate, ...] = (), request_id: str = "rec-1"
) -> RecommendationResult:
    return RecommendationResult(
        request_id=request_id,
        generated_at=NOW,
        total_candidates=len(candidates),
        recommendations=candidates,
        summary=RecommendationSummary(),
    )
