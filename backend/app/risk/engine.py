"""RiskAnalyticsService: the Risk Analytics Engine's Application layer.

Evaluates already-generated `app.recommendations.models.RecommendationResult`
(and, optionally, `app.strategy.models.StrategyEvaluationResult`) output for
portfolio risk characteristics — never optimizes an allocation, never
rebalances, never executes a trade, never connects to a broker, never
fetches market data, and never runs a Monte Carlo simulation. Combines
request management (delegated to an injected `BaseRiskAnalyticsRepository`)
with risk calculation (pure, deterministic — no I/O, no market data, no
AI). No globals, no singleton: every dependency is injected at
construction time.

Every risk metric this service computes is built *only* from
`RecommendationCandidate`'s own already-normalized fields (`sector`,
`country`, `industry`, `overall_score`, `confidence`, `supporting_signals`)
— nothing here is a real statistical measurement of price volatility,
trading liquidity, or market capitalization, because none of that data
reaches this engine (see `app.risk.models`'s own module docstring). Each
formula below is documented as exactly what it is: a deterministic,
transparent proxy built from available evidence, never a fabricated
number standing in for data that was never supplied.

Scoring convention: every `RiskMetric.score` and `RiskAssessment
.overall_risk_score` use one consistent polarity — 0 is no risk, 100 is
maximum risk. `RiskThresholds.classify()` (ascending cut-points) applies
uniformly to every metric and to the overall blended score.
"""

from __future__ import annotations

import statistics
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

from app.recommendations.models import RecommendationCandidate, RecommendationResult
from app.risk.exceptions import (
    DuplicateRiskRequestNameError,
    RiskAssessmentNotFoundError,
    RiskAssessmentRequestNotFoundError,
)
from app.risk.models import (
    MarketDataCoverage,
    MarketDataCoverageStatus,
    PortfolioExposure,
    RiskAssessment,
    RiskAssessmentRequest,
    RiskCategory,
    RiskMetric,
    RiskSeverity,
    RiskThresholds,
    RiskWeighting,
)
from app.services.market_snapshot.models import MarketSnapshotStatus
from app.signals.models import SignalCategory
from app.strategy.models import StrategyEvaluationResult

if TYPE_CHECKING:
    from app.repositories.risk.repository import BaseRiskAnalyticsRepository

__all__ = ["RiskAnalyticsService"]

DEFAULT_MAX_EXPOSURES = 20

_MARKET_CAP_INSUFFICIENT_DATA_DESCRIPTION = (
    "No market-cap data is available: RecommendationCandidate carries no market "
    "capitalization field, and this engine does not fetch market data directly."
)


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


