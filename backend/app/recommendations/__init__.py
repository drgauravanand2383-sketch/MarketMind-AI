"""Portfolio Recommendation Engine: consumes normalized outputs from
existing engines (Screening, Signal Detection, Alerts, Company Research,
Portfolio Intelligence) and generates explainable, scored, ranked
recommendation candidates.

No trade execution, no automatic rebalancing, no portfolio optimization,
no advanced risk calculation, no broker connection, and no live market
data fetch exist anywhere in this package — recommendation candidates
only, with transparent reasoning.
"""

from __future__ import annotations

from app.recommendations.engine import PortfolioRecommendationService
from app.recommendations.exceptions import (
    DuplicateRequestNameError,
    RecommendationEngineError,
    RecommendationRequestNotFoundError,
    RecommendationResultNotFoundError,
)
from app.recommendations.models import (
    CandidateEvidence,
    RecommendationCandidate,
    RecommendationRequest,
    RecommendationResult,
    RecommendationSummary,
    RecommendationThresholds,
    RecommendationType,
    ScoringWeights,
)

__all__ = [
    "PortfolioRecommendationService",
    "RecommendationType",
    "ScoringWeights",
    "RecommendationThresholds",
    "CandidateEvidence",
    "RecommendationRequest",
    "RecommendationCandidate",
    "RecommendationSummary",
    "RecommendationResult",
    "RecommendationEngineError",
    "RecommendationRequestNotFoundError",
    "RecommendationResultNotFoundError",
    "DuplicateRequestNameError",
]
