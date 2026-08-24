"""Tests for ChangeDetectionService — significant vs insignificant market/
news/signal/risk/recommendation/strategy changes, first-observation
baseline semantics, and stale-data safety (§20)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.recommendations.models import RecommendationCandidate, RecommendationType
from app.risk.models import RiskAssessment, RiskSeverity
from app.services.continuous_intelligence.config import ContinuousIntelligenceThresholds
from app.services.continuous_intelligence.detector import ChangeDetectionService
from app.services.continuous_intelligence.models import ChangePriority
from app.services.continuous_intelligence.state import InMemoryContinuousIntelligenceStateStore
from app.services.market_snapshot.models import MarketSnapshot, MarketSnapshotResult, MarketSnapshotStatus
from app.signals.models import SignalCategory, SignalPriority, SignalResult
from app.strategy.models import StrategyEvaluationResult, StrategySummary

NOW = datetime(2026, 8, 15, tzinfo=UTC)


def _detector(**overrides: object) -> ChangeDetectionService:
    return ChangeDetectionService(
        InMemoryContinuousIntelligenceStateStore(), ContinuousIntelligenceThresholds(**overrides)
    )


def _snapshot_result(
    price: float, status: MarketSnapshotStatus = MarketSnapshotStatus.FRESH, fetched_at: datetime = NOW
) -> MarketSnapshotResult:
    snapshot = None
    if status in (MarketSnapshotStatus.FRESH, MarketSnapshotStatus.STALE):
        snapshot = MarketSnapshot(
            entity_id="dell", canonical_name="Dell Technologies Inc.", ticker="DELL",
            price=price, quoted_at=fetched_at, fetched_at=fetched_at, provider="Yahoo Finance",
        )
    return MarketSnapshotResult(entity_id="dell", status=status, snapshot=snapshot, reason="test")


# --- Market -----------------------------------------------------------


async def test_market_first_observation_is_never_a_change() -> None:
    detector = _detector()
    assert await detector.detect_market_change("dell", "Dell", _snapshot_result(100.0)) is None


async def test_market_significant_move_detected() -> None:
    detector = _detector(market_change_percent_threshold=3.0)
    await detector.detect_market_change("dell", "Dell", _snapshot_result(100.0))

    change = await detector.detect_market_change("dell", "Dell", _snapshot_result(105.0))

    assert change is not None
    assert change.domain.value == "MARKET"
    assert change.previous_value == "100.00"
    assert change.current_value == "105.00"


async def test_market_insignificant_move_not_detected() -> None:
    detector = _detector(market_change_percent_threshold=3.0)
    await detector.detect_market_change("dell", "Dell", _snapshot_result(100.0))

    change = await detector.detect_market_change("dell", "Dell", _snapshot_result(101.0))

    assert change is None


async def test_market_priority_scales_with_magnitude() -> None:
    detector = _detector(market_change_percent_threshold=2.0)
    await detector.detect_market_change("dell", "Dell", _snapshot_result(100.0))

    big_move = await detector.detect_market_change("dell", "Dell", _snapshot_result(120.0))  # 20% = 10x threshold

    assert big_move is not None
    assert big_move.priority == ChangePriority.CRITICAL


async def test_market_stale_transition_detected_as_medium_priority() -> None:
    detector = _detector()
    await detector.detect_market_change("dell", "Dell", _snapshot_result(100.0, status=MarketSnapshotStatus.FRESH))

    change = await detector.detect_market_change(
        "dell", "Dell", _snapshot_result(100.0, status=MarketSnapshotStatus.STALE)
    )

    assert change is not None
    assert change.priority == ChangePriority.MEDIUM
    assert change.current_value == "STALE"


async def test_market_stale_price_never_compared_as_a_real_move() -> None:
    """§15: stale fallback values must never create a false significant-change event."""
    detector = _detector(market_change_percent_threshold=3.0)
    await detector.detect_market_change("dell", "Dell", _snapshot_result(100.0, status=MarketSnapshotStatus.FRESH))
    await detector.detect_market_change("dell", "Dell", _snapshot_result(100.0, status=MarketSnapshotStatus.STALE))

    # Provider recovers with the SAME stale-carried price re-marked FRESH - no artificial move.
    change = await detector.detect_market_change(
        "dell", "Dell", _snapshot_result(100.0, status=MarketSnapshotStatus.STALE)
    )

    assert change is None


async def test_market_unavailable_never_produces_a_fabricated_price_change() -> None:
    detector = _detector()
    await detector.detect_market_change("dell", "Dell", _snapshot_result(100.0))

    change = await detector.detect_market_change(
        "dell", "Dell", _snapshot_result(0.0, status=MarketSnapshotStatus.PROVIDER_UNAVAILABLE)
    )

    assert change is not None
    assert change.current_value == "PROVIDER_UNAVAILABLE"
    assert change.priority == ChangePriority.LOW


# --- News -----------------------------------------------------------


async def test_news_first_observation_is_never_a_change() -> None:
    detector = _detector()
    assert await detector.detect_news_change("dell", "Dell", frozenset({"r1"})) is None


async def test_news_significant_new_records_detected() -> None:
    detector = _detector(news_significance_threshold=2)
    await detector.detect_news_change("dell", "Dell", frozenset({"r1"}))

    change = await detector.detect_news_change("dell", "Dell", frozenset({"r1", "r2", "r3"}))

    assert change is not None
    assert "2 new" in change.summary


async def test_news_below_threshold_not_detected() -> None:
    detector = _detector(news_significance_threshold=2)
    await detector.detect_news_change("dell", "Dell", frozenset({"r1"}))

    change = await detector.detect_news_change("dell", "Dell", frozenset({"r1", "r2"}))

    assert change is None


async def test_news_duplicate_reprocessing_of_same_records_is_not_a_change() -> None:
    detector = _detector(news_significance_threshold=1)
    await detector.detect_news_change("dell", "Dell", frozenset({"r1", "r2"}))

    change = await detector.detect_news_change("dell", "Dell", frozenset({"r1", "r2"}))

    assert change is None


async def test_news_confidence_newly_crossing_threshold_detected() -> None:
    detector = _detector(news_high_confidence_threshold=0.75)
    await detector.detect_news_confidence_change("dell", "Dell", 0.5)

    change = await detector.detect_news_confidence_change("dell", "Dell", 0.9)

    assert change is not None


async def test_news_confidence_staying_high_is_not_repeatedly_reported() -> None:
    detector = _detector(news_high_confidence_threshold=0.75)
    await detector.detect_news_confidence_change("dell", "Dell", 0.9)

    change = await detector.detect_news_confidence_change("dell", "Dell", 0.92)

    assert change is None


# --- Signal -----------------------------------------------------------


def _signal_result(triggered: bool) -> SignalResult:
    return SignalResult(
        ticker="DELL", signal_name="Breakout", category=SignalCategory.TECHNICAL, triggered=triggered,
        confidence=90.0, score=90.0, priority=SignalPriority.HIGH, reason="x", timestamp=NOW,
    )


async def test_signal_first_observation_is_never_a_change() -> None:
    detector = _detector()
    assert await detector.detect_signal_change("dell", "Dell", "def-1", _signal_result(True)) is None


async def test_signal_transition_to_triggered_detected() -> None:
    detector = _detector()
    await detector.detect_signal_change("dell", "Dell", "def-1", _signal_result(False))

    change = await detector.detect_signal_change("dell", "Dell", "def-1", _signal_result(True))

    assert change is not None
    assert change.priority == ChangePriority.HIGH


async def test_signal_unchanged_state_not_detected() -> None:
    detector = _detector()
    await detector.detect_signal_change("dell", "Dell", "def-1", _signal_result(True))

    change = await detector.detect_signal_change("dell", "Dell", "def-1", _signal_result(True))

    assert change is None


# --- Risk -----------------------------------------------------------


def _risk_assessment(severity: RiskSeverity) -> RiskAssessment:
    return RiskAssessment(
        request_id="r1", overall_risk_score=50.0, overall_severity=severity, summary="x", generated_at=NOW
    )


async def test_risk_first_observation_is_never_a_change() -> None:
    detector = _detector()
    assert await detector.detect_risk_change("wl-1", "My Portfolio", _risk_assessment(RiskSeverity.LOW)) is None


async def test_risk_severity_transition_detected() -> None:
    detector = _detector()
    await detector.detect_risk_change("wl-1", "My Portfolio", _risk_assessment(RiskSeverity.LOW))

    change = await detector.detect_risk_change("wl-1", "My Portfolio", _risk_assessment(RiskSeverity.CRITICAL))

    assert change is not None
    assert change.priority == ChangePriority.CRITICAL
    assert change.portfolio_id == "wl-1"


async def test_risk_same_severity_not_detected() -> None:
    detector = _detector()
    await detector.detect_risk_change("wl-1", "My Portfolio", _risk_assessment(RiskSeverity.HIGH))

    change = await detector.detect_risk_change("wl-1", "My Portfolio", _risk_assessment(RiskSeverity.HIGH))

    assert change is None


# --- Recommendation -----------------------------------------------------------


def _candidate(recommendation: RecommendationType, score: float) -> RecommendationCandidate:
    return RecommendationCandidate(
        ticker="DELL", company_name="Dell", overall_score=score, confidence=80.0,
        recommendation=recommendation, reasoning="x", created_at=NOW,
    )


async def test_recommendation_first_observation_is_never_a_change() -> None:
    detector = _detector()
    assert await detector.detect_recommendation_change("wl-1", _candidate(RecommendationType.HOLD, 50.0)) is None


async def test_recommendation_type_transition_detected() -> None:
    detector = _detector()
    await detector.detect_recommendation_change("wl-1", _candidate(RecommendationType.HOLD, 50.0))

    change = await detector.detect_recommendation_change("wl-1", _candidate(RecommendationType.STRONG_BUY, 95.0))

    assert change is not None
    assert change.priority == ChangePriority.HIGH


async def test_recommendation_score_delta_above_threshold_detected_without_type_change() -> None:
    detector = _detector(recommendation_score_delta_threshold=10.0)
    await detector.detect_recommendation_change("wl-1", _candidate(RecommendationType.BUY, 76.0))

    change = await detector.detect_recommendation_change("wl-1", _candidate(RecommendationType.BUY, 90.0))

    assert change is not None


async def test_recommendation_small_score_wobble_not_detected() -> None:
    detector = _detector(recommendation_score_delta_threshold=10.0)
    await detector.detect_recommendation_change("wl-1", _candidate(RecommendationType.BUY, 76.0))

    change = await detector.detect_recommendation_change("wl-1", _candidate(RecommendationType.BUY, 78.0))

    assert change is None


# --- Strategy -----------------------------------------------------------


def _strategy_result(alignment: float) -> StrategyEvaluationResult:
    return StrategyEvaluationResult(
        request_id="s1", evaluated_at=NOW, overall_alignment=alignment, summary=StrategySummary()
    )


async def test_strategy_first_observation_is_never_a_change() -> None:
    detector = _detector()
    assert await detector.detect_strategy_change("wl-1", "My Portfolio", _strategy_result(50.0)) is None


async def test_strategy_significant_alignment_delta_detected() -> None:
    detector = _detector(strategy_alignment_delta_threshold=10.0)
    await detector.detect_strategy_change("wl-1", "My Portfolio", _strategy_result(50.0))

    change = await detector.detect_strategy_change("wl-1", "My Portfolio", _strategy_result(70.0))

    assert change is not None


async def test_strategy_small_delta_not_detected() -> None:
    detector = _detector(strategy_alignment_delta_threshold=10.0)
    await detector.detect_strategy_change("wl-1", "My Portfolio", _strategy_result(50.0))

    change = await detector.detect_strategy_change("wl-1", "My Portfolio", _strategy_result(55.0))

    assert change is None