class RiskAnalyticsService:
    def __init__(
        self,
        repository: BaseRiskAnalyticsRepository,
        *,
        weighting: RiskWeighting = RiskWeighting(),
        thresholds: RiskThresholds = RiskThresholds(),
        max_exposures: int = DEFAULT_MAX_EXPOSURES,
        enforce_unique_names: bool = True,
        now_fn: Callable[[], datetime] = _default_now,
    ) -> None:
        self._repository = repository
        self._weighting = weighting
        self._thresholds = thresholds
        self._max_exposures = max_exposures
        self._enforce_unique_names = enforce_unique_names
        self._now_fn = now_fn

    # --- Request management -----------------------------------------------------------

    async def create_request(
        self,
        request_name: str,
        portfolio_id: str,
        recommendation_result_id: str,
        *,
        strategy_evaluation_id: str | None = None,
    ) -> RiskAssessmentRequest:
        """Create a new risk assessment request.

        Raises:
            DuplicateRiskRequestNameError: `request_name` is already in
                use (only when `enforce_unique_names=True`, the default).
        """
        await self._check_unique_name(request_name)
        request = RiskAssessmentRequest(
            id=str(uuid.uuid4()),
            request_name=request_name,
            portfolio_id=portfolio_id,
            strategy_evaluation_id=strategy_evaluation_id,
            recommendation_result_id=recommendation_result_id,
            created_at=self._now_fn(),
        )
        return await self._repository.create_request(request)

    async def get_request(self, request_id: str) -> RiskAssessmentRequest:
        """Raises `RiskAssessmentRequestNotFoundError` if no request exists for `request_id`."""
        request = await self._repository.get_request(request_id)
        if request is None:
            raise RiskAssessmentRequestNotFoundError(request_id)
        return request

    async def list_requests(self) -> list[RiskAssessmentRequest]:
        return await self._repository.list_requests()

    async def get_assessment(self, request_id: str) -> RiskAssessment:
        """Raises `RiskAssessmentNotFoundError` if no assessment exists for `request_id`."""
        assessment = await self._repository.get_assessment(request_id)
        if assessment is None:
            raise RiskAssessmentNotFoundError(request_id)
        return assessment

    async def list_assessments(self) -> list[RiskAssessment]:
        return await self._repository.list_assessments()

    async def _check_unique_name(self, name: str) -> None:
        if not self._enforce_unique_names:
            return
        for existing in await self._repository.list_requests():
            if existing.request_name == name:
                raise DuplicateRiskRequestNameError(name)

    # --- Exposure aggregation -----------------------------------------------------------

    def calculate_exposures(
        self, candidates: tuple[RecommendationCandidate, ...]
    ) -> tuple[PortfolioExposure, ...]:
        """Aggregate `candidates` into sector/country/industry exposure
        buckets. Every candidate is treated as equally weighted — no real
        position-sizing (dollar amount, share count) data exists anywhere
        in this codebase, so `weight = holding_count / total_candidates`
        is the only defensible, documented default. Truncated to the
        configured `max_exposures` per dimension, sorted deterministically
        by weight descending, then dimension value ascending.
        """
        total = len(candidates)
        exposures: list[PortfolioExposure] = []
        for dimension, key_fn in (
            ("sector", lambda c: c.sector),
            ("country", lambda c: c.country),
            ("industry", lambda c: c.industry),
        ):
            exposures.extend(_aggregate_dimension(candidates, dimension, key_fn, total, self._max_exposures))
        return tuple(exposures)

    # --- Risk metric calculations -----------------------------------------------------------

    def calculate_diversification(self, candidates: tuple[RecommendationCandidate, ...]) -> RiskMetric:
        """Diversification *risk*: the Herfindahl-Hirschman Index (HHI)
        over aggregate sector weights — the standard concentration measure
        in finance/economics, applied here across sectors rather than
        holdings (see `calculate_concentration` for the holding-level
        version). HHI ranges from `1/N` (N sectors, evenly spread) to `1.0`
        (a single sector). Score = `HHI * 100`: higher means the portfolio
        leans on fewer sectors, i.e. worse (riskier) diversification.
        """
        sector_weights = _dimension_weights(candidates, lambda c: c.sector)
        hhi = _herfindahl_hirschman_index(sector_weights)
        score = round(hhi * 100, 2)
        return RiskMetric(
            metric_name="Sector Diversification",
            category=RiskCategory.DIVERSIFICATION,
            value=round(hhi, 4),
            score=score,
            severity=self._thresholds.classify(score),
            description=(
                f"Herfindahl-Hirschman Index across {len(sector_weights)} distinct sector(s): {round(hhi, 4)}. "
                "Higher values indicate the portfolio relies on fewer sectors."
            ),
        )

    def calculate_concentration(self, candidates: tuple[RecommendationCandidate, ...]) -> RiskMetric:
        """Concentration risk: the Herfindahl-Hirschman Index over
        per-holding weights (equal-weighted — see `calculate_exposures`).
        For N equally-weighted holdings, HHI = `1/N`; score = `HHI * 100`,
        so a 1-holding portfolio scores 100 (maximum concentration risk)
        and a 100-holding portfolio scores 1 (minimal).
        """
        total = len(candidates)
        hhi = (1 / total) if total else 1.0
        score = round(hhi * 100, 2)
        return RiskMetric(
            metric_name="Holding Concentration",
            category=RiskCategory.CONCENTRATION,
            value=round(hhi, 4),
            score=score,
            severity=self._thresholds.classify(score),
            description=(
                f"{total} holding(s), equally weighted. Herfindahl-Hirschman Index: {round(hhi, 4)}. "
                "Higher values indicate risk concentrated in fewer holdings."
            ),
        )

    def calculate_sector_exposure(self, candidates: tuple[RecommendationCandidate, ...]) -> RiskMetric:
        """Sector risk: the single largest sector's aggregate weight —
        distinct from `calculate_diversification`'s whole-distribution
        HHI, this looks only at the biggest bucket."""
        sector_weights = _dimension_weights(candidates, lambda c: c.sector)
        top_sector, top_weight = _largest_bucket(sector_weights)
        score = round(top_weight * 100, 2)
        description = (
            f"Largest single sector ({top_sector}) accounts for {score}% of holdings."
            if top_sector is not None
            else "No sector data available on any candidate."
        )
        return RiskMetric(
            metric_name="Sector Concentration",
            category=RiskCategory.SECTOR,
            value=round(top_weight, 4),
            score=score,
            severity=self._thresholds.classify(score),
            description=description,
        )

    def calculate_geographic_exposure(self, candidates: tuple[RecommendationCandidate, ...]) -> RiskMetric:
        """Geographic risk: the single largest country's aggregate weight
        — mirrors `calculate_sector_exposure`, over `country` instead."""
        country_weights = _dimension_weights(candidates, lambda c: c.country)
        top_country, top_weight = _largest_bucket(country_weights)
        score = round(top_weight * 100, 2)
        description = (
            f"Largest single country ({top_country}) accounts for {score}% of holdings."
            if top_country is not None
            else "No country data available on any candidate."
        )
        return RiskMetric(
            metric_name="Geographic Concentration",
            category=RiskCategory.GEOGRAPHIC,
            value=round(top_weight, 4),
            score=score,
            severity=self._thresholds.classify(score),
            description=description,
        )

    def calculate_market_cap_distribution(self, candidates: tuple[RecommendationCandidate, ...]) -> RiskMetric:
        """Market-cap risk: always reported as insufficient data (score 0,
        `LOW` severity) — see this module's own docstring and
        `app.risk.models`'s module docstring for why. Never fabricated."""
        return RiskMetric(
            metric_name="Market Capitalization Distribution",
            category=RiskCategory.MARKET_CAP,
            value=0.0,
            score=0.0,
            severity=RiskSeverity.LOW,
            description=_MARKET_CAP_INSUFFICIENT_DATA_DESCRIPTION,
        )

    def estimate_volatility(self, candidates: tuple[RecommendationCandidate, ...]) -> RiskMetric:
        """Volatility risk *proxy* — this engine has no access to price
        history, returns, or beta (never fetched; forbidden by this
        sprint). Built entirely from `RecommendationCandidate`'s own
        already-normalized inputs: (1) the population standard deviation
        of `overall_score` across the portfolio (wide score dispersion is
        a weak signal of heterogeneous/uncertain quality), scaled by 2 and
        capped at 100 since a 0-100-bounded value's stdev rarely exceeds
        ~50; and (2) the fraction of candidates carrying at least one
        triggered `SignalCategory.VOLATILITY` supporting signal. Blended
        with a plain, documented 50/50 average — this is NOT a Monte Carlo
        simulation and NOT a statistical estimate of return volatility.
        """
        total = len(candidates)
        if total == 0:
            return RiskMetric(
                metric_name="Volatility Proxy",
                category=RiskCategory.VOLATILITY,
                value=0.0,
                score=0.0,
                severity=self._thresholds.classify(0.0),
                description="No candidates to evaluate.",
            )

        scores = [c.overall_score for c in candidates]
        dispersion = statistics.pstdev(scores) if total > 1 else 0.0
        normalized_dispersion = min(100.0, dispersion * 2)

        volatility_flagged = sum(
            1
            for c in candidates
            if any(s.triggered and s.category == SignalCategory.VOLATILITY for s in c.supporting_signals)
        )
        volatility_fraction = volatility_flagged / total

        score = round(0.5 * normalized_dispersion + 0.5 * (volatility_fraction * 100), 2)
        return RiskMetric(
            metric_name="Volatility Proxy",
            category=RiskCategory.VOLATILITY,
            value=round(dispersion, 2),
            score=score,
            severity=self._thresholds.classify(score),
            description=(
                f"Score dispersion (population stdev of overall_score): {round(dispersion, 2)}. "
                f"{volatility_flagged}/{total} candidate(s) carry a triggered VOLATILITY signal. "
                "Proxy only — no price/return data was available."
            ),
        )

    def calculate_liquidity(self, candidates: tuple[RecommendationCandidate, ...]) -> RiskMetric:
        """Liquidity risk *proxy* — this engine has no access to trading
        volume (never fetched; forbidden by this sprint). Built from the
        portfolio's average `confidence` (Sprint 49's own coverage-based
        confidence — how much supporting evidence existed per candidate),
        inverted: `score = 100 - average_confidence`. Sparse evidence
        coverage is used as a weak proxy for thin market coverage — this
        is NOT a real liquidity/trading-volume measurement.
        """
        if not candidates:
            return RiskMetric(
                metric_name="Liquidity Proxy",
                category=RiskCategory.LIQUIDITY,
                value=0.0,
                score=0.0,
                severity=self._thresholds.classify(0.0),
                description="No candidates to evaluate.",
            )

        average_confidence = round(sum(c.confidence for c in candidates) / len(candidates), 2)
        score = round(max(0.0, 100.0 - average_confidence), 2)
        return RiskMetric(
            metric_name="Liquidity Proxy",
            category=RiskCategory.LIQUIDITY,
            value=average_confidence,
            score=score,
            severity=self._thresholds.classify(score),
            description=(
                f"Average recommendation confidence (evidence coverage): {average_confidence}%. "
                "Proxy only — no trading-volume data was available."
            ),
        )

    # --- Assessment -----------------------------------------------------------

    async def assess_portfolio(
        self,
        request: RiskAssessmentRequest,
        recommendation_result: RecommendationResult,
        strategy_evaluation_result: StrategyEvaluationResult | None = None,
    ) -> RiskAssessment:
        """Compute every built-in risk metric against `recommendation_result`,
        blend them into `overall_risk_score` using the configured
        `RiskWeighting`, and persist the result. `strategy_evaluation_result`
        is accepted (reused per this sprint's own requirement) but this
        built-in pipeline does not currently derive any metric from it —
        it is available for a future extension without a signature change.
        """
        candidates = recommendation_result.recommendations

        metrics = (
            self.calculate_diversification(candidates),
            self.calculate_concentration(candidates),
            self.calculate_sector_exposure(candidates),
            self.calculate_geographic_exposure(candidates),
            self.calculate_market_cap_distribution(candidates),
            self.estimate_volatility(candidates),
            self.calculate_liquidity(candidates),
        )
        exposures = self.calculate_exposures(candidates)

        overall_score = _weighted_overall_score(metrics, self._weighting)
        overall_severity = self._thresholds.classify(overall_score)
        recommendations = _build_recommendations(metrics)

        assessment = RiskAssessment(
            request_id=request.id,
            overall_risk_score=overall_score,
            overall_severity=overall_severity,
            risk_metrics=metrics,
            exposures=exposures,
            recommendations=recommendations,
            summary=_build_summary(overall_score, overall_severity, metrics, len(candidates)),
            market_data_coverage=_compute_market_data_coverage(candidates),
            generated_at=self._now_fn(),
        )
        return await self._repository.store_assessment(assessment)


