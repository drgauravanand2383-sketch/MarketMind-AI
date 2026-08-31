"""Tests for `classify` (`app.global_markets.ranking.classification`)."""

from __future__ import annotations

from app.global_markets.ranking.classification import RiskClassification, classify


def test_low_confidence_always_classifies_as_insufficient_confidence() -> None:
    """Never guess a tier when the data genuinely doesn't support one —
    regardless of how good the momentum/risk numbers otherwise look."""
    result = classify(momentum_score=95.0, risk_score=95.0, data_confidence_score=10.0)
    assert result is RiskClassification.INSUFFICIENT_CONFIDENCE


def test_strong_momentum_and_low_danger_is_lower_risk() -> None:
    # risk_score is inverted (higher = safer); risk_score=90 -> danger=10 (low).
    result = classify(momentum_score=80.0, risk_score=90.0, data_confidence_score=80.0)
    assert result is RiskClassification.STRONG_MOMENTUM_LOWER_RISK


def test_strong_momentum_and_moderate_danger_is_moderate_risk() -> None:
    # risk_score=50 -> danger=50 (moderate).
    result = classify(momentum_score=80.0, risk_score=50.0, data_confidence_score=80.0)
    assert result is RiskClassification.STRONG_MOMENTUM_MODERATE_RISK


def test_strong_momentum_and_high_danger_is_high_risk() -> None:
    # risk_score=20 -> danger=80 (high, but not extreme).
    result = classify(momentum_score=80.0, risk_score=20.0, data_confidence_score=80.0)
    assert result is RiskClassification.STRONG_MOMENTUM_HIGH_RISK


def test_extreme_momentum_and_extreme_danger_is_extreme() -> None:
    result = classify(momentum_score=95.0, risk_score=10.0, data_confidence_score=80.0)
    assert result is RiskClassification.EXTREME_MOMENTUM_EXTREME_RISK


def test_a_high_performing_but_highly_risky_asset_is_never_labeled_lower_risk() -> None:
    """Explicit product principle: a high-momentum, high-risk asset must
    never be classified as an unqualified 'best opportunity.'"""
    result = classify(momentum_score=90.0, risk_score=15.0, data_confidence_score=90.0)
    assert result not in (RiskClassification.STRONG_MOMENTUM_LOWER_RISK,)


def test_moderate_momentum_is_classified_distinctly_from_strong() -> None:
    result = classify(momentum_score=50.0, risk_score=50.0, data_confidence_score=80.0)
    assert result is RiskClassification.MODERATE_MOMENTUM


def test_weak_momentum_is_classified_distinctly() -> None:
    result = classify(momentum_score=10.0, risk_score=50.0, data_confidence_score=80.0)
    assert result is RiskClassification.WEAK_MOMENTUM


def test_thresholds_are_fully_configurable() -> None:
    """The 'configurable, auditable' requirement — every threshold is a
    keyword argument, not a hidden literal."""
    default_result = classify(momentum_score=60.0, risk_score=50.0, data_confidence_score=80.0)
    lowered_result = classify(
        momentum_score=60.0, risk_score=50.0, data_confidence_score=80.0, strong_momentum_threshold=50.0
    )
    assert default_result is RiskClassification.MODERATE_MOMENTUM
    assert lowered_result is RiskClassification.STRONG_MOMENTUM_MODERATE_RISK
