"""Tests for the Portfolio Recommendation Engine's domain models:
ScoringWeights (positive weights), RecommendationThresholds (strictly
descending, no overlap, classify()), CandidateEvidence, RecommendationRequest
(max_recommendations/minimum_score validation), and the result/summary models.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.recommendations.models import (
    RecommendationRequest,
    RecommendationResult,
    RecommendationSummary,
    RecommendationThresholds,
    RecommendationType,
    ScoringWeights,
)
from tests.recommendations.conftest import NOW, make_evidence

# --- ScoringWeights -----------------------------------------------------------


def test_scoring_weights_defaults_are_all_positive() -> None:
    weights = ScoringWeights()
    assert weights.planning > 0
    assert weights.screening > 0
    assert weights.signals > 0
    assert weights.research > 0
    assert weights.portfolio > 0
    assert weights.alerts > 0


@pytest.mark.parametrize("field", ["planning", "screening", "signals", "research", "portfolio", "alerts"])
def test_scoring_weights_rejects_zero_weight(field: str) -> None:
    with pytest.raises(ValidationError):
        ScoringWeights(**{field: 0})


@pytest.mark.parametrize("field", ["planning", "screening", "signals", "research", "portfolio", "alerts"])
def test_scoring_weights_rejects_negative_weight(field: str) -> None:
    with pytest.raises(ValidationError):
        ScoringWeights(**{field: -1})


def test_scoring_weights_accepts_arbitrary_positive_values() -> None:
    weights = ScoringWeights(planning=5.0, screening=0.1, signals=100.0)
    assert weights.planning == 5.0
    assert weights.screening == 0.1
    assert weights.signals == 100.0


def test_scoring_weights_is_frozen() -> None:
    weights = ScoringWeights()
    with pytest.raises(ValidationError):
        weights.screening = 2.0


# --- RecommendationThresholds -----------------------------------------------------------


def test_recommendation_thresholds_defaults() -> None:
    thresholds = RecommendationThresholds()
    assert thresholds.strong_buy_min == 90.0
    assert thresholds.buy_min == 75.0
    assert thresholds.watch_min == 60.0
    assert thresholds.hold_min == 40.0


def test_recommendation_thresholds_rejects_non_descending_order() -> None:
    with pytest.raises(ValidationError):
        RecommendationThresholds(strong_buy_min=50, buy_min=60, watch_min=20, hold_min=10)


def test_recommendation_thresholds_rejects_equal_adjacent_bounds() -> None:
    with pytest.raises(ValidationError):
        RecommendationThresholds(strong_buy_min=90, buy_min=90, watch_min=60, hold_min=40)


def test_recommendation_thresholds_accepts_valid_custom_ordering() -> None:
    thresholds = RecommendationThresholds(strong_buy_min=95, buy_min=80, watch_min=50, hold_min=20)
    assert thresholds.strong_buy_min == 95


@pytest.mark.parametrize("field", ["strong_buy_min", "buy_min", "watch_min", "hold_min"])
def test_recommendation_thresholds_rejects_out_of_range(field: str) -> None:
    with pytest.raises(ValidationError):
        RecommendationThresholds(**{field: 150})
    with pytest.raises(ValidationError):
        RecommendationThresholds(**{field: -1})


# --- RecommendationThresholds.classify -----------------------------------------------------------


@pytest.mark.parametrize(
    "score,expected",
    [
        (100, RecommendationType.STRONG_BUY),
        (90, RecommendationType.STRONG_BUY),
        (89.99, RecommendationType.BUY),
        (75, RecommendationType.BUY),
        (74.99, RecommendationType.WATCH),
        (60, RecommendationType.WATCH),
        (59.99, RecommendationType.HOLD),
        (40, RecommendationType.HOLD),
        (39.99, RecommendationType.AVOID),
        (0, RecommendationType.AVOID),
    ],
)
def test_classify_default_thresholds(score: float, expected: RecommendationType) -> None:
    assert RecommendationThresholds().classify(score) == expected


def test_classify_with_custom_thresholds() -> None:
    thresholds = RecommendationThresholds(strong_buy_min=50, buy_min=30, watch_min=20, hold_min=10)
    assert thresholds.classify(10) == RecommendationType.HOLD
    assert thresholds.classify(9.99) == RecommendationType.AVOID
    assert thresholds.classify(50) == RecommendationType.STRONG_BUY


def test_no_overlap_every_score_maps_to_exactly_one_type() -> None:
    """Every integer score 0-100 maps to exactly one RecommendationType --
    proof there is no gap or overlap in the threshold bands."""
    thresholds = RecommendationThresholds()
    for score in range(0, 101):
        result = thresholds.classify(score)
        assert result in RecommendationType


# --- CandidateEvidence -----------------------------------------------------------


def test_candidate_evidence_requires_ticker() -> None:
    with pytest.raises(ValidationError):
        make_evidence(ticker="")


def test_candidate_evidence_ticker_is_normalized() -> None:
    evidence = make_evidence(ticker="  aapl  ")
    assert evidence.ticker == "AAPL"


def test_candidate_evidence_all_sources_optional() -> None:
    evidence = make_evidence()
    assert evidence.screening_result is None
    assert evidence.signals == ()
    assert evidence.alerts == ()
    assert evidence.research_report is None
    assert evidence.portfolio_summary is None
    assert evidence.planning_score is None


def test_candidate_evidence_planning_score_must_be_in_range() -> None:
    with pytest.raises(ValidationError):
        make_evidence(planning_score=150)
    with pytest.raises(ValidationError):
        make_evidence(planning_score=-1)


# --- RecommendationRequest -----------------------------------------------------------


def test_recommendation_request_requires_name() -> None:
    with pytest.raises(ValidationError):
        RecommendationRequest(id="r1", request_name="", created_at=NOW)


def test_recommendation_request_max_recommendations_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        RecommendationRequest(id="r1", request_name="X", created_at=NOW, max_recommendations=0)


def test_recommendation_request_minimum_score_must_be_in_range() -> None:
    with pytest.raises(ValidationError):
        RecommendationRequest(id="r1", request_name="X", created_at=NOW, minimum_score=150)
    with pytest.raises(ValidationError):
        RecommendationRequest(id="r1", request_name="X", created_at=NOW, minimum_score=-1)


def test_recommendation_request_defaults() -> None:
    request = RecommendationRequest(id="r1", request_name="X", created_at=NOW)
    assert request.max_recommendations == 10
    assert request.minimum_score == 0.0
    assert request.watchlist_ids == ()
    assert request.planning_context == {}


def test_recommendation_request_is_frozen() -> None:
    request = RecommendationRequest(id="r1", request_name="X", created_at=NOW)
    with pytest.raises(ValidationError):
        request.request_name = "Y"


# --- RecommendationSummary / RecommendationResult -----------------------------------------------------------


def test_recommendation_summary_defaults_to_zero() -> None:
    summary = RecommendationSummary()
    assert summary.strong_buy == 0
    assert summary.average_score == 0.0


def test_recommendation_result_construction() -> None:
    result = RecommendationResult(
        request_id="r1", generated_at=NOW, total_candidates=0, summary=RecommendationSummary()
    )
    assert result.recommendations == ()