_MARKET_DATA_PRESENT_STATUSES = (MarketSnapshotStatus.FRESH, MarketSnapshotStatus.STALE)


def _compute_market_data_coverage(candidates: tuple[RecommendationCandidate, ...]) -> MarketDataCoverage:
    """Purely informational (§5): summarizes how many of `candidates` carry
    live market data, without feeding into `overall_risk_score` or any
    `RiskMetric` above. `market_freshness` is `None` for candidates
    generated before Milestone 14 wired market data into Recommendations
    (or when this recommendation run had none supplied) — those count as
    `not_evaluated`, distinct from a candidate that was evaluated and
    genuinely came back unmapped/unavailable."""
    total = len(candidates)
    fresh = stale = unavailable = not_evaluated = 0
    for candidate in candidates:
        freshness = candidate.market_freshness
        if freshness is None:
            not_evaluated += 1
        elif freshness == MarketSnapshotStatus.FRESH:
            fresh += 1
        elif freshness == MarketSnapshotStatus.STALE:
            stale += 1
        else:
            unavailable += 1

    present = fresh + stale
    if total == 0 or present + unavailable == 0:
        status = MarketDataCoverageStatus.NOT_EVALUATED
    elif present == 0:
        status = MarketDataCoverageStatus.NONE
    elif present == total:
        status = MarketDataCoverageStatus.FULL
    else:
        status = MarketDataCoverageStatus.PARTIAL

    return MarketDataCoverage(
        status=status,
        fresh_count=fresh,
        stale_count=stale,
        unavailable_count=unavailable,
        not_evaluated_count=not_evaluated,
        total_candidates=total,
    )


