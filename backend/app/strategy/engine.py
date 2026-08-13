"""StrategyEvaluationService: the Strategy Evaluation Engine's Application layer.

Evaluates already-generated `app.recommendations.models.RecommendationResult`
output against configurable `InvestmentStrategy` definitions — never
optimizes an allocation, never executes a trade, never calculates
portfolio risk, never rebalances, and never fetches market data. Combines
strategy management (delegated to an injected `BaseStrategyRepository`)
with evaluation (population-level rule/weighting scoring — see
`app.strategy.models`'s own module docstring for the algorithm). No
globals, no singleton: every dependency is injected at construction time.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable

from app.recommendations.models import RecommendationCandidate, RecommendationResult
from app.strategy.exceptions import (
    DuplicateStrategyNameError,
    MaxStrategiesExceededError,
    MaxStrategyRulesExceededError,
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
    StrategyWeighting,
)

if TYPE_CHECKING:
    from app.repositories.strategy.repository import BaseStrategyRepository

__all__ = ["StrategyEvaluationService"]

DEFAULT_MAX_STRATEGIES = 100
DEFAULT_MAX_RULES = 100

_WEIGHTING_FIELDS = (
    "overall_score",
    "screening_score",
    "planning_score",
    "research_score",
    "portfolio_score",
    "signal_score",
    "alert_score",
)


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


class StrategyEvaluationService:
    def __init__(
        self,
        repository: BaseStrategyRepository,
        *,
        max_strategies: int = DEFAULT_MAX_STRATEGIES,
        max_rules: int = DEFAULT_MAX_RULES,
        enforce_unique_names: bool = True,
        now_fn: Callable[[], datetime] = _default_now,
    ) -> None:
        self._repository = repository
        self._max_strategies = max_strategies
        self._max_rules = max_rules
        self._enforce_unique_names = enforce_unique_names
        self._now_fn = now_fn

    # --- Strategy management -----------------------------------------------------------

    async def create_strategy(
        self,
        name: str,
        *,
        description: str = "",
        strategy_type: str = "CUSTOM",
        enabled: bool = True,
        weightings: StrategyWeighting = StrategyWeighting(),
        rules: tuple[StrategyRule, ...] = (),
    ) -> InvestmentStrategy:
        """Create a new strategy.

        Raises:
            MaxStrategiesExceededError: creating this strategy would exceed the configured maximum.
            MaxStrategyRulesExceededError: `len(rules)` exceeds the configured maximum.
            DuplicateStrategyNameError: `name` is already in use (only
                when `enforce_unique_names=True`, the default).
        """
        await self._check_strategy_count()
        self._check_rule_count(None, rules)
        await self._check_unique_name(name)

        now = self._now_fn()
        strategy = InvestmentStrategy(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
            strategy_type=strategy_type,
            enabled=enabled,
            weightings=weightings,
            rules=rules,
            created_at=now,
            updated_at=now,
        )
        return await self._repository.create_strategy(strategy)

    async def update_strategy(self, strategy: InvestmentStrategy) -> InvestmentStrategy:
        """Replace an existing strategy's stored state with `strategy` (same id).

        Raises:
            StrategyNotFoundError: no strategy exists for `strategy.id`.
            MaxStrategyRulesExceededError: `len(strategy.rules)` exceeds the configured maximum.
            DuplicateStrategyNameError: `strategy.name` is already in use
                by a *different* strategy (only when `enforce_unique_names=True`).
        """
        self._check_rule_count(strategy.id, strategy.rules)
        await self._check_unique_name(strategy.name, ignore_strategy_id=strategy.id)

        updated = strategy.model_copy(update={"updated_at": self._now_fn()})
        result = await self._repository.update_strategy(updated)
        if result is None:
            raise StrategyNotFoundError(strategy.id)
        return result

    async def delete_strategy(self, strategy_id: str) -> None:
        """Raises `StrategyNotFoundError` if no strategy exists for `strategy_id`."""
        deleted = await self._repository.delete_strategy(strategy_id)
        if not deleted:
            raise StrategyNotFoundError(strategy_id)

    async def list_strategies(self) -> list[InvestmentStrategy]:
        return await self._repository.list_strategies()

    async def get_strategy(self, strategy_id: str) -> InvestmentStrategy:
        """Raises `StrategyNotFoundError` if no strategy exists for `strategy_id`."""
        strategy = await self._repository.get_strategy(strategy_id)
        if strategy is None:
            raise StrategyNotFoundError(strategy_id)
        return strategy

    async def duplicate_strategy(self, strategy_id: str, new_name: str) -> InvestmentStrategy:
        """Copy an existing strategy's weightings/rules into a new strategy.

        Raises:
            StrategyNotFoundError: no strategy exists for `strategy_id`.
            MaxStrategiesExceededError: creating the copy would exceed the configured maximum.
            DuplicateStrategyNameError: `new_name` is already in use
                (only when `enforce_unique_names=True`).
        """
        await self._check_strategy_count()
        await self._check_unique_name(new_name)
        result = await self._repository.duplicate_strategy(strategy_id, str(uuid.uuid4()), new_name)
        if result is None:
            raise StrategyNotFoundError(strategy_id)
        return result

    async def get_evaluation(self, request_id: str) -> StrategyEvaluationResult:
        """Raises `StrategyEvaluationNotFoundError` if no result exists for `request_id`."""
        result = await self._repository.get_evaluation(request_id)
        if result is None:
            raise StrategyEvaluationNotFoundError(request_id)
        return result

    async def list_evaluations(self) -> list[StrategyEvaluationResult]:
        return await self._repository.list_evaluations()

    async def _check_strategy_count(self) -> None:
        existing = len(await self._repository.list_strategies())
        if existing >= self._max_strategies:
            raise MaxStrategiesExceededError(limit=self._max_strategies, actual=existing + 1)

    def _check_rule_count(self, strategy_id: str | None, rules: tuple[StrategyRule, ...]) -> None:
        if len(rules) > self._max_rules:
            raise MaxStrategyRulesExceededError(strategy_id, limit=self._max_rules, actual=len(rules))

    async def _check_unique_name(self, name: str, *, ignore_strategy_id: str | None = None) -> None:
        if not self._enforce_unique_names:
            return
        for existing in await self._repository.list_strategies():
            if existing.name == name and existing.id != ignore_strategy_id:
                raise DuplicateStrategyNameError(name)

    # --- Evaluation -----------------------------------------------------------

    def evaluate_strategy(
        self, recommendation_result: RecommendationResult, strategy: InvestmentStrategy
    ) -> StrategyMatch:
        """Evaluate one strategy against a whole `RecommendationResult`,
        population-level (not per-candidate — see `app.strategy.models`'s
        module docstring). Pure and synchronous — no I/O, no market data,
        no AI reasoning.
        """
        candidates = recommendation_result.recommendations
        enabled_rules = [rule for rule in strategy.rules if rule.enabled]

        avg_component_score, weighting_covered, weighting_possible = _component_alignment(
            candidates, strategy.weightings
        )
        rule_alignments = [_evaluate_rule_population(rule, candidates) for rule in enabled_rules]
        rule_match_score, rule_covered, rule_possible = _rule_alignment_summary(rule_alignments, candidates)

        alignment_score = _blend_scores(avg_component_score, rule_match_score)
        confidence = _coverage_confidence(
            weighting_covered + rule_covered, weighting_possible + rule_possible
        )

        matched_rules = tuple(ra for ra in rule_alignments if ra.pass_rate >= 0.5)
        failed_rules = tuple(ra for ra in rule_alignments if ra.pass_rate < 0.5)

        return StrategyMatch(
            strategy_id=strategy.id,
            strategy_name=strategy.name,
            alignment_score=alignment_score,
            confidence=confidence,
            matched_rules=matched_rules,
            failed_rules=failed_rules,
            reasoning=_build_reasoning(
                avg_component_score, rule_match_score, len(matched_rules), len(failed_rules), alignment_score, confidence
            ),
        )

    async def evaluate_recommendations(
        self,
        request: StrategyEvaluationRequest,
        recommendation_result: RecommendationResult,
        strategies: list[InvestmentStrategy],
    ) -> StrategyEvaluationResult:
        """Evaluate every enabled strategy in `strategies` against
        `recommendation_result`, rank by alignment score descending (ties
        broken by strategy name, ascending — fully deterministic
        regardless of `strategies`' input order), and select the best.
        The generated result is persisted before being returned.
        """
        matches = [
            self.evaluate_strategy(recommendation_result, strategy)
            for strategy in strategies
            if strategy.enabled
        ]
        ranked = sorted(matches, key=lambda match: (-match.alignment_score, match.strategy_name))

        result = StrategyEvaluationResult(
            request_id=request.id,
            evaluated_at=self._now_fn(),
            overall_alignment=ranked[0].alignment_score if ranked else 0.0,
            best_strategy=ranked[0].strategy_id if ranked else None,
            strategy_matches=tuple(ranked),
            summary=_build_summary(ranked),
        )
        return await self._repository.store_evaluation(result)


def _component_alignment(
    candidates: tuple[RecommendationCandidate, ...], weighting: StrategyWeighting
) -> tuple[float | None, int, int]:
    """Weighted-average each candidate's own score fields (renormalized
    per candidate across whichever are present — mirrors
    `app.recommendations.engine._weighted_score`, Sprint 49), then average
    across the population. Returns `(avg_component_score, covered_count,
    possible_count)` for confidence accounting."""
    weight_map = {name: getattr(weighting, name) for name in _WEIGHTING_FIELDS}
    per_candidate_scores: list[float] = []
    covered = 0

    for candidate in candidates:
        available = [
            (name, getattr(candidate, name))
            for name in _WEIGHTING_FIELDS
            if getattr(candidate, name) is not None
        ]
        covered += len(available)
        if not available:
            continue
        total_weight = sum(weight_map[name] for name, _ in available)
        weighted_sum = sum(weight_map[name] * value for name, value in available)
        per_candidate_scores.append(weighted_sum / total_weight)

    possible = len(candidates) * len(_WEIGHTING_FIELDS)
    if not per_candidate_scores:
        return None, covered, possible
    return round(sum(per_candidate_scores) / len(per_candidate_scores), 2), covered, possible


def _evaluate_rule_population(
    rule: StrategyRule, candidates: tuple[RecommendationCandidate, ...]
) -> RuleAlignment:
    outcomes = [_evaluate_rule_against_candidate(rule, candidate) for candidate in candidates]
    evaluable = [outcome for outcome in outcomes if outcome is not None]
    passed = sum(1 for outcome in evaluable if outcome)

    if evaluable:
        pass_rate = round(passed / len(evaluable), 4)
        reason = f"{rule.field} {rule.operator.value} {rule.value!r}: {passed}/{len(evaluable)} evaluable candidates passed."
    else:
        pass_rate = 0.0
        reason = f"{rule.field} was not present on any candidate in this recommendation result."

    return RuleAlignment(
        rule_id=rule.id,
        field=rule.field,
        operator=rule.operator,
        weight=rule.weight,
        pass_rate=pass_rate,
        evaluated_candidate_count=len(evaluable),
        reason=reason,
    )


def _evaluate_rule_against_candidate(rule: StrategyRule, candidate: RecommendationCandidate) -> bool | None:
    actual = getattr(candidate, rule.field, None)
    if actual is None:
        return None
    return _apply_operator(rule.operator, actual, rule.value)


def _apply_operator(operator: StrategyOperator, actual: Any, expected: Any) -> bool:
    if operator == StrategyOperator.EQUALS:
        return actual == expected
    if operator == StrategyOperator.NOT_EQUALS:
        return actual != expected
    if operator == StrategyOperator.GREATER_THAN:
        return actual > expected
    if operator == StrategyOperator.GREATER_EQUAL:
        return actual >= expected
    if operator == StrategyOperator.LESS_THAN:
        return actual < expected
    if operator == StrategyOperator.LESS_EQUAL:
        return actual <= expected
    if operator == StrategyOperator.BETWEEN:
        low, high = expected
        return low <= actual <= high
    if operator == StrategyOperator.IN:
        return actual in expected
    return actual not in expected  # StrategyOperator.NOT_IN


def _rule_alignment_summary(
    rule_alignments: list[RuleAlignment], candidates: tuple[RecommendationCandidate, ...]
) -> tuple[float | None, int, int]:
    """Weighted average of each rule's population pass rate (×100),
    renormalized across the rules that had it. Returns `(rule_match_score,
    covered_count, possible_count)` for confidence accounting — a rule
    never evaluable against any candidate contributes 0 coverage."""
    if not rule_alignments:
        return None, 0, 0

    total_weight = sum(ra.weight for ra in rule_alignments)
    weighted_sum = sum(ra.weight * ra.pass_rate * 100 for ra in rule_alignments)
    rule_match_score = round(weighted_sum / total_weight, 2)

    covered = sum(ra.evaluated_candidate_count for ra in rule_alignments)
    possible = len(rule_alignments) * len(candidates)
    return rule_match_score, covered, possible


def _blend_scores(component_score: float | None, rule_score: float | None) -> float:
    """`alignment_score` is a plain average of `weightings`' component
    score and `rules`' population match score when both are computable —
    the sprint's own field list provides exactly two configurable scoring
    inputs (`weightings`, `rules`) and no third blend-ratio knob, so a
    documented, flagged, unweighted average is the simplest way to combine
    them (mirrors similarly-flagged formulas in `app.signals.engine` and
    `app.alerts.engine`). Either side alone is used directly when the
    other has no usable data; zero evidence at all yields 0.
    """
    if component_score is not None and rule_score is not None:
        return round((component_score + rule_score) / 2, 2)
    if component_score is not None:
        return component_score
    if rule_score is not None:
        return rule_score
    return 0.0


def _coverage_confidence(covered: int, possible: int) -> float:
    """Confidence reflects evidence *coverage*, not opportunity quality —
    the fraction of (candidate x weighting-field) and (candidate x rule)
    slots that actually had usable data. Mirrors
    `app.recommendations.engine._confidence`'s identical philosophy
    (Sprint 49)."""
    if possible == 0:
        return 0.0
    return round(covered / possible * 100, 2)


def _build_reasoning(
    component_score: float | None,
    rule_score: float | None,
    matched_count: int,
    failed_count: int,
    alignment_score: float,
    confidence: float,
) -> str:
    parts = [f"Alignment {alignment_score}% (confidence {confidence}%)"]
    if component_score is not None:
        parts.append(f"component score {component_score}%")
    if rule_score is not None:
        total_rules = matched_count + failed_count
        parts.append(f"{matched_count} of {total_rules} rule(s) matched population-wide (rule score {rule_score}%)")
    return "; ".join(parts) + "."


def _build_summary(matches: list[StrategyMatch]) -> StrategySummary:
    if not matches:
        return StrategySummary()
    return StrategySummary(
        total_strategies=len(matches),
        best_alignment=max(match.alignment_score for match in matches),
        average_alignment=round(sum(match.alignment_score for match in matches) / len(matches), 2),
        highest_confidence=max(match.confidence for match in matches),
    )
