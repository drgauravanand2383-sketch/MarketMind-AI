"""Domain models for the Strategy Evaluation Engine.

Evaluates already-generated `app.recommendations.models.RecommendationResult`
output (Sprint 49) against configurable `InvestmentStrategy` definitions —
never fetches market data, never optimizes an allocation, never
calculates portfolio risk, never rebalances, and never executes a trade.
Like every evaluation engine since Sprint 47, this one never calls into
the Recommendation Engine (or any other subsystem) itself: the caller
supplies an already-computed `RecommendationResult`, mirroring exactly how
`app.recommendations.engine.PortfolioRecommendationService` (Sprint 49)
consumes already-computed `CandidateEvidence` rather than invoking
Screening/Signal Detection/Alerts itself.

Design note — population-level (not per-candidate) evaluation: the
sprint's literal `StrategyMatch` field list has no per-candidate identity
field (no `ticker`) — only `strategy_id`/`strategy_name` plus one
`alignment_score`/`confidence`/`matched_rules`/`failed_rules`/`reasoning`
set. "How well recommendations [plural] align with a strategy" is
therefore evaluated at the level of the whole `RecommendationResult`
population, not per individual `RecommendationCandidate`: each
`StrategyRule` is checked against every candidate, and a rule's
contribution is that *population pass rate* (the fraction of candidates,
among those where the referenced field was present, that satisfied it) —
not a single pass/fail. See `app.strategy.engine` for the full algorithm.

Design note — `StrategyWeighting` and `rules` are two independent,
complementary scoring inputs, not a redundant pair: `weightings` blends a
candidate's own already-computed score fields (`overall_score`,
`screening_score`, etc. — the same shape as
`app.recommendations.models.ScoringWeights`, Sprint 49, but keyed to
`RecommendationCandidate`'s fields rather than `CandidateEvidence`'s),
while `rules` are explicit threshold/membership conditions (mirrors
`app.alerts.models.AlertCondition`, Sprint 48). The two are combined into
one final `alignment_score`; see the module's scoring design note below
and `app.strategy.engine` for the exact formula — no third configurable
blend ratio is introduced beyond the two the sprint's own field list
provides (`weightings`, `rules`), so the blend is a plain, documented,
flagged average of the two, each falling back to the other alone when one
side has no usable data.

Design note — additive `RuleAlignment`: `StrategyMatch.matched_rules`/
`failed_rules` need *some* element type to carry population-level
per-rule detail (which rule, its pass rate, how many candidates it was
even evaluable against, why) — `RuleAlignment` is that type, additive per
this codebase's established precedent (`ConditionEvaluation`, Sprints
47-48), introduced because "Explainability" (an explicit capability of
this sprint's Strategy Evaluation Engine) is otherwise unimplementable at
the rule level.

Design note — no AND/OR/nested rule logic: like `app.alerts.models`
(Sprint 48), this sprint's own Strategy Evaluation Engine capabilities
list has no AND/OR/nested-evaluation requirement. `rules` are independent,
individually weighted, and combined by weighted-average pass rate — never
gated behind a boolean AND/OR tree. `StrategyMatch` correspondingly has no
boolean "matched"/"triggered" field, only continuous `alignment_score`/
`confidence` — this is a scoring engine, not a gate.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.recommendations.models import RecommendationCandidate

__all__ = [
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
]


class StrategyOperator(str, Enum):
    EQUALS = "EQUALS"
    NOT_EQUALS = "NOT_EQUALS"
    GREATER_THAN = "GREATER_THAN"
    GREATER_EQUAL = "GREATER_EQUAL"
    LESS_THAN = "LESS_THAN"
    LESS_EQUAL = "LESS_EQUAL"
    BETWEEN = "BETWEEN"
    IN = "IN"
    NOT_IN = "NOT_IN"


class StrategyType(str, Enum):
    VALUE = "VALUE"
    GROWTH = "GROWTH"
    DIVIDEND = "DIVIDEND"
    QUALITY = "QUALITY"
    MOMENTUM = "MOMENTUM"
    BALANCED = "BALANCED"
    INCOME = "INCOME"
    CUSTOM = "CUSTOM"


_STRATEGY_RULE_FIELDS: frozenset[str] = frozenset(
    name
    for name in RecommendationCandidate.model_fields
    if name not in {"supporting_signals", "supporting_alerts", "market_snapshot"}
)

_WEIGHTING_FIELDS = (
    "overall_score",
    "screening_score",
    "planning_score",
    "research_score",
    "portfolio_score",
    "signal_score",
    "alert_score",
)

_LIST_LIKE_OPERATORS = frozenset({StrategyOperator.IN, StrategyOperator.NOT_IN})


class StrategyWeighting(BaseModel):
    """Configurable weights blending a candidate's own already-computed
    score fields into one component score. Every weight must be positive
    — the sprint's own "Positive weights" requirement; a component a
    strategy doesn't care about is simply absent from a given candidate
    (its score field is `None`), not given a zero weight (mirrors
    `app.recommendations.models.ScoringWeights`'s identical reasoning,
    Sprint 49)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    overall_score: float = Field(default=1.0, gt=0)
    screening_score: float = Field(default=1.0, gt=0)
    planning_score: float = Field(default=1.0, gt=0)
    research_score: float = Field(default=1.0, gt=0)
    portfolio_score: float = Field(default=1.0, gt=0)
    signal_score: float = Field(default=1.0, gt=0)
    alert_score: float = Field(default=1.0, gt=0)


