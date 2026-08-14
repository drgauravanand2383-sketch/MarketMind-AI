"""Domain models for the Risk Analytics Engine.

Evaluates already-generated `app.recommendations.models.RecommendationResult`
(Sprint 49) and, optionally, `app.strategy.models.StrategyEvaluationResult`
(Sprint 50) output — never optimizes an allocation, never rebalances,
never executes a trade, never connects to a broker, never fetches market
data, and never runs a Monte Carlo simulation. Like every evaluation
engine since Sprint 48, this one never calls into the Recommendation or
Strategy Evaluation Engines itself: the caller supplies already-computed
results.

Design note — no market cap, price, volume, or return data anywhere in
this pipeline: `RecommendationCandidate` (this engine's primary input)
carries no `market_cap`, no price/volume, and no historical return series
— those fields exist on `app.market_data.models.CompanyProfile`/
`MarketQuote`/`HistoricalSeries`, but never propagate onto
`RecommendationCandidate`, and this sprint explicitly forbids fetching
market data directly. `app.risk.engine` is transparent about this: the
MARKET_CAP metric is always reported as "insufficient data" (never
fabricated), and VOLATILITY/LIQUIDITY are honestly-labeled *proxies* built
only from `RecommendationCandidate`'s own already-normalized 0-100 score
fields — never presented as a real statistical volatility/liquidity
measurement. See `app.risk.engine`'s own docstring for the exact formulas.

Design note — additive fields, flagged per this codebase's established
precedent: `RiskMetric.category` and `RiskAssessmentRequest.request_name`
are not in this sprint's literal field lists, but both are structurally
required by capabilities the sprint explicitly does require:
  - "Use configurable weighting for each risk category" is
    unimplementable without knowing which `RiskCategory` each `RiskMetric`
    belongs to — the literal `RiskMetric` field list has no such field.
  - "Duplicate request names configurable" (Validation) has no name field
    to check uniqueness against otherwise — every other engine in this
    series (Screening, Signals, Alerts, Recommendations, Strategy) has an
    explicit name field on its request/rule/strategy entity for exactly
    this purpose; `RiskAssessmentRequest` conspicuously had none.

Design note — "Consistent portfolio identifiers" (Validation): this
engine never fetches or cross-references `strategy_evaluation_id`/
`recommendation_result_id` against real records (see above — it only ever
sees whatever `RecommendationResult`/`StrategyEvaluationResult` objects
the caller directly supplies), so there is nothing to cross-check
consistency *against*. The literal, implementable reading enforced here:
`portfolio_id` must be a well-formed, non-blank identifier.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "RiskCategory",
    "RiskSeverity",
    "RiskWeighting",
    "RiskThresholds",
    "RiskAssessmentRequest",
    "PortfolioExposure",
    "RiskMetric",
    "MarketDataCoverageStatus",
    "MarketDataCoverage",
    "RiskAssessment",
]


class RiskCategory(str, Enum):
    DIVERSIFICATION = "DIVERSIFICATION"
    CONCENTRATION = "CONCENTRATION"
    SECTOR = "SECTOR"
    GEOGRAPHIC = "GEOGRAPHIC"
    VOLATILITY = "VOLATILITY"
    LIQUIDITY = "LIQUIDITY"
    STYLE = "STYLE"
    MARKET_CAP = "MARKET_CAP"
    CUSTOM = "CUSTOM"


class RiskSeverity(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskWeighting(BaseModel):
    """Configurable per-category weights used to compute
    `RiskAssessment.overall_risk_score`. Every weight must be positive —
    the sprint's own "Positive weights" requirement. Covers exactly the
    seven categories this engine's built-in pipeline always computes
    (`STYLE`/`CUSTOM` are not computed by the built-in pipeline — see
    `app.risk.engine`'s own docstring — and so have no weight here)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    diversification: float = Field(default=1.0, gt=0)
    concentration: float = Field(default=1.0, gt=0)
    sector: float = Field(default=1.0, gt=0)
    geographic: float = Field(default=1.0, gt=0)
    market_cap: float = Field(default=1.0, gt=0)
    volatility: float = Field(default=1.0, gt=0)
    liquidity: float = Field(default=1.0, gt=0)


class RiskThresholds(BaseModel):
    """Configurable score cut-points classifying a 0-100 risk score into a
    `RiskSeverity`. Three strictly ascending boundaries (higher score =
    higher risk, consistently across every metric this engine computes —
    see `app.risk.engine`) guarantee no gap or overlap by construction,
    the same reasoning `app.recommendations.models.RecommendationThresholds`
    (Sprint 49) already established for its own four boundaries."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    moderate_min: float = Field(default=25.0, ge=0, le=100)
    high_min: float = Field(default=50.0, ge=0, le=100)
    critical_min: float = Field(default=75.0, ge=0, le=100)

    @model_validator(mode="after")
    def _validate_strictly_ascending(self) -> RiskThresholds:
        if not (self.moderate_min < self.high_min < self.critical_min):
            raise ValueError(
                "Thresholds must be strictly ascending: moderate_min < high_min < critical_min."
            )
        return self

    def classify(self, score: float) -> RiskSeverity:
        if score >= self.critical_min:
            return RiskSeverity.CRITICAL
        if score >= self.high_min:
            return RiskSeverity.HIGH
        if score >= self.moderate_min:
            return RiskSeverity.MODERATE
        return RiskSeverity.LOW


class RiskAssessmentRequest(BaseModel):
    """A request to assess portfolio risk, referencing (never fetching —
    see module docstring) whichever `RecommendationResult`/
    `StrategyEvaluationResult` inform it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    request_name: str = Field(min_length=1)
    portfolio_id: str = Field(min_length=1)
    strategy_evaluation_id: str | None = None
    recommendation_result_id: str = Field(min_length=1)
    created_at: datetime


class PortfolioExposure(BaseModel):
    """One aggregated exposure bucket along a single dimension. Exactly
    one of `sector`/`country`/`industry` is populated on a given entry —
    which one identifies which dimension this bucket belongs to; the
    other two are `None`. See `app.risk.engine` for how these are
    aggregated (equal-weighted per candidate — no real position-sizing
    data exists anywhere in this codebase)."""

    model_config = ConfigDict(extra="forbid")

    sector: str | None = None
    country: str | None = None
    industry: str | None = None
    weight: float = Field(ge=0, le=1)
    holding_count: int = Field(ge=0)


class RiskMetric(BaseModel):
    """One computed risk signal."""

    model_config = ConfigDict(extra="forbid")

    metric_name: str
    category: RiskCategory
    value: float
    score: float = Field(ge=0, le=100)
    severity: RiskSeverity
    description: str


class MarketDataCoverageStatus(str, Enum):
    """How much of a `RiskAssessment`'s underlying `RecommendationCandidate`s
    (Milestone 14) carry live market data — purely informational (see
    `app.risk.engine`'s own docstring: this engine never fetches market
    data and no risk formula changes based on this value; distinguishing
    fresh from stale, and propagating unavailable honestly, is §5's own
    requirement, satisfied here without touching a single existing
    calculation).

    NOT_EVALUATED: no candidate carried a `market_freshness` at all (the
        pre-Milestone-14 shape, or this recommendation run never had
        market data wired in) — indistinguishable from "not applicable."
    NONE: market data was evaluated for every candidate, but none came
        back `FRESH`/`STALE` (e.g. every ticker unmapped/unavailable).
    PARTIAL: some, but not all, candidates have `FRESH`/`STALE` market data.
    FULL: every candidate has `FRESH`/`STALE` market data.
    """

    NOT_EVALUATED = "NOT_EVALUATED"
    NONE = "NONE"
    PARTIAL = "PARTIAL"
    FULL = "FULL"


class MarketDataCoverage(BaseModel):
    """Additive, informational-only summary of how much live market data
    backs one `RiskAssessment`'s input candidates. Never changes
    `overall_risk_score`/`risk_metrics` — see `app.risk.engine`'s module
    docstring for why this engine's formulas stay deterministic and
    market-data-free regardless of this field's value."""

    model_config = ConfigDict(extra="forbid")

    status: MarketDataCoverageStatus
    fresh_count: int = Field(ge=0, default=0)
    stale_count: int = Field(ge=0, default=0)
    unavailable_count: int = Field(ge=0, default=0)
    not_evaluated_count: int = Field(ge=0, default=0)
    total_candidates: int = Field(ge=0, default=0)


class RiskAssessment(BaseModel):
    """The outcome of one `RiskAnalyticsService.assess_portfolio()` run."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    overall_risk_score: float = Field(ge=0, le=100)
    overall_severity: RiskSeverity
    risk_metrics: tuple[RiskMetric, ...] = Field(default_factory=tuple)
    exposures: tuple[PortfolioExposure, ...] = Field(default_factory=tuple)
    recommendations: tuple[str, ...] = Field(default_factory=tuple)
    summary: str
    market_data_coverage: MarketDataCoverage = Field(
        default_factory=lambda: MarketDataCoverage(status=MarketDataCoverageStatus.NOT_EVALUATED)
    )
    generated_at: datetime
