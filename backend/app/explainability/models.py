"""Domain models for the Explainability & Performance Attribution Engine.

Explains already-generated `app.recommendations.models.RecommendationResult`
(Sprint 49), `app.strategy.models.StrategyEvaluationResult` (Sprint 50),
`app.risk.models.RiskAssessment` (Sprint 51), and
`app.backtesting.models.BacktestRun`/`BacktestResult` (Sprint 52) output —
never recomputes any score, never alters a historical backtest result,
never fetches market data, never executes a trade, and never optimizes a
portfolio. This engine produces analytical explanations only.

Design note — same reuse pattern as Sprint 52, extended to a fourth
engine: like `app.backtesting.engine.BacktestingService`, this one is
constructed with the actual `PortfolioRecommendationService`/
`StrategyEvaluationService`/`RiskAnalyticsService`/`BacktestingService`
instances injected, and resolves `ExplainabilityRequest`'s referenced ids
by calling only those services' own read-only `get_result`/`get_evaluation`/
`get_assessment`/`get_run`/`get_result` methods — never their generate/
evaluate/assess/run methods. "Use existing outputs only. Do not recompute
business logic." is read literally throughout `app.explainability.engine`:
every score, every `RuleAlignment`, every `RiskMetric`, every
`PortfolioExposure` an explanation surfaces is copied verbatim from the
resolved result, never recalculated. See that module's own docstring for
the full resolution and attribution algorithm.

Design note — `ContributionBreakdown` is reused across three different
explanation levels, `RiskExplanation.category_breakdown` is not: at the
per-candidate (`RecommendationExplanation`) and per-strategy
(`StrategyExplanation`) level, and at the aggregate portfolio level
(`PerformanceAttribution`), every contributing signal already maps
directly onto one of this sprint's own `AttributionCategory` values
(`SCREENING`, `PLANNING`, `RESEARCH`, `PORTFOLIO_INTELLIGENCE`, `SIGNALS`,
`ALERTS` from `RecommendationCandidate`'s own score fields; `STRATEGY`
from rule weights; `SECTOR`/`COUNTRY`/`INDUSTRY` from
`RiskAssessment.exposures`; `RISK` from the inverted overall risk score).
`RiskExplanation.category_breakdown`, however, is populated from
`RiskAssessment.risk_metrics`, which is already typed by a *different*,
pre-existing, more granular taxonomy — `app.risk.models.RiskCategory`
(`DIVERSIFICATION`/`CONCENTRATION`/`VOLATILITY`/`LIQUIDITY`/`MARKET_CAP`/
etc.) — that has no clean, non-lossy mapping onto `AttributionCategory`.
Forcing a remap would either drop information or misrepresent the
original metric. `RiskExplanation.category_breakdown` therefore reuses
`RiskMetric` directly (re-sorted by score descending for the sprint's own
"Rank contributing factors" requirement — never recalculated), and
`exposure_breakdown` reuses `PortfolioExposure` directly — both already
exist, already carry exactly the needed fields, and copying them verbatim
is the most literal reading of "transparent attribution based on
previously generated results."

Design note — additive `ExplainabilityWeighting`: "Support configurable
contribution weighting" has no configuration model anywhere in this
sprint's literal Domain Models list. Mirrors every prior sprint's own
`*Weighting` model (`RiskWeighting`, Sprint 51; `StrategyWeighting`,
Sprint 50; `ScoringWeights`, Sprint 49) — one positive weight per
`AttributionCategory` the built-in pipeline actually computes (`CUSTOM` is
reserved for future extensibility and has no weight here, exactly as
`RiskWeighting` excluded `STYLE`/`CUSTOM`).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.risk.models import PortfolioExposure, RiskMetric, RiskSeverity
from app.strategy.models import RuleAlignment

__all__ = [
    "AttributionCategory",
    "ExplainabilityWeighting",
    "ExplainabilityRequest",
    "ContributionBreakdown",
    "RecommendationExplanation",
    "StrategyExplanation",
    "RiskExplanation",
    "PerformanceAttribution",
    "ExplainabilityResult",
]


class AttributionCategory(StrEnum):
    PLANNING = "PLANNING"
    SCREENING = "SCREENING"
    SIGNALS = "SIGNALS"
    ALERTS = "ALERTS"
    RESEARCH = "RESEARCH"
    PORTFOLIO_INTELLIGENCE = "PORTFOLIO_INTELLIGENCE"
    STRATEGY = "STRATEGY"
    RISK = "RISK"
    SECTOR = "SECTOR"
    COUNTRY = "COUNTRY"
    INDUSTRY = "INDUSTRY"
    CUSTOM = "CUSTOM"


class ExplainabilityWeighting(BaseModel):
    """Configurable per-category weights used to blend already-computed
    scores into a `ContributionBreakdown`. Every weight must be positive —
    the sprint's own "Contribution weights valid" requirement. Covers
    exactly the eleven categories the built-in pipeline computes
    (`CUSTOM` is not computed by the built-in pipeline and so has no
    weight here)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    planning: float = Field(default=1.0, gt=0)
    screening: float = Field(default=1.0, gt=0)
    signals: float = Field(default=1.0, gt=0)
    alerts: float = Field(default=1.0, gt=0)
    research: float = Field(default=1.0, gt=0)
    portfolio_intelligence: float = Field(default=1.0, gt=0)
    strategy: float = Field(default=1.0, gt=0)
    risk: float = Field(default=1.0, gt=0)
    sector: float = Field(default=1.0, gt=0)
    country: float = Field(default=1.0, gt=0)
    industry: float = Field(default=1.0, gt=0)


