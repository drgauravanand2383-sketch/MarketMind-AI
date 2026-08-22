"""ChangeDetectionService (§2/§3) — deterministic comparisons of current vs
previous state, using a `ContinuousIntelligenceStateStore` (in-memory or
Postgres-backed, Milestone 16 §2) for the "previous" side. Every method
takes an already-fetched domain object (a `MarketSnapshotResult`, a
`RiskAssessment`, ...) — never fetches anything itself, mirroring every
evaluation engine in this codebase since Sprint 47
(`SignalDetectionService.evaluate_company`, `AlertService.evaluate_signal`,
...). Methods are `async` solely because the injected state store's own
`observe_*` calls may be (Postgres-backed) I/O — the comparison/scoring
logic itself remains pure and synchronous internally.

Each `detect_*` method returns `DetectedChange | None` (never raises) —
`None` covers both "nothing to compare against yet" (first observation)
and "compared, but not significant enough" (§3's threshold gate). A
scheduler run producing zero `DetectedChange`s is the *expected*, correct
outcome most cycles — see this milestone's own §2 instruction: "Do NOT
emit an event simply because a scheduler ran."
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.recommendations.models import RecommendationCandidate, RecommendationType
from app.risk.models import RiskAssessment
from app.services.continuous_intelligence.config import ContinuousIntelligenceThresholds
from app.services.continuous_intelligence.models import (
    ChangeDomain,
    ChangePriority,
    DetectedChange,
    priority_from_magnitude,
    priority_from_risk_severity,
    priority_from_signal_priority,
)
from app.services.continuous_intelligence.state import ContinuousIntelligenceStateStore
from app.services.market_snapshot.models import MarketSnapshotResult, MarketSnapshotStatus
from app.signals.models import SignalResult
from app.strategy.models import StrategyEvaluationResult

__all__ = ["ChangeDetectionService"]

_MARKET_DATA_PRESENT = (MarketSnapshotStatus.FRESH, MarketSnapshotStatus.STALE)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ChangeDetectionService:
    def __init__(
        self, state: ContinuousIntelligenceStateStore, thresholds: ContinuousIntelligenceThresholds
    ) -> None:
        self._state = state
        self._thresholds = thresholds

    # --- Market (§2A) -----------------------------------------------------------

    async def detect_market_change(
        self, entity_id: str, label: str, result: MarketSnapshotResult
    ) -> DetectedChange | None:
        """Compares `result.status`/`.snapshot.price` against the
        previously-observed status/snapshot for `entity_id`. Never treats
        a STALE-valued snapshot's `.snapshot.price` as evidence of a real
        move relative to a FRESH previous price without saying so — the
        summary always states both statuses so a STALE-vs-STALE
        unchanged price is never confused with a genuine FRESH move."""
        previous_status = await self._state.observe_market_status(entity_id, result.status.value)
        previous_snapshot = await self._state.observe_market(
            entity_id, result.snapshot if result.status in _MARKET_DATA_PRESENT else None
        )

        if previous_status is None:
            return None  # first observation: establishes baseline only

        # Status transition into/out of unavailable-or-stale is itself notable,
        # independent of any price comparison (§15: distinguish FRESH from STALE).
        if previous_status != result.status.value:
            if result.status in _MARKET_DATA_PRESENT and previous_status not in (
                MarketSnapshotStatus.FRESH.value,
                MarketSnapshotStatus.STALE.value,
            ):
                return None  # recovered from unavailable -> not alert-worthy on its own
            priority = ChangePriority.MEDIUM if result.status == MarketSnapshotStatus.STALE else ChangePriority.LOW
            fingerprint = f"MARKET:{entity_id}:status:{result.status.value}"
            return DetectedChange(
                fingerprint=fingerprint,
                domain=ChangeDomain.MARKET,
                entity_id=entity_id,
                label=label,
                priority=priority,
                summary=f"{label} market data transitioned from {previous_status} to {result.status.value}.",
                previous_value=previous_status,
                current_value=result.status.value,
                event_fingerprint=fingerprint,
                detected_at=_now(),
            )

        if result.status not in _MARKET_DATA_PRESENT or result.snapshot is None:
            return None
        if previous_snapshot is None or previous_snapshot.price <= 0:
            return None

        change_percent = (result.snapshot.price - previous_snapshot.price) / previous_snapshot.price * 100
        magnitude = abs(change_percent)
        threshold = self._thresholds.market_change_percent_threshold
        if magnitude < threshold:
            return None

        direction = "up" if change_percent > 0 else "down"
        fingerprint = f"MARKET:{entity_id}:price:{result.snapshot.fetched_at.isoformat()}"
        return DetectedChange(
            fingerprint=fingerprint,
            domain=ChangeDomain.MARKET,
            entity_id=entity_id,
            label=label,
            priority=priority_from_magnitude(magnitude, threshold),
            summary=(
                f"{label} moved {direction} {magnitude:.2f}% to {result.snapshot.price:.2f} "
                f"{result.snapshot.currency.value if result.snapshot.currency else ''}"
            ).strip()
            + ".",
            previous_value=f"{previous_snapshot.price:.2f}",
            current_value=f"{result.snapshot.price:.2f}",
            event_fingerprint=fingerprint,
            detected_at=_now(),
        )

    # --- News / Knowledge (§2B) -----------------------------------------------------------

    async def detect_news_change(
        self, entity_id: str, label: str, record_ids: frozenset[str]
    ) -> DetectedChange | None:
        previous_ids = await self._state.observe_news(entity_id, record_ids)
        if previous_ids is None:
            return None  # first observation: establishes baseline only

        new_ids = record_ids - previous_ids
        if len(new_ids) < self._thresholds.news_significance_threshold:
            return None

        fingerprint = f"NEWS:{entity_id}:count:{len(record_ids)}"
        return DetectedChange(
            fingerprint=fingerprint,
            domain=ChangeDomain.NEWS,
            entity_id=entity_id,
            label=label,
            priority=priority_from_magnitude(
                float(len(new_ids)), float(self._thresholds.news_significance_threshold)
            ),
            summary=f"{len(new_ids)} new knowledge record(s) ingested for {label}.",
            previous_value=str(len(previous_ids)),
            current_value=str(len(record_ids)),
            event_fingerprint=fingerprint,
            detected_at=_now(),
        )

    async def detect_news_confidence_change(
        self, entity_id: str, label: str, confidence: float
    ) -> DetectedChange | None:
        """`confidence` is the current `NewsGroup.confidence_score` (0-1)
        for this entity's evidence group, as already computed by the
        existing `MarketIntelligenceEngine.analyze()` — never recomputed
        here."""
        previous = await self._state.observe_news_confidence(entity_id, confidence)
        if previous is None:
            return None
        threshold = self._thresholds.news_high_confidence_threshold
        if not (confidence >= threshold and previous < threshold):
            return None  # only a *newly*-crossed threshold is news, not "still high"
        fingerprint = f"NEWS:{entity_id}:high_confidence"
        return DetectedChange(
            fingerprint=fingerprint,
            domain=ChangeDomain.NEWS,
            entity_id=entity_id,
            label=label,
            priority=ChangePriority.MEDIUM,
            summary=f"Evidence for {label} newly reached high confidence ({confidence:.2f}).",
            previous_value=f"{previous:.2f}",
            current_value=f"{confidence:.2f}",
            event_fingerprint=fingerprint,
            detected_at=_now(),
        )

    # --- Signal (§16) -----------------------------------------------------------

    async def detect_signal_change(
        self, entity_id: str, label: str, signal_definition_id: str, result: SignalResult
    ) -> DetectedChange | None:
        key = f"{entity_id}:{signal_definition_id}"
        previous_triggered = await self._state.observe_signal_triggered(key, result.triggered)
        if previous_triggered is None:
            return None
        if previous_triggered == result.triggered:
            return None
        fingerprint = f"SIGNAL:{key}:{result.triggered}"
        return DetectedChange(
            fingerprint=fingerprint,
            domain=ChangeDomain.SIGNAL,
            entity_id=entity_id,
            label=label,
            priority=priority_from_signal_priority(result.priority) if result.triggered else ChangePriority.INFO,
            summary=f"Signal {result.signal_name!r} for {label} {'triggered' if result.triggered else 'cleared'}.",
            previous_value=str(previous_triggered),
            current_value=str(result.triggered),
            event_fingerprint=fingerprint,
            detected_at=_now(),
        )

    # --- Risk (§16) -----------------------------------------------------------

    async def detect_risk_change(
        self, portfolio_id: str, label: str, assessment: RiskAssessment
    ) -> DetectedChange | None:
        previous_severity = await self._state.observe_risk_severity(portfolio_id, assessment.overall_severity)
        if previous_severity is None:
            return None
        if previous_severity == assessment.overall_severity:
            return None
        fingerprint = f"RISK:{portfolio_id}:{assessment.overall_severity.value}"
        return DetectedChange(
            fingerprint=fingerprint,
            domain=ChangeDomain.RISK,
            entity_id=portfolio_id,
            label=label,
            priority=priority_from_risk_severity(assessment.overall_severity),
            summary=f"Portfolio risk for {label} transitioned from {previous_severity.value} to {assessment.overall_severity.value}.",
            previous_value=previous_severity.value,
            current_value=assessment.overall_severity.value,
            portfolio_id=portfolio_id,
            event_fingerprint=fingerprint,
            detected_at=_now(),
        )

    # --- Recommendation (§16) -----------------------------------------------------------

    async def detect_recommendation_change(
        self, portfolio_id: str, candidate: RecommendationCandidate
    ) -> DetectedChange | None:
        key = f"{portfolio_id}:{candidate.ticker}"
        previous = await self._state.observe_recommendation(
            key, candidate.recommendation, candidate.overall_score
        )
        if previous is None:
            return None
        previous_type, previous_score = previous
        score_delta = abs(candidate.overall_score - previous_score)
        type_changed = previous_type != candidate.recommendation
        if not type_changed and score_delta < self._thresholds.recommendation_score_delta_threshold:
            return None

        priority = (
            _recommendation_type_priority(candidate.recommendation)
            if type_changed
            else priority_from_magnitude(score_delta, self._thresholds.recommendation_score_delta_threshold)
        )
        summary = (
            f"{candidate.ticker} recommendation changed from {previous_type.value} to {candidate.recommendation.value}."
            if type_changed
            else f"{candidate.ticker} recommendation score moved {score_delta:.1f} points to {candidate.overall_score:.1f}."
        )
        fingerprint = f"RECOMMENDATION:{key}:{candidate.recommendation.value}:{candidate.overall_score:.0f}"
        return DetectedChange(
            fingerprint=fingerprint,
            domain=ChangeDomain.RECOMMENDATION,
            entity_id=candidate.ticker,
            label=candidate.company_name or candidate.ticker,
            priority=priority,
            summary=summary,
            previous_value=f"{previous_type.value} ({previous_score:.1f})",
            current_value=f"{candidate.recommendation.value} ({candidate.overall_score:.1f})",
            portfolio_id=portfolio_id,
            event_fingerprint=fingerprint,
            detected_at=_now(),
        )

    # --- Strategy (§16) -----------------------------------------------------------

    async def detect_strategy_change(
        self, portfolio_id: str, label: str, result: StrategyEvaluationResult
    ) -> DetectedChange | None:
        previous_alignment = await self._state.observe_strategy_alignment(portfolio_id, result.overall_alignment)
        if previous_alignment is None:
            return None
        delta = abs(result.overall_alignment - previous_alignment)
        if delta < self._thresholds.strategy_alignment_delta_threshold:
            return None
        fingerprint = f"STRATEGY:{portfolio_id}:{result.overall_alignment:.0f}"
        return DetectedChange(
            fingerprint=fingerprint,
            domain=ChangeDomain.STRATEGY,
            entity_id=portfolio_id,
            label=label,
            priority=priority_from_magnitude(delta, self._thresholds.strategy_alignment_delta_threshold),
            summary=f"Strategy alignment for {label} moved {delta:.1f} points to {result.overall_alignment:.1f}.",
            previous_value=f"{previous_alignment:.1f}",
            current_value=f"{result.overall_alignment:.1f}",
            portfolio_id=portfolio_id,
            event_fingerprint=fingerprint,
            detected_at=_now(),
        )


_STRONG_TYPES = (RecommendationType.STRONG_BUY, RecommendationType.AVOID)


def _recommendation_type_priority(recommendation: RecommendationType) -> ChangePriority:
    """A `RecommendationType` transition's priority reflects how
    actionable the *new* type is — `STRONG_BUY`/`AVOID` are the two types
    this engine's own thresholds reserve for its most confident calls
    (`RecommendationThresholds`, Sprint 49), so a transition *into* either
    is `HIGH`; every other transition (e.g. `HOLD` -> `WATCH`) is `MEDIUM`
    — still worth surfacing (the type changed), never `LOW`/`INFO` (this
    detector only reaches this function when the type genuinely changed)."""
    return ChangePriority.HIGH if recommendation in _STRONG_TYPES else ChangePriority.MEDIUM