def _dimension_weights(
    candidates: tuple[RecommendationCandidate, ...], key_fn: Callable[[RecommendationCandidate], str | None]
) -> dict[str, float]:
    total = len(candidates)
    if total == 0:
        return {}
    counts = Counter(value for c in candidates if (value := key_fn(c)) is not None)
    return {value: count / total for value, count in counts.items()}


def _largest_bucket(weights: dict[str, float]) -> tuple[str | None, float]:
    if not weights:
        return None, 0.0
    name = max(weights, key=lambda key: (weights[key], key))
    return name, weights[name]


def _herfindahl_hirschman_index(weights: dict[str, float]) -> float:
    if not weights:
        return 1.0  # no data at all is treated as maximally concentrated/undiversified
    return sum(weight**2 for weight in weights.values())


def _aggregate_dimension(
    candidates: tuple[RecommendationCandidate, ...],
    dimension: str,
    key_fn: Callable[[RecommendationCandidate], str | None],
    total: int,
    max_exposures: int,
) -> list[PortfolioExposure]:
    counts: Counter[str] = Counter(value for c in candidates if (value := key_fn(c)) is not None)
    entries = [
        PortfolioExposure(
            **{dimension: value},
            weight=round(count / total, 4) if total else 0.0,
            holding_count=count,
        )
        for value, count in counts.items()
    ]
    entries.sort(key=lambda entry: (-entry.weight, getattr(entry, dimension)))
    return entries[:max_exposures]


