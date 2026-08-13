"""Strategy Evaluation Engine: evaluates already-generated
`app.recommendations.models.RecommendationResult` output against
configurable investment strategies, determining how well a batch of
recommendations aligns with one or more strategies.

No portfolio-allocation optimization, no trade execution, no portfolio
risk calculation, no rebalancing, and no market-data fetch exist anywhere
in this package — alignment scoring and explainability only.
"""

from __future__ import annotations

from app.strategy.exceptions import (
    DuplicateStrategyNameError,
    MaxStrategiesExceededError,
    MaxStrategyRulesExceededError,
    StrategyEngineError,
    StrategyEvaluationNotFoundError,
    StrategyNotFoundError,
)
from app.strategy.models import (
    InvestmentStrategy,
    RuleAlignment,
    StrategyEvaluationRequest,
    StrategyEvaluationResult,
    StrategyMatch,
    StrategyOperator,
    StrategyRule,
    StrategySummary,
    StrategyType,
    StrategyWeighting,
)
from app.strategy.engine import StrategyEvaluationService

__all__ = [
    "StrategyEvaluationService",
    "StrategyOperator",
    "StrategyType",
    "StrategyWeighting",
    "StrategyRule",
    "InvestmentStrategy",
    "StrategyEvaluationRequest",
    "RuleAlignment",
    "StrategyMatch",
    "StrategySummary",
    "StrategyEvaluationResult",
    "StrategyEngineError",
    "StrategyNotFoundError",
    "StrategyEvaluationNotFoundError",
    "DuplicateStrategyNameError",
    "MaxStrategiesExceededError",
    "MaxStrategyRulesExceededError",
]
