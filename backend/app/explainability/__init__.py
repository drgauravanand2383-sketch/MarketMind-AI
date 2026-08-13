"""Explainability & Performance Attribution Engine: explains already-
generated Recommendation, Strategy Evaluation, Risk Analytics, and
Backtesting output, providing analytical explanations only.

No score is ever recomputed, no historical backtest result is ever
altered, and no live market data fetch, trade execution, or portfolio
optimization exists anywhere in this package.
"""

from __future__ import annotations

from app.explainability.exceptions import (
    DuplicateExplainabilityRequestNameError,
    ExplainabilityError,
    ExplainabilityRequestNotFoundError,
    ExplainabilityResultNotFoundError,
    InvalidReferenceError,
)
from app.explainability.models import (
    AttributionCategory,
    ContributionBreakdown,
    ExplainabilityRequest,
    ExplainabilityResult,
    ExplainabilityWeighting,
    PerformanceAttribution,
    RecommendationExplanation,
    RiskExplanation,
    StrategyExplanation,
)
from app.explainability.engine import ExplainabilityService

__all__ = [
    "ExplainabilityService",
    "AttributionCategory",
    "ExplainabilityWeighting",
    "ExplainabilityRequest",
    "ContributionBreakdown",
    "RecommendationExplanation",
    "StrategyExplanation",
    "RiskExplanation",
    "PerformanceAttribution",
    "ExplainabilityResult",
    "ExplainabilityError",
    "ExplainabilityRequestNotFoundError",
    "ExplainabilityResultNotFoundError",
    "DuplicateExplainabilityRequestNameError",
    "InvalidReferenceError",
]