def _weighted_overall_score(metrics: tuple[RiskMetric, ...], weighting: RiskWeighting) -> float:
    weight_map = {
        RiskCategory.DIVERSIFICATION: weighting.diversification,
        RiskCategory.CONCENTRATION: weighting.concentration,
        RiskCategory.SECTOR: weighting.sector,
        RiskCategory.GEOGRAPHIC: weighting.geographic,
        RiskCategory.MARKET_CAP: weighting.market_cap,
        RiskCategory.VOLATILITY: weighting.volatility,
        RiskCategory.LIQUIDITY: weighting.liquidity,
    }
    total_weight = sum(weight_map[metric.category] for metric in metrics)
    weighted_sum = sum(weight_map[metric.category] * metric.score for metric in metrics)
    return round(weighted_sum / total_weight, 2) if total_weight else 0.0


def _build_recommendations(metrics: tuple[RiskMetric, ...]) -> tuple[str, ...]:
    return tuple(
        f"{metric.metric_name} is {metric.severity.value}: {metric.description}"
        for metric in metrics
        if metric.severity in (RiskSeverity.HIGH, RiskSeverity.CRITICAL)
    )


def _build_summary(
    overall_score: float, overall_severity: RiskSeverity, metrics: tuple[RiskMetric, ...], candidate_count: int
) -> str:
    elevated = sum(1 for m in metrics if m.severity in (RiskSeverity.HIGH, RiskSeverity.CRITICAL))
    return (
        f"Overall risk score {overall_score} ({overall_severity.value}) across {candidate_count} "
        f"holding(s); {elevated} of {len(metrics)} risk metric(s) at HIGH or CRITICAL severity."
    )