class StrategyRule(BaseModel):
    """One strategy condition: `field` `operator` `value`, evaluated
    against a `RecommendationCandidate`. `field` must be one of
    `RecommendationCandidate`'s own scalar field names — its two
    tuple-typed fields (`supporting_signals`/`supporting_alerts`) and its
    nested `market_snapshot` (Milestone 14) are not comparable by a single
    operator/value pair and are excluded. Milestone 14's flat scalar
    fields (`market_price`, `market_change_percent`, `market_freshness`,
    `market_contribution`) remain usable here with no engine changes,
    exactly like every other `RecommendationCandidate` scalar field — see
    `docs/architecture/PORTFOLIO_INTELLIGENCE.md`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    field: str = Field(min_length=1)
    operator: StrategyOperator
    value: Any = None
    weight: float = Field(default=1.0, gt=0)
    enabled: bool = True

    @model_validator(mode="after")
    def _validate_field_and_value(self) -> StrategyRule:
        if self.field not in _STRATEGY_RULE_FIELDS:
            raise ValueError(
                f"Rule {self.id!r} references unknown field {self.field!r}. "
                f"Expected one of {sorted(_STRATEGY_RULE_FIELDS)!r}."
            )

        if self.operator == StrategyOperator.BETWEEN:
            if not isinstance(self.value, (list, tuple)) or len(self.value) != 2:
                raise ValueError(f"Rule {self.id!r}: BETWEEN requires a value of exactly [low, high].")
            low, high = self.value
            if low is None or high is None:
                raise ValueError(f"Rule {self.id!r}: BETWEEN bounds must not be None.")
            if low > high:
                raise ValueError(
                    f"Rule {self.id!r}: BETWEEN low bound {low!r} exceeds high bound {high!r}."
                )
        elif self.operator in _LIST_LIKE_OPERATORS:
            if not isinstance(self.value, (list, tuple)) or len(self.value) == 0:
                raise ValueError(
                    f"Rule {self.id!r}: {self.operator.value} requires a non-empty list of values."
                )
        elif self.value is None:
            raise ValueError(f"Rule {self.id!r}: {self.operator.value} requires a value.")

        return self


class InvestmentStrategy(BaseModel):
    """A named, reusable investment strategy: a component-score weighting
    plus a set of independently-weighted rules (see module docstring for
    how the two combine)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    strategy_type: StrategyType = StrategyType.CUSTOM
    enabled: bool = True
    weightings: StrategyWeighting = Field(default_factory=StrategyWeighting)
    rules: tuple[StrategyRule, ...] = Field(default_factory=tuple)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _validate_rules(self) -> InvestmentStrategy:
        seen_ids: set[str] = set()
        for rule in self.rules:
            if rule.id in seen_ids:
                raise ValueError(f"Duplicate rule id {rule.id!r}.")
            seen_ids.add(rule.id)
        return self


class StrategyEvaluationRequest(BaseModel):
    """A request to evaluate one `RecommendationResult` (referenced, never
    fetched — see module docstring) against one or more strategies."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    strategy_ids: tuple[str, ...] = Field(default_factory=tuple)
    recommendation_result_id: str = Field(min_length=1)
    created_at: datetime


class RuleAlignment(BaseModel):
    """One `StrategyRule`'s population-level outcome: the fraction of
    candidates (among those where the field was present) that satisfied
    it."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    field: str
    operator: StrategyOperator
    weight: float
    pass_rate: float
    evaluated_candidate_count: int
    reason: str


class StrategyMatch(BaseModel):
    """One strategy's alignment outcome against a whole `RecommendationResult`."""

    model_config = ConfigDict(extra="forbid")

    strategy_id: str
    strategy_name: str
    alignment_score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=100)
    matched_rules: tuple[RuleAlignment, ...] = Field(default_factory=tuple)
    failed_rules: tuple[RuleAlignment, ...] = Field(default_factory=tuple)
    reasoning: str


class StrategySummary(BaseModel):
    """A breakdown of one `StrategyEvaluationResult`'s strategy matches."""

    model_config = ConfigDict(extra="forbid")

    total_strategies: int = 0
    best_alignment: float = 0.0
    average_alignment: float = 0.0
    highest_confidence: float = 0.0


class StrategyEvaluationResult(BaseModel):
    """The outcome of one `StrategyEvaluationService.evaluate_recommendations()` run."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    evaluated_at: datetime
    overall_alignment: float = Field(ge=0, le=100)
    best_strategy: str | None = None
    strategy_matches: tuple[StrategyMatch, ...] = Field(default_factory=tuple)
    summary: StrategySummary
