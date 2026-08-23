"""ExplainabilityService: the Explainability & Performance Attribution
Engine's Application layer.

Explains already-computed `RecommendationResult`/`StrategyEvaluationResult`/
`RiskAssessment`/`BacktestRun`+`BacktestResult` output — never recomputes
a score, never alters a historical backtest result, never fetches market
data, never executes a trade, and never optimizes a portfolio. Combines
request/result management (delegated to an injected
`BaseExplainabilityRepository`) with explanation generation (pure,
deterministic given its inputs — no randomness, no wall-clock dependency
beyond the injected `now_fn` used purely for bookkeeping timestamps).

Reuse discipline — read-only invocation, exactly like Sprint 52's
`BacktestingService`: this service is constructed with the actual
`PortfolioRecommendationService`, `StrategyEvaluationService`,
`RiskAnalyticsService`, and `BacktestingService` instances injected, and
calls only their read-only `get_result`/`get_evaluation`/`get_assessment`/
`get_run` methods to resolve an `ExplainabilityRequest`'s referenced ids.
It never calls `generate_recommendations`/`evaluate_recommendations`/
`assess_portfolio`/`run_backtest` — explanation only ever looks up results
those engines already computed and persisted; it never re-runs their
scoring or replay.

Contribution attribution — the exact formula: every `ContributionBreakdown`
this service produces is a normalized, weighted share of a total, built
from already-computed 0-100 scores (never a fabricated number). Given a
`category -> raw_score` mapping and the configured `ExplainabilityWeighting`,
each category's `contribution_percent = (weight * raw_score) /
sum(weight * raw_score for every category) * contribution_total`, rounded,
descending by `contribution_percent` with a deterministic
`(category, source)` tiebreak, truncated to the configured `max_categories`.
`top_positive_factors`/`top_negative_factors` rank the same categories by
their *raw* score (not `contribution_percent`, which is always
non-negative and does not indicate whether a component was strong or
weak) — the highest-scoring `TOP_FACTORS_COUNT` categories are "positive"
(helped the outcome), the lowest-scoring are "negative" (hurt it).

Explanation sources, category by category:
  - `RecommendationExplanation`: `SCREENING`/`PLANNING`/`RESEARCH`/
    `PORTFOLIO_INTELLIGENCE`/`SIGNALS`/`ALERTS` from that candidate's own
    `screening_score`/`planning_score`/`research_score`/`portfolio_score`/
    `signal_score`/`alert_score` (each only included when present).
  - `StrategyExplanation.weight_breakdown`: one `STRATEGY`-category entry
    per rule in `matched_rules` + `failed_rules`, weighted by the rule's
    own `weight`.
  - `PerformanceAttribution.contribution_breakdown`: the mean of every
    resolved candidate's component scores (same six categories as
    `RecommendationExplanation`, averaged only over candidates where each
    component was present) plus, when resolved, `STRATEGY` (the strategy
    evaluation's `overall_alignment`), `RISK` (`100 -
    RiskAssessment.overall_risk_score`, inverted so higher consistently
    means "helped"), and `SECTOR`/`COUNTRY`/`INDUSTRY` (each of
    `RiskAssessment.exposures`, one entry per exposure bucket, weighted by
    that bucket's own `weight`).
  - `RiskExplanation.category_breakdown`/`exposure_breakdown`: copied
    verbatim from `RiskAssessment.risk_metrics`/`exposures` (re-sorted for
    ranking, never recalculated) — see `app.explainability.models`'s own
    docstring for why these don't use `ContributionBreakdown`.
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.backtesting.engine import BacktestingService
from app.backtesting.exceptions import BacktestResultNotFoundError, BacktestRunNotFoundError
from app.backtesting.models import BacktestResult, BacktestRun
from app.explainability.exceptions import (
    DuplicateExplainabilityRequestNameError,
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
from app.recommendations.engine import PortfolioRecommendationService
from app.recommendations.exceptions import RecommendationResultNotFoundError
from app.recommendations.models import RecommendationCandidate, RecommendationResult
from app.risk.engine import RiskAnalyticsService
from app.risk.exceptions import RiskAssessmentNotFoundError
from app.risk.models import RiskAssessment
from app.strategy.engine import StrategyEvaluationService
from app.strategy.exceptions import StrategyEvaluationNotFoundError
from app.strategy.models import StrategyEvaluationResult, StrategyMatch

if TYPE_CHECKING:
    from app.repositories.explainability.repository import BaseExplainabilityRepository

__all__ = ["ExplainabilityService"]

DEFAULT_MAX_CATEGORIES = 20
DEFAULT_CONTRIBUTION_TOTAL = 100.0
TOP_FACTORS_COUNT = 3

_PORTFOLIO_SOURCE = "Portfolio"

_COMPONENT_CATEGORY_FIELDS: tuple[tuple[AttributionCategory, str], ...] = (
    (AttributionCategory.SCREENING, "screening_score"),
    (AttributionCategory.PLANNING, "planning_score"),
    (AttributionCategory.RESEARCH, "research_score"),
    (AttributionCategory.PORTFOLIO_INTELLIGENCE, "portfolio_score"),
    (AttributionCategory.SIGNALS, "signal_score"),
    (AttributionCategory.ALERTS, "alert_score"),
)


def _default_now() -> datetime:
    return datetime.now(UTC)


class ExplainabilityService:
    def __init__(
        self,
        repository: BaseExplainabilityRepository,
        recommendation_service: PortfolioRecommendationService,
        strategy_service: StrategyEvaluationService,
        risk_service: RiskAnalyticsService,
        backtesting_service: BacktestingService,
        *,
        weighting: ExplainabilityWeighting = ExplainabilityWeighting(),
        contribution_total: float = DEFAULT_CONTRIBUTION_TOTAL,
        max_categories: int = DEFAULT_MAX_CATEGORIES,
        enforce_unique_names: bool = True,
        now_fn: Callable[[], datetime] = _default_now,
    ) -> None:
        self._repository = repository
        self._recommendation_service = recommendation_service
        self._strategy_service = strategy_service
        self._risk_service = risk_service
        self._backtesting_service = backtesting_service
        self._weighting = weighting
        self._contribution_total = contribution_total
        self._max_categories = max_categories
        self._enforce_unique_names = enforce_unique_names
        self._now_fn = now_fn

    # --- Request management -----------------------------------------------------------

    async def create_request(
        self,
        name: str,
        recommendation_result_id: str,
        *,
        strategy_evaluation_id: str | None = None,
        risk_assessment_id: str | None = None,
        backtest_run_id: str | None = None,
    ) -> ExplainabilityRequest:
        """Create a new explainability request.

        Raises:
            DuplicateExplainabilityRequestNameError: `name` is already in
                use (only when `enforce_unique_names=True`, the default).
        """
        await self._check_unique_name(name)
        request = ExplainabilityRequest(
            id=str(uuid.uuid4()),
            name=name,
            recommendation_result_id=recommendation_result_id,
            strategy_evaluation_id=strategy_evaluation_id,
            risk_assessment_id=risk_assessment_id,
            backtest_run_id=backtest_run_id,
            created_at=self._now_fn(),
        )
        return await self._repository.create_request(request)

    async def get_request(self, request_id: str) -> ExplainabilityRequest:
        """Raises `ExplainabilityRequestNotFoundError` if no request exists for `request_id`."""
        request = await self._repository.get_request(request_id)
        if request is None:
            raise ExplainabilityRequestNotFoundError(request_id)
        return request

    async def list_requests(self) -> list[ExplainabilityRequest]:
        return await self._repository.list_requests()

    async def get_result(self, request_id: str) -> ExplainabilityResult:
        """Raises `ExplainabilityResultNotFoundError` if no result exists for `request_id`."""
        result = await self._repository.get_result(request_id)
        if result is None:
            raise ExplainabilityResultNotFoundError(request_id)
        return result

    async def list_results(self) -> list[ExplainabilityResult]:
        return await self._repository.list_results()

    async def _check_unique_name(self, name: str) -> None:
        if not self._enforce_unique_names:
            return
        for existing in await self._repository.list_requests():
            if existing.name == name:
                raise DuplicateExplainabilityRequestNameError(name)

    # --- Per-item explanations -----------------------------------------------------------

    def explain_recommendation(self, candidate: RecommendationCandidate) -> RecommendationExplanation:
        category_scores = _candidate_category_scores(candidate)
        contributing = self._build_contribution_breakdown(candidate.ticker, category_scores)
        positive = _top_factors(category_scores, contributing, positive=True)
        negative = _top_factors(category_scores, contributing, positive=False)
        return RecommendationExplanation(
            ticker=candidate.ticker,
            company_name=candidate.company_name,
            overall_score=candidate.overall_score,
            confidence=candidate.confidence,
            contributing_components=contributing,
            top_positive_factors=positive,
            top_negative_factors=negative,
            reasoning=candidate.reasoning,
            summary=(
                f"{candidate.ticker}: overall score {candidate.overall_score} "
                f"({candidate.recommendation.value}), confidence {candidate.confidence}%. "
                f"{len(contributing)} contributing component(s)."
            ),
        )

    def explain_strategy(self, match: StrategyMatch) -> StrategyExplanation:
        all_rules = match.matched_rules + match.failed_rules
        total_weight = sum(rule.weight for rule in all_rules)
        entries = [
            ContributionBreakdown(
                source=match.strategy_name,
                category=AttributionCategory.STRATEGY,
                weight=rule.weight,
                contribution_percent=(
                    round((rule.weight / total_weight) * self._contribution_total, 4) if total_weight else 0.0
                ),
                description=(
                    f"Rule {rule.rule_id} ({rule.field} {rule.operator.value}): "
                    f"pass rate {round(rule.pass_rate * 100, 2)}%, weight {rule.weight}."
                ),
            )
            for rule in all_rules
        ]
        entries.sort(key=lambda entry: (-entry.contribution_percent, entry.description))
        return StrategyExplanation(
            strategy_name=match.strategy_name,
            alignment_score=match.alignment_score,
            matched_rules=match.matched_rules,
            failed_rules=match.failed_rules,
            weight_breakdown=tuple(entries[: self._max_categories]),
            summary=(
                f"{match.strategy_name}: alignment {match.alignment_score} "
                f"(confidence {match.confidence}%); {len(match.matched_rules)}/{len(all_rules)} rule(s) matched."
            ),
        )

    def explain_risk(self, assessment: RiskAssessment) -> RiskExplanation:
        category_breakdown = tuple(
            sorted(assessment.risk_metrics, key=lambda metric: (-metric.score, metric.metric_name))
        )
        severity_breakdown = dict(Counter(metric.severity for metric in assessment.risk_metrics))
        elevated = sum(1 for metric in assessment.risk_metrics if metric.severity.value in ("HIGH", "CRITICAL"))
        return RiskExplanation(
            overall_risk_score=assessment.overall_risk_score,
            category_breakdown=category_breakdown,
            severity_breakdown=severity_breakdown,
            exposure_breakdown=assessment.exposures,
            summary=(
                f"Overall risk score {assessment.overall_risk_score} ({assessment.overall_severity.value}); "
                f"{elevated} of {len(assessment.risk_metrics)} risk metric(s) at HIGH or CRITICAL severity."
            ),
        )

    def attribute_performance(
        self,
        recommendation_result: RecommendationResult,
        strategy_evaluation_result: StrategyEvaluationResult | None,
        risk_assessment: RiskAssessment | None,
        backtest_run: BacktestRun,
        backtest_result: BacktestResult,
    ) -> PerformanceAttribution:
        category_scores = _average_category_scores(recommendation_result.recommendations)

        if strategy_evaluation_result is not None:
            category_scores[AttributionCategory.STRATEGY] = strategy_evaluation_result.overall_alignment
        if risk_assessment is not None:
            category_scores[AttributionCategory.RISK] = 100.0 - risk_assessment.overall_risk_score

        contribution_breakdown = list(self._build_contribution_breakdown(_PORTFOLIO_SOURCE, category_scores))
        if risk_assessment is not None:
            contribution_breakdown.extend(_exposure_contributions(risk_assessment, self._contribution_total))
        contribution_breakdown.sort(key=lambda entry: (-entry.contribution_percent, entry.source, entry.category.value))
        contribution_breakdown = contribution_breakdown[: self._max_categories]

        period = _describe_period(backtest_run)
        return PerformanceAttribution(
            period=period,
            portfolio_return=backtest_result.portfolio_return,
            benchmark_return=backtest_result.benchmark_return,
            excess_return=backtest_result.excess_return,
            contribution_breakdown=tuple(contribution_breakdown),
            summary=(
                f"Over {period}, portfolio return {backtest_result.portfolio_return}% vs benchmark "
                f"{backtest_result.benchmark_return}% (excess {backtest_result.excess_return}%), "
                f"attributed across {len(contribution_breakdown)} source(s)."
            ),
        )

    def _build_contribution_breakdown(
        self, source: str, category_scores: dict[AttributionCategory, float]
    ) -> tuple[ContributionBreakdown, ...]:
        if not category_scores:
            return ()
        weight_map = _weight_map(self._weighting)
        weighted = {
            category: score * weight_map.get(category, 1.0) for category, score in category_scores.items()
        }
        weighted_sum = sum(weighted.values())
        entries = [
            ContributionBreakdown(
                source=source,
                category=category,
                weight=weight_map.get(category, 1.0),
                contribution_percent=(
                    round((weighted[category] / weighted_sum) * self._contribution_total, 4) if weighted_sum else 0.0
                ),
                description=(
                    f"{category.value} scored {round(score, 2)}, weighted {weight_map.get(category, 1.0)}."
                ),
            )
            for category, score in category_scores.items()
        ]
        entries.sort(key=lambda entry: (-entry.contribution_percent, entry.category.value))
        return tuple(entries[: self._max_categories])

    # --- Orchestration -----------------------------------------------------------

    async def explain(self, request: ExplainabilityRequest) -> ExplainabilityResult:
        """Resolve every id `request` references via the injected
        services, build every applicable explanation, persist the result,
        and return it.

        Raises:
            InvalidReferenceError: a referenced id could not be resolved
                via the injected services.
        """
        try:
            recommendation_result = await self._recommendation_service.get_result(
                request.recommendation_result_id
            )
            strategy_evaluation_result = (
                await self._strategy_service.get_evaluation(request.strategy_evaluation_id)
                if request.strategy_evaluation_id is not None
                else None
            )
            risk_assessment = (
                await self._risk_service.get_assessment(request.risk_assessment_id)
                if request.risk_assessment_id is not None
                else None
            )
            backtest_run: BacktestRun | None = None
            backtest_result: BacktestResult | None = None
            if request.backtest_run_id is not None:
                backtest_run = await self._backtesting_service.get_run(request.backtest_run_id)
                backtest_result = await self._backtesting_service.get_result(request.backtest_run_id)
        except (
            RecommendationResultNotFoundError,
            StrategyEvaluationNotFoundError,
            RiskAssessmentNotFoundError,
            BacktestRunNotFoundError,
            BacktestResultNotFoundError,
        ) as exc:
            raise InvalidReferenceError(request.id, str(exc)) from exc

        recommendation_explanations = tuple(
            self.explain_recommendation(candidate) for candidate in recommendation_result.recommendations
        )
        strategy_explanations = (
            tuple(self.explain_strategy(match) for match in strategy_evaluation_result.strategy_matches)
            if strategy_evaluation_result is not None
            else ()
        )
        risk_explanation = self.explain_risk(risk_assessment) if risk_assessment is not None else None
        performance_attribution = (
            self.attribute_performance(
                recommendation_result, strategy_evaluation_result, risk_assessment, backtest_run, backtest_result
            )
            if backtest_run is not None and backtest_result is not None
            else None
        )

        result = ExplainabilityResult(
            request_id=request.id,
            generated_at=self._now_fn(),
            recommendation_explanations=recommendation_explanations,
            strategy_explanations=strategy_explanations,
            risk_explanation=risk_explanation,
            performance_attribution=performance_attribution,
            overall_summary=_build_overall_summary(
                recommendation_explanations, strategy_explanations, risk_explanation, performance_attribution
            ),
        )
        return await self._repository.store_result(result)


def _candidate_category_scores(candidate: RecommendationCandidate) -> dict[AttributionCategory, float]:
    scores: dict[AttributionCategory, float] = {}
    for category, field_name in _COMPONENT_CATEGORY_FIELDS:
        value = getattr(candidate, field_name)
        if value is not None:
            scores[category] = value
    return scores


def _average_category_scores(
    candidates: tuple[RecommendationCandidate, ...],
) -> dict[AttributionCategory, float]:
    sums: dict[AttributionCategory, float] = {}
    counts: dict[AttributionCategory, int] = {}
    for candidate in candidates:
        for category, score in _candidate_category_scores(candidate).items():
            sums[category] = sums.get(category, 0.0) + score
            counts[category] = counts.get(category, 0) + 1
    return {category: round(sums[category] / counts[category], 4) for category in sums}


def _weight_map(weighting: ExplainabilityWeighting) -> dict[AttributionCategory, float]:
    return {
        AttributionCategory.PLANNING: weighting.planning,
        AttributionCategory.SCREENING: weighting.screening,
        AttributionCategory.SIGNALS: weighting.signals,
        AttributionCategory.ALERTS: weighting.alerts,
        AttributionCategory.RESEARCH: weighting.research,
        AttributionCategory.PORTFOLIO_INTELLIGENCE: weighting.portfolio_intelligence,
        AttributionCategory.STRATEGY: weighting.strategy,
        AttributionCategory.RISK: weighting.risk,
        AttributionCategory.SECTOR: weighting.sector,
        AttributionCategory.COUNTRY: weighting.country,
        AttributionCategory.INDUSTRY: weighting.industry,
    }


def _top_factors(
    category_scores: dict[AttributionCategory, float],
    contributing: tuple[ContributionBreakdown, ...],
    *,
    positive: bool,
) -> tuple[ContributionBreakdown, ...]:
    by_category = {entry.category: entry for entry in contributing}
    ordered = sorted(
        category_scores.items(),
        key=lambda item: (-item[1] if positive else item[1], item[0].value),
    )
    return tuple(by_category[category] for category, _ in ordered[:TOP_FACTORS_COUNT] if category in by_category)


def _exposure_contributions(assessment: RiskAssessment, contribution_total: float) -> list[ContributionBreakdown]:
    entries: list[ContributionBreakdown] = []
    for exposure in assessment.exposures:
        if exposure.sector is not None:
            category, value = AttributionCategory.SECTOR, exposure.sector
        elif exposure.country is not None:
            category, value = AttributionCategory.COUNTRY, exposure.country
        elif exposure.industry is not None:
            category, value = AttributionCategory.INDUSTRY, exposure.industry
        else:
            continue
        entries.append(
            ContributionBreakdown(
                source=value,
                category=category,
                weight=exposure.weight,
                contribution_percent=round(exposure.weight * contribution_total, 4),
                description=f"{value}: {exposure.holding_count} holding(s), {round(exposure.weight * 100, 2)}% of portfolio.",
            )
        )
    return entries


def _describe_period(run: BacktestRun) -> str:
    if not run.results:
        return "No periods processed."
    first, last = run.results[0], run.results[-1]
    return f"{first.timestamp.date().isoformat()} to {last.timestamp.date().isoformat()} ({len(run.results)} period(s))"


def _build_overall_summary(
    recommendation_explanations: tuple[RecommendationExplanation, ...],
    strategy_explanations: tuple[StrategyExplanation, ...],
    risk_explanation: RiskExplanation | None,
    performance_attribution: PerformanceAttribution | None,
) -> str:
    parts = [f"Explained {len(recommendation_explanations)} recommendation(s)"]
    if strategy_explanations:
        parts.append(f"{len(strategy_explanations)} strategy alignment(s)")
    if risk_explanation is not None:
        parts.append(f"risk score {risk_explanation.overall_risk_score}")
    if performance_attribution is not None:
        parts.append(f"performance attribution over {performance_attribution.period}")
    return "; ".join(parts) + "."
