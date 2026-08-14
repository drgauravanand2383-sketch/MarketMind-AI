"""PortfolioRecommendationService: the Portfolio Recommendation Engine's
Application layer.

Merges already-computed outputs from other subsystems into scored, ranked,
explainable `RecommendationCandidate`s — never executes a trade, never
rebalances a portfolio, never performs portfolio optimization or advanced
risk calculation, never connects to a broker, and never fetches live
market data. Every `app.recommendations.models.CandidateEvidence` is
supplied by the caller, already computed elsewhere — this service never
calls into Screening, Signal Detection, Alerts, Company Research, or
Portfolio Intelligence itself, exactly mirroring how
`app.alerts.engine.AlertService` (Sprint 48) consumes an already-computed
`SignalResult` rather than running Signal Detection itself. No globals, no
singleton: every dependency is injected at construction time.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

from app.alerts.models import Alert, AlertStatus
from app.recommendations.exceptions import (
    DuplicateRequestNameError,
    RecommendationRequestNotFoundError,
    RecommendationResultNotFoundError,
)
from app.recommendations.models import (
    CandidateEvidence,
    MarketContribution,
    RecommendationCandidate,
    RecommendationRequest,
    RecommendationResult,
    RecommendationSummary,
    RecommendationThresholds,
    RecommendationType,
    ScoringWeights,
)
from app.services.market_snapshot.models import MarketSnapshotResult, MarketSnapshotStatus
from app.signals.models import SignalResult

if TYPE_CHECKING:
    from app.repositories.recommendations.repository import BaseRecommendationRepository

__all__ = ["PortfolioRecommendationService"]

_COMPONENT_NAMES = ("planning", "screening", "signals", "research", "portfolio", "alerts")


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


class PortfolioRecommendationService:
    def __init__(
        self,
        repository: BaseRecommendationRepository,
        *,
        weights: ScoringWeights = ScoringWeights(),
        thresholds: RecommendationThresholds = RecommendationThresholds(),
        enforce_unique_names: bool = True,
        now_fn: Callable[[], datetime] = _default_now,
    ) -> None:
        """Initialize the service.

        Args:
            repository: Persists `RecommendationRequest`s and `RecommendationResult`s.
            weights: Configurable per-component weights (see `ScoringWeights`).
            thresholds: Configurable score cut-points (see `RecommendationThresholds`).
            enforce_unique_names: Whether request names must be unique.
            now_fn: Returns the current time. Injected (never `datetime.now()`
                called directly elsewhere in this class) so tests can supply
                a fixed clock — mirrors `AlertService`'s injectable `now_fn`
                (Sprint 48).
        """
        self._repository = repository
        self._weights = weights
        self._thresholds = thresholds
        self._enforce_unique_names = enforce_unique_names
        self._now_fn = now_fn

    # --- Request management -----------------------------------------------------------

    async def create_request(
        self,
        request_name: str,
        *,
        watchlist_ids: tuple[str, ...] = (),
        screening_profile_ids: tuple[str, ...] = (),
        signal_definition_ids: tuple[str, ...] = (),
        alert_rule_ids: tuple[str, ...] = (),
        planning_context: dict | None = None,
        max_recommendations: int = 10,
        minimum_score: float = 0.0,
    ) -> RecommendationRequest:
        """Create a new recommendation request.

        Raises:
            DuplicateRequestNameError: `request_name` is already in use
                (only when `enforce_unique_names=True`, the default).
        """
        await self._check_unique_name(request_name)
        request = RecommendationRequest(
            id=str(uuid.uuid4()),
            request_name=request_name,
            watchlist_ids=watchlist_ids,
            screening_profile_ids=screening_profile_ids,
            signal_definition_ids=signal_definition_ids,
            alert_rule_ids=alert_rule_ids,
            planning_context=planning_context or {},
            max_recommendations=max_recommendations,
            minimum_score=minimum_score,
            created_at=self._now_fn(),
        )
        return await self._repository.create_request(request)

    async def get_request(self, request_id: str) -> RecommendationRequest:
        """Raises `RecommendationRequestNotFoundError` if no request exists for `request_id`."""
        request = await self._repository.get_request(request_id)
        if request is None:
            raise RecommendationRequestNotFoundError(request_id)
        return request

    async def list_requests(self) -> list[RecommendationRequest]:
        return await self._repository.list_requests()

    async def get_result(self, request_id: str) -> RecommendationResult:
        """Raises `RecommendationResultNotFoundError` if no result exists for `request_id`."""
        result = await self._repository.get_result(request_id)
        if result is None:
            raise RecommendationResultNotFoundError(request_id)
        return result

    async def list_results(self) -> list[RecommendationResult]:
        return await self._repository.list_results()

    async def _check_unique_name(self, name: str) -> None:
        if not self._enforce_unique_names:
            return
        for existing in await self._repository.list_requests():
            if existing.request_name == name:
                raise DuplicateRequestNameError(name)

    # --- Scoring -----------------------------------------------------------

    def score_candidate(self, evidence: CandidateEvidence) -> RecommendationCandidate:
        """Score, classify, and explain one candidate. Pure and
        synchronous — no I/O, no market data fetch, no AI reasoning.
        Merges every one of the candidate's six possible evidence sources
        (see `app.recommendations.models` module docstring for how each
        component score is derived and scaled).

        Milestone 14: `evidence.market_snapshot`, if the caller supplied
        one, is relayed onto the candidate's own `market_price`/
        `market_change_percent`/`market_freshness`/`market_snapshot`
        fields — exactly like every other evidence field, this method
        never fetches it. `_derive_components`/`_weighted_score` (the
        actual scoring formula) are completely untouched by this —
        market data never becomes a seventh weighted score component,
        only a transparently-labeled `market_contribution` (see
        `app.recommendations.models.MarketContribution`'s own docstring).
        """
        components = _derive_components(evidence)
        overall_score = _weighted_score(components, self._weights)
        confidence = _confidence(components)
        recommendation = self._thresholds.classify(overall_score)
        supporting_signals = _triggered_signals(evidence)
        supporting_alerts = _generated_alerts(evidence)
        market_price, market_change_percent, market_freshness = _market_fields(evidence.market_snapshot)
        market_contribution = _market_contribution(evidence.market_snapshot, supporting_signals)

        return RecommendationCandidate(
            ticker=evidence.ticker,
            company_name=evidence.company_name,
            country=evidence.country,
            sector=evidence.sector,
            industry=evidence.industry,
            overall_score=overall_score,
            confidence=confidence,
            recommendation=recommendation,
            reasoning=_build_reasoning(
                recommendation, overall_score, confidence, components, supporting_signals, supporting_alerts
            ),
            supporting_signals=supporting_signals,
            supporting_alerts=supporting_alerts,
            screening_score=components["screening"],
            planning_score=components["planning"],
            research_score=components["research"],
            portfolio_score=components["portfolio"],
            signal_score=components["signals"],
            alert_score=components["alerts"],
            market_price=market_price,
            market_change_percent=market_change_percent,
            market_freshness=market_freshness,
            market_snapshot=evidence.market_snapshot,
            market_contribution=market_contribution,
            created_at=self._now_fn(),
        )

    # --- Generation -----------------------------------------------------------

    async def generate_recommendations(
        self, request: RecommendationRequest, evidence: list[CandidateEvidence]
    ) -> RecommendationResult:
        """Score every candidate, filter by `request.minimum_score`, rank
        by score descending (ties broken by ticker, ascending — fully
        deterministic regardless of `evidence`'s input order), and keep
        the top `request.max_recommendations`. The generated result is
        persisted before being returned.
        """
        candidates = [self.score_candidate(item) for item in evidence]
        total_candidates = len(candidates)

        eligible = [c for c in candidates if c.overall_score >= request.minimum_score]
        ranked = sorted(eligible, key=lambda c: (-c.overall_score, c.ticker))
        top = ranked[: request.max_recommendations]

        result = RecommendationResult(
            request_id=request.id,
            generated_at=self._now_fn(),
            total_candidates=total_candidates,
            recommendations=tuple(top),
            summary=_build_summary(top),
        )
        return await self._repository.store_result(result)


def _derive_components(evidence: CandidateEvidence) -> dict[str, float | None]:
    """Extract each of the six score components from `evidence`, scaled to
    0–100 (see the module docstring on `app.recommendations.models` for
    why research/portfolio confidence — natively 0.0–1.0 — is multiplied
    by 100, and why `planning_score` is a directly-supplied value)."""
    return {
        "planning": evidence.planning_score,
        "screening": evidence.screening_result.score if evidence.screening_result is not None else None,
        "signals": _average_score(_triggered_signals(evidence)),
        "research": (
            round(evidence.research_report.confidence_summary.overall_confidence * 100, 2)
            if evidence.research_report is not None
            else None
        ),
        "portfolio": (
            round(evidence.portfolio_summary.overall_confidence * 100, 2)
            if evidence.portfolio_summary is not None
            else None
        ),
        "alerts": _average_score(_generated_alerts(evidence)),
    }


def _triggered_signals(evidence: CandidateEvidence) -> tuple[SignalResult, ...]:
    """Only triggered signals count as supporting evidence — an untriggered
    evaluation supports nothing."""
    return tuple(signal for signal in evidence.signals if signal.triggered)


def _generated_alerts(evidence: CandidateEvidence) -> tuple[Alert, ...]:
    """Only `GENERATED` alerts count as supporting evidence — a `SUPPRESSED`
    alert is noise the Alert Engine already decided not to act on."""
    return tuple(alert for alert in evidence.alerts if alert.status == AlertStatus.GENERATED)


_MARKET_DATA_PRESENT_STATUSES = (MarketSnapshotStatus.FRESH, MarketSnapshotStatus.STALE)


def _market_fields(
    market_snapshot: MarketSnapshotResult | None,
) -> tuple[float | None, float | None, MarketSnapshotStatus | None]:
    """Extract the flat scalar market fields from a caller-supplied
    `MarketSnapshotResult`, if any. Only unpacks price/change_percent
    when a real snapshot exists (`status` FRESH/STALE) — an
    `ENTITY_NOT_MAPPED`/provider-failure result carries no `.snapshot` to
    unpack, and `market_freshness` alone already records that outcome
    honestly (never a fabricated 0.0)."""
    if market_snapshot is None:
        return None, None, None
    freshness = market_snapshot.status
    if market_snapshot.snapshot is None:
        return None, None, freshness
    return market_snapshot.snapshot.price, market_snapshot.snapshot.change_percent, freshness


def _market_contribution(
    market_snapshot: MarketSnapshotResult | None, supporting_signals: tuple[SignalResult, ...]
) -> MarketContribution:
    """See `app.recommendations.models.MarketContribution`'s own
    docstring for the full definition of "direct"/"indirect"/"none"."""
    if market_snapshot is not None and market_snapshot.status in _MARKET_DATA_PRESENT_STATUSES:
        return "direct"
    if any(_references_market_quote(signal) for signal in supporting_signals):
        return "indirect"
    return "none"


def _references_market_quote(signal: SignalResult) -> bool:
    return any(
        condition.field.startswith("quote.")
        for condition in (*signal.matched_conditions, *signal.failed_conditions)
    )


def _average_score(items: tuple) -> float | None:  # noqa: ANN401 - SignalResult or Alert, both have `.score`
    if not items:
        return None
    return round(sum(item.score for item in items) / len(items), 2)


def _weighted_score(components: dict[str, float | None], weights: ScoringWeights) -> float:
    """The weighted average of whichever components are available (not
    `None`), renormalized by the sum of *only those* components' weights —
    see `ScoringWeights`'s own docstring on why the raw weight total need
    not equal any fixed constant. A candidate with zero available evidence
    scores 0 (there is nothing to credit it for)."""
    weight_map = {name: getattr(weights, name) for name in _COMPONENT_NAMES}
    available = [(name, value) for name, value in components.items() if value is not None]
    if not available:
        return 0.0
    total_weight = sum(weight_map[name] for name, _ in available)
    weighted_sum = sum(weight_map[name] * value for name, value in available)
    return round(weighted_sum / total_weight, 2)


def _confidence(components: dict[str, float | None]) -> float:
    """Confidence reflects evidence *coverage*, not opportunity quality:
    the percentage of the six possible components that were actually
    available for this candidate. A candidate built from all six sources
    is reported with higher confidence than one built from a single
    source, even at an identical `overall_score` — no exact formula is
    given by the sprint spec; this is a documented, flagged judgment call
    (mirrors `app.signals.engine._confidence`'s own similarly-flagged
    formula from Sprint 47)."""
    available_count = sum(1 for value in components.values() if value is not None)
    return round(available_count / len(components) * 100, 2)


def _build_reasoning(
    recommendation: RecommendationType,
    overall_score: float,
    confidence: float,
    components: dict[str, float | None],
    supporting_signals: tuple[SignalResult, ...],
    supporting_alerts: tuple[Alert, ...],
) -> str:
    contributing = ", ".join(
        f"{name}={value}" for name, value in components.items() if value is not None
    )
    sources = contributing if contributing else "no available data sources"
    return (
        f"{recommendation.value}: overall score {overall_score} (confidence {confidence}%) "
        f"from {sources}; {len(supporting_signals)} supporting signal(s), "
        f"{len(supporting_alerts)} supporting alert(s)."
    )


def _build_summary(candidates: list[RecommendationCandidate]) -> RecommendationSummary:
    if not candidates:
        return RecommendationSummary()
    counts = Counter(candidate.recommendation for candidate in candidates)
    return RecommendationSummary(
        strong_buy=counts[RecommendationType.STRONG_BUY],
        buy=counts[RecommendationType.BUY],
        watch=counts[RecommendationType.WATCH],
        hold=counts[RecommendationType.HOLD],
        avoid=counts[RecommendationType.AVOID],
        average_score=round(sum(c.overall_score for c in candidates) / len(candidates), 2),
        average_confidence=round(sum(c.confidence for c in candidates) / len(candidates), 2),
    )