class ExplainabilityRequest(BaseModel):
    """A request to explain one already-generated pipeline of results,
    referencing (never resolving/fetching — see module docstring)
    whichever recommendation/strategy/risk/backtest results inform it.
    `recommendation_result_id` is required — every explanation this engine
    produces ultimately traces back to a `RecommendationResult`; the other
    three are optional, each unlocking one additional explanation
    (`strategy_explanations`, `risk_explanation`, `performance_attribution`
    respectively) only when supplied."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    recommendation_result_id: str = Field(min_length=1)
    strategy_evaluation_id: str | None = None
    risk_assessment_id: str | None = None
    backtest_run_id: str | None = None
    created_at: datetime


class ContributionBreakdown(BaseModel):
    """One category's share of an already-computed score or return — see
    `app.explainability.engine` for exactly how `contribution_percent` is
    derived (a normalized, weighted share of a total; never a fabricated
    number)."""

    model_config = ConfigDict(extra="forbid")

    source: str
    category: AttributionCategory
    weight: float
    contribution_percent: float
    description: str


class RecommendationExplanation(BaseModel):
    """Why one `RecommendationCandidate` was scored/ranked the way it
    was — every field here is copied or derived from that candidate's own
    already-computed fields, never recalculated."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    company_name: str | None = None
    overall_score: float
    confidence: float
    contributing_components: tuple[ContributionBreakdown, ...] = Field(default_factory=tuple)
    top_positive_factors: tuple[ContributionBreakdown, ...] = Field(default_factory=tuple)
    top_negative_factors: tuple[ContributionBreakdown, ...] = Field(default_factory=tuple)
    reasoning: str
    summary: str


class StrategyExplanation(BaseModel):
    """Why one `StrategyMatch` aligned the way it did — `matched_rules`/
    `failed_rules` are that match's own `RuleAlignment` tuples, copied
    verbatim (never recomputed); `weight_breakdown` re-expresses those same
    rules' weights as a normalized `ContributionBreakdown`."""

    model_config = ConfigDict(extra="forbid")

    strategy_name: str
    alignment_score: float
    matched_rules: tuple[RuleAlignment, ...] = Field(default_factory=tuple)
    failed_rules: tuple[RuleAlignment, ...] = Field(default_factory=tuple)
    weight_breakdown: tuple[ContributionBreakdown, ...] = Field(default_factory=tuple)
    summary: str


class RiskExplanation(BaseModel):
    """Why one `RiskAssessment` scored the way it did — `category_breakdown`/
    `exposure_breakdown` are that assessment's own `RiskMetric`/
    `PortfolioExposure` tuples (re-sorted by score/weight, never
    recalculated); `severity_breakdown` is a plain count of `risk_metrics`
    by severity."""

    model_config = ConfigDict(extra="forbid")

    overall_risk_score: float
    category_breakdown: tuple[RiskMetric, ...] = Field(default_factory=tuple)
    severity_breakdown: dict[RiskSeverity, int] = Field(default_factory=dict)
    exposure_breakdown: tuple[PortfolioExposure, ...] = Field(default_factory=tuple)
    summary: str


class PerformanceAttribution(BaseModel):
    """How one backtest's already-computed return decomposes across
    contributing sources. `portfolio_return`/`benchmark_return`/
    `excess_return` are copied verbatim from the resolved `BacktestResult`
    — never recalculated; `contribution_breakdown` allocates that return
    across the categories that fed the underlying recommendation/strategy/
    risk pipeline."""

    model_config = ConfigDict(extra="forbid")

    period: str
    portfolio_return: float
    benchmark_return: float
    excess_return: float
    contribution_breakdown: tuple[ContributionBreakdown, ...] = Field(default_factory=tuple)
    summary: str


class ExplainabilityResult(BaseModel):
    """The outcome of one `ExplainabilityService.explain()` run."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    generated_at: datetime
    recommendation_explanations: tuple[RecommendationExplanation, ...] = Field(default_factory=tuple)
    strategy_explanations: tuple[StrategyExplanation, ...] = Field(default_factory=tuple)
    risk_explanation: RiskExplanation | None = None
    performance_attribution: PerformanceAttribution | None = None
    overall_summary: str
