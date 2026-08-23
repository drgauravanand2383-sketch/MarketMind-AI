"""Domain models for the Portfolio Recommendation Engine.

This engine performs no trade execution, no automatic rebalancing, no
portfolio optimization, no advanced risk calculation, no broker
connection, and no live market data fetch. It consumes already-computed
outputs from other subsystems — `app.screening.models.ScreenResult`,
`app.signals.models.SignalResult`, `app.alerts.models.Alert`,
`app.agents.company_research.models.CompanyResearchReport`,
`app.agents.portfolio_intelligence.models.CompanySummary` — and merges,
scores, ranks, and explains candidates from them. It never calls into any
of those subsystems itself (see `app.recommendations.engine`'s own
docstring): every evidence object is supplied by the caller, already
computed elsewhere, exactly like `app.alerts.engine.AlertService` consumes
an already-computed `SignalResult` rather than running Signal Detection
itself (Sprint 48's own precedent).

Design note — additive `CandidateEvidence`: no single existing subsystem
output carries every field a recommendation might draw from (a
`ScreenResult` doesn't carry research confidence; a `CompanyResearchReport`
doesn't carry signals). `CandidateEvidence` is the per-candidate bundle of
already-computed subsystem outputs this engine scores from — additive,
not in the sprint's literal Domain Models list, introduced because
"consume normalized domain models from existing subsystems" and "generate
recommendation candidates" are both structurally meaningless without a
place to hold that per-candidate bundle. Flagged per this codebase's
established precedent (`MarketDataSnapshot`, Sprint 47).

Design note — score component derivation and scale: `screening_score`
(`ScreenResult.score`) and signal/alert scores (`SignalResult.score`/
`Alert.score`) are already on a 0–100 scale from their own engines.
`CompanyResearchReport.confidence_summary.overall_confidence` and
`CompanySummary.overall_confidence` are on a 0.0–1.0 scale (see
`app.services.market_intelligence.engine`'s own confidence formula, which
caps at 1.0) — both are multiplied by 100 here so every component is
comparable on the same 0–100 scale before weighting. `planning_score` has
no source at all: the Planning Engine (Sprint 43) builds execution plans,
not company scores, so there is nothing in its output to extract a score
from. `CandidateEvidence.planning_score` is therefore accepted as a
directly-supplied, already-0–100 value — how a caller derives it (e.g.
whether the ticker's research plan executed successfully) is outside this
engine's scope.

Design note — additive `RecommendationCandidate.signal_score`/
`alert_score`: the sprint's own Scoring section names six suggested
weighted components (Planning, Screening, Signals, Research, Portfolio
Intelligence, Alerts), but the literal `RecommendationCandidate` field
list only names four `_score` fields (`screening_score`, `planning_score`,
`research_score`, `portfolio_score`) — `supporting_signals`/
`supporting_alerts` carry the raw evidence, but nothing carries their
*numeric* contribution. Two additive fields fill that gap, flagged per the
same established precedent above; omitting them would make the "six
configurable weighted components" requirement unauditable from the output
alone.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.agents.company_research.models import CompanyResearchReport
from app.agents.portfolio_intelligence.models import CompanySummary
from app.alerts.models import Alert
from app.screening.models import ScreenResult
from app.services.market_snapshot.models import MarketSnapshotResult, MarketSnapshotStatus
from app.signals.models import SignalResult

__all__ = [
    "RecommendationType",
    "MarketContribution",
    "ScoringWeights",
    "RecommendationThresholds",
    "CandidateEvidence",
    "RecommendationRequest",
    "RecommendationCandidate",
    "RecommendationSummary",
    "RecommendationResult",
]


class RecommendationType(StrEnum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    WATCH = "WATCH"
    HOLD = "HOLD"
    AVOID = "AVOID"


MarketContribution = Literal["direct", "indirect", "none"]
"""Whether live market data (Milestone 13) informed one
`RecommendationCandidate` — always computed, never a hidden/opaque
signal (§7's own "no hidden weighting... all scoring contributions must
remain inspectable" requirement):

- `"direct"`: `CandidateEvidence.market_snapshot` was supplied for this
  ticker and its status was `FRESH`/`STALE` (real data, just possibly
  aging — never `ENTITY_NOT_MAPPED` or a provider-failure status).
- `"indirect"`: no direct market snapshot, but at least one of the
  candidate's `supporting_signals` was evaluated against a
  `"quote.*"`-namespaced `SignalCondition` (Milestone 13's Signal
  Detection integration — see `app.services.portfolio_market_snapshot`'s
  signal adapter) — i.e. market data reached this candidate through
  Signal Detection, the one real existing pathway (this codebase's
  Signals engine is upstream of Recommendations; Risk is downstream of
  Recommendations and cannot feed back into it, so "indirectly through
  risk" — as this milestone's own prose names it — is not a real
  pathway in this architecture; "indirectly through signals" is the
  literal, honest equivalent, flagged here as a documented
  interpretation).
- `"none"`: neither applies — this candidate's score is exactly what it
  would have been without Milestone 14.
"""


class ScoringWeights(BaseModel):
    """Configurable per-component weights used to compute a candidate's
    weighted `overall_score`. Every weight must be positive (the sprint's
    own "Positive weights" validation requirement) — a component a caller
    wants to exclude from scoring is simply left absent on the
    `CandidateEvidence` (its score is `None`), not given a zero weight; see
    `app.recommendations.engine` for how weights are renormalized across
    only the components actually present for a given candidate (the
    sprint's own "Weights total configurable" requirement — the raw sum of
    configured weights need not equal any particular total, since scoring
    always normalizes by whatever subset of weights is available).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    planning: float = Field(default=1.0, gt=0)
    screening: float = Field(default=1.0, gt=0)
    signals: float = Field(default=1.0, gt=0)
    research: float = Field(default=1.0, gt=0)
    portfolio: float = Field(default=1.0, gt=0)
    alerts: float = Field(default=1.0, gt=0)


class RecommendationThresholds(BaseModel):
    """Configurable score cut-points classifying a candidate's
    `overall_score` into a `RecommendationType`. Represented as four
    strictly descending minimum-score boundaries (not five `[low, high]`
    pairs) — a single ordered set of cut-points across one 0–100 scale can
    never produce a gap or an overlap by construction, directly satisfying
    the sprint's "No overlapping threshold ranges" requirement. A score
    `>= strong_buy_min` is `STRONG_BUY`; `>= buy_min` (and below
    `strong_buy_min`) is `BUY`; and so on down to `AVOID` for anything
    below `hold_min`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    strong_buy_min: float = Field(default=90.0, ge=0, le=100)
    buy_min: float = Field(default=75.0, ge=0, le=100)
    watch_min: float = Field(default=60.0, ge=0, le=100)
    hold_min: float = Field(default=40.0, ge=0, le=100)

    @model_validator(mode="after")
    def _validate_strictly_descending(self) -> RecommendationThresholds:
        if not (self.strong_buy_min > self.buy_min > self.watch_min > self.hold_min):
            raise ValueError(
                "Thresholds must be strictly descending: "
                "strong_buy_min > buy_min > watch_min > hold_min."
            )
        return self

    def classify(self, score: float) -> RecommendationType:
        if score >= self.strong_buy_min:
            return RecommendationType.STRONG_BUY
        if score >= self.buy_min:
            return RecommendationType.BUY
        if score >= self.watch_min:
            return RecommendationType.WATCH
        if score >= self.hold_min:
            return RecommendationType.HOLD
        return RecommendationType.AVOID


class CandidateEvidence(BaseModel):
    """One candidate's bundle of already-computed subsystem outputs. See
    the module docstring for why this exists and how each score component
    is derived from it."""

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    company_name: str | None = None
    country: str | None = None
    sector: str | None = None
    industry: str | None = None
    screening_result: ScreenResult | None = None
    signals: tuple[SignalResult, ...] = Field(default_factory=tuple)
    alerts: tuple[Alert, ...] = Field(default_factory=tuple)
    research_report: CompanyResearchReport | None = None
    portfolio_summary: CompanySummary | None = None
    planning_score: float | None = Field(default=None, ge=0, le=100)
    market_snapshot: MarketSnapshotResult | None = None
    """Milestone 13 market data for this ticker, supplied by the caller
    — this engine never fetches market data itself, exactly like every
    other evidence field above. Purely additive: `None` (the default)
    reproduces this model's exact pre-Milestone-14 shape and behavior."""

    @field_validator("ticker")
    @classmethod
    def _normalize_ticker(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("ticker must not be blank.")
        return normalized


class RecommendationRequest(BaseModel):
    """A request to generate portfolio recommendations, referencing
    (never resolving/fetching — see module docstring) whichever upstream
    subsystem records inform it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    request_name: str = Field(min_length=1)
    watchlist_ids: tuple[str, ...] = Field(default_factory=tuple)
    screening_profile_ids: tuple[str, ...] = Field(default_factory=tuple)
    signal_definition_ids: tuple[str, ...] = Field(default_factory=tuple)
    alert_rule_ids: tuple[str, ...] = Field(default_factory=tuple)
    planning_context: dict[str, Any] = Field(default_factory=dict)
    max_recommendations: int = Field(default=10, ge=1)
    minimum_score: float = Field(default=0.0, ge=0, le=100)
    created_at: datetime


class RecommendationCandidate(BaseModel):
    """One scored, ranked, explainable recommendation candidate.

    `market_price`/`market_change_percent`/`market_freshness` (Milestone
    14) are flat scalars, deliberately not nested inside
    `market_snapshot` alone — `app.strategy.models.StrategyRule.field`
    derives its allowed field set generically from this model's own
    field names (`getattr(candidate, rule.field)`), and a strategy rule
    needs a directly-comparable scalar to reference (mirrors §6's own
    example list: "current price, percentage change, market status").
    `market_snapshot` itself carries full provenance (§21) but is
    excluded from strategy rules — see
    `app.strategy.models._STRATEGY_RULE_FIELDS`.
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str
    company_name: str | None = None
    country: str | None = None
    sector: str | None = None
    industry: str | None = None
    overall_score: float
    confidence: float
    recommendation: RecommendationType
    reasoning: str
    supporting_signals: tuple[SignalResult, ...] = Field(default_factory=tuple)
    supporting_alerts: tuple[Alert, ...] = Field(default_factory=tuple)
    screening_score: float | None = None
    planning_score: float | None = None
    research_score: float | None = None
    portfolio_score: float | None = None
    signal_score: float | None = None
    alert_score: float | None = None
    market_price: float | None = None
    market_change_percent: float | None = None
    market_freshness: MarketSnapshotStatus | None = None
    market_snapshot: MarketSnapshotResult | None = None
    market_contribution: MarketContribution = "none"
    created_at: datetime


class RecommendationSummary(BaseModel):
    """A breakdown of one `RecommendationResult`'s candidates by type, plus aggregate statistics."""

    model_config = ConfigDict(extra="forbid")

    strong_buy: int = 0
    buy: int = 0
    watch: int = 0
    hold: int = 0
    avoid: int = 0
    average_score: float = 0.0
    average_confidence: float = 0.0


class RecommendationResult(BaseModel):
    """The outcome of one `PortfolioRecommendationService.generate_recommendations()` run."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    generated_at: datetime
    total_candidates: int
    recommendations: tuple[RecommendationCandidate, ...] = Field(default_factory=tuple)
    summary: RecommendationSummary
