"""Risk Analytics Engine: evaluates the overall risk characteristics of a
portfolio from already-generated Recommendation and Strategy Evaluation
outputs, providing analytical insight only.

No allocation optimization, no rebalancing, no trade execution, no broker
connection, no market-data fetch, and no Monte Carlo simulation exist
anywhere in this package.
"""

from __future__ import annotations

from app.risk.exceptions import (
    DuplicateRiskRequestNameError,
    RiskAnalyticsError,
    RiskAssessmentNotFoundError,
    RiskAssessmentRequestNotFoundError,
)
from app.risk.models import (
    PortfolioExposure,
    RiskAssessment,
    RiskAssessmentRequest,
    RiskCategory,
    RiskMetric,
    RiskSeverity,
    RiskThresholds,
    RiskWeighting,
)
from app.risk.engine import RiskAnalyticsService

__all__ = [
    "RiskAnalyticsService",
    "RiskCategory",
    "RiskSeverity",
    "RiskWeighting",
    "RiskThresholds",
    "RiskAssessmentRequest",
    "PortfolioExposure",
    "RiskMetric",
    "RiskAssessment",
    "RiskAnalyticsError",
    "RiskAssessmentRequestNotFoundError",
    "RiskAssessmentNotFoundError",
    "DuplicateRiskRequestNameError",
]
