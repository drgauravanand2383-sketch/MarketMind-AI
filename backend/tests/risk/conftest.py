"""Shared helpers for Risk Analytics Engine tests."""

from __future__ import annotations

from datetime import datetime, timezone

from app.recommendations.models import RecommendationCandidate, RecommendationResult, RecommendationSummary, RecommendationType
from app.signals.models import SignalCategory, SignalPriority, SignalResult

NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)


def make_signal(
    category: SignalCategory = SignalCategory.VOLATILITY,
    triggered: bool = True,
    score: float = 80.0,
) -> SignalResult:
    return SignalResult(
        ticker="X", signal_name="Signal", category=category, triggered=triggered,
        confidence=90.0, score=score, priority=SignalPriority.HIGH, reason="x", timestamp=NOW,
    )


def make_candidate(
    ticker: str = "AAPL",
    overall_score: float = 50.0,
    confidence: float = 80.0,
    sector: str | None = None,
    country: str | None = None,
    industry: str | None = None,
    supporting_signals: tuple[SignalResult, ...] = (),
    **overrides: object,
) -> RecommendationCandidate:
    defaults: dict[str, object] = {
        "ticker": ticker,
        "overall_score": overall_score,
        "confidence": confidence,
        "recommendation": RecommendationType.HOLD,
        "reasoning": "x",
        "sector": sector,
        "country": country,
        "industry": industry,
        "supporting_signals": supporting_signals,
        "created_at": NOW,
    }
    defaults.update(overrides)
    return RecommendationCandidate(**defaults)


def make_recommendation_result(
    candidates: tuple[RecommendationCandidate, ...] = (), request_id: str = "rec-1"
) -> RecommendationResult:
    return RecommendationResult(
        request_id=request_id,
        generated_at=NOW,
        total_candidates=len(candidates),
        recommendations=candidates,
        summary=RecommendationSummary(),
    )
