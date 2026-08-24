"""Tests for PortfolioRecommendationService's scoring: weighted-score
merging of all six components, confidence (data-coverage) calculation,
threshold mapping, explainability, and edge cases. Constructed directly
against `PortfolioRecommendationService.__new__` where no repository is
needed (`score_candidate` is pure and synchronous) — request/result
persistence and ranking-in-context tests live in `test_generation.py`.
"""

from __future__ import annotations

import pytest

from app.alerts.models import AlertStatus
from app.recommendations.engine import PortfolioRecommendationService
from app.recommendations.models import RecommendationThresholds, RecommendationType, ScoringWeights
from tests.recommendations.conftest import (
    NOW,
    make_alert,
    make_evidence,
    make_portfolio_summary,
    make_research_report,
    make_screen_result,
    make_signal,
)


@pytest.fixture
def service() -> PortfolioRecommendationService:
    instance = PortfolioRecommendationService.__new__(PortfolioRecommendationService)
    instance._weights = ScoringWeights()
    instance._thresholds = RecommendationThresholds()
    instance._now_fn = lambda: NOW
    return instance


# --- Merge each individual component -----------------------------------------------------------


def test_screening_score_derived_from_screen_result(service: PortfolioRecommendationService) -> None:
    evidence = make_evidence(screening_result=make_screen_result(score=72.0))
    candidate = service.score_candidate(evidence)
    assert candidate.screening_score == 72.0


def test_signal_score_is_average_of_triggered_signals(service: PortfolioRecommendationService) -> None:
    evidence = make_evidence(signals=(make_signal(score=80), make_signal(score=60)))
    candidate = service.score_candidate(evidence)
    assert candidate.signal_score == 70.0


def test_alert_score_is_average_of_generated_alerts(service: PortfolioRecommendationService) -> None:
    evidence = make_evidence(alerts=(make_alert(score=90, alert_id="a1"), make_alert(score=70, alert_id="a2")))
    candidate = service.score_candidate(evidence)
    assert candidate.alert_score == 80.0


def test_research_score_scaled_from_zero_to_one_confidence(service: PortfolioRecommendationService) -> None:
    evidence = make_evidence(research_report=make_research_report(confidence=0.75))
    candidate = service.score_candidate(evidence)
    assert candidate.research_score == 75.0


def test_portfolio_score_scaled_from_zero_to_one_confidence(service: PortfolioRecommendationService) -> None:
    evidence = make_evidence(portfolio_summary=make_portfolio_summary(confidence=0.6))
    candidate = service.score_candidate(evidence)
    assert candidate.portfolio_score == 60.0


def test_planning_score_passed_through_directly(service: PortfolioRecommendationService) -> None:
    evidence = make_evidence(planning_score=42.0)
    candidate = service.score_candidate(evidence)
    assert candidate.planning_score == 42.0


# --- Filtering: only triggered signals / generated alerts count -------------------------------------


def test_untriggered_signals_excluded_from_signal_score(service: PortfolioRecommendationService) -> None:
    evidence = make_evidence(signals=(make_signal(score=99, triggered=False),))
    candidate = service.score_candidate(evidence)
    assert candidate.signal_score is None
    assert candidate.supporting_signals == ()


def test_mixed_triggered_and_untriggered_signals(service: PortfolioRecommendationService) -> None:
    evidence = make_evidence(signals=(make_signal(score=80, triggered=True), make_signal(score=99, triggered=False)))
    candidate = service.score_candidate(evidence)
    assert candidate.signal_score == 80.0
    assert len(candidate.supporting_signals) == 1


def test_suppressed_alerts_excluded_from_alert_score(service: PortfolioRecommendationService) -> None:
    evidence = make_evidence(alerts=(make_alert(score=99, status=AlertStatus.SUPPRESSED),))
    candidate = service.score_candidate(evidence)
    assert candidate.alert_score is None
    assert candidate.supporting_alerts == ()


def test_mixed_generated_and_suppressed_alerts(service: PortfolioRecommendationService) -> None:
    evidence = make_evidence(
        alerts=(
            make_alert(score=80, status=AlertStatus.GENERATED, alert_id="a1"),
            make_alert(score=99, status=AlertStatus.SUPPRESSED, alert_id="a2"),
        )
    )
    candidate = service.score_candidate(evidence)
    assert candidate.alert_score == 80.0
    assert len(candidate.supporting_alerts) == 1


# --- Weighted scoring -----------------------------------------------------------


def test_overall_score_is_equal_weighted_average_when_weights_equal(
    service: PortfolioRecommendationService,
) -> None:
    evidence = make_evidence(
        screening_result=make_screen_result(score=100),
        planning_score=0.0,
    )
    candidate = service.score_candidate(evidence)
    assert candidate.overall_score == 50.0  # (100 + 0) / 2, equal weights


def test_overall_score_renormalizes_across_only_available_components(
    service: PortfolioRecommendationService,
) -> None:
    """With only one component present, overall_score equals that
    component exactly (renormalized weight = 1.0), not divided by 6."""
    evidence = make_evidence(screening_result=make_screen_result(score=42.0))
    candidate = service.score_candidate(evidence)
    assert candidate.overall_score == 42.0


def test_overall_score_with_no_evidence_is_zero(service: PortfolioRecommendationService) -> None:
    evidence = make_evidence()
    candidate = service.score_candidate(evidence)
    assert candidate.overall_score == 0.0


def test_custom_weights_change_the_weighted_average() -> None:
    instance = PortfolioRecommendationService.__new__(PortfolioRecommendationService)
    instance._weights = ScoringWeights(
        screening=9.0, planning=1.0, signals=1.0, research=1.0, portfolio=1.0, alerts=1.0
    )
    instance._thresholds = RecommendationThresholds()
    instance._now_fn = lambda: NOW

    evidence = make_evidence(screening_result=make_screen_result(score=100), planning_score=0.0)
    candidate = instance.score_candidate(evidence)
    # weighted: (9*100 + 1*0) / (9+1) = 90
    assert candidate.overall_score == 90.0


def test_all_six_components_present_uses_full_weighted_average(
    service: PortfolioRecommendationService,
) -> None:
    evidence = make_evidence(
        screening_result=make_screen_result(score=100),
        signals=(make_signal(score=100),),
        alerts=(make_alert(score=100),),
        research_report=make_research_report(confidence=1.0),
        portfolio_summary=make_portfolio_summary(confidence=1.0),
        planning_score=100.0,
    )
    candidate = service.score_candidate(evidence)
    assert candidate.overall_score == 100.0


# --- Confidence calculation -----------------------------------------------------------


def test_confidence_with_all_six_components_is_100(service: PortfolioRecommendationService) -> None:
    evidence = make_evidence(
        screening_result=make_screen_result(),
        signals=(make_signal(),),
        alerts=(make_alert(),),
        research_report=make_research_report(),
        portfolio_summary=make_portfolio_summary(),
        planning_score=50.0,
    )
    candidate = service.score_candidate(evidence)
    assert candidate.confidence == 100.0


def test_confidence_with_one_component_is_one_sixth(service: PortfolioRecommendationService) -> None:
    evidence = make_evidence(screening_result=make_screen_result())
    candidate = service.score_candidate(evidence)
    assert candidate.confidence == round(1 / 6 * 100, 2)


def test_confidence_with_no_components_is_zero(service: PortfolioRecommendationService) -> None:
    evidence = make_evidence()
    candidate = service.score_candidate(evidence)
    assert candidate.confidence == 0.0


def test_confidence_is_independent_of_overall_score(service: PortfolioRecommendationService) -> None:
    """A low score built from all six sources reports higher confidence
    than a high score built from just one -- confidence measures coverage,
    not quality."""
    full_low = make_evidence(
        screening_result=make_screen_result(score=1),
        signals=(make_signal(score=1),),
        alerts=(make_alert(score=1),),
        research_report=make_research_report(confidence=0.01),
        portfolio_summary=make_portfolio_summary(confidence=0.01),
        planning_score=1.0,
    )
    partial_high = make_evidence(screening_result=make_screen_result(score=100))

    full_low_candidate = service.score_candidate(full_low)
    partial_high_candidate = service.score_candidate(partial_high)

    assert full_low_candidate.overall_score < partial_high_candidate.overall_score
    assert full_low_candidate.confidence > partial_high_candidate.confidence


# --- Recommendation classification -----------------------------------------------------------


@pytest.mark.parametrize(
    "score,expected",
    [
        (95, RecommendationType.STRONG_BUY),
        (80, RecommendationType.BUY),
        (65, RecommendationType.WATCH),
        (45, RecommendationType.HOLD),
        (10, RecommendationType.AVOID),
    ],
)
def test_candidate_recommendation_matches_thresholds(
    service: PortfolioRecommendationService, score: float, expected: RecommendationType
) -> None:
    evidence = make_evidence(screening_result=make_screen_result(score=score))
    candidate = service.score_candidate(evidence)
    assert candidate.recommendation == expected


def test_custom_thresholds_change_classification() -> None:
    instance = PortfolioRecommendationService.__new__(PortfolioRecommendationService)
    instance._weights = ScoringWeights()
    instance._thresholds = RecommendationThresholds(strong_buy_min=50, buy_min=30, watch_min=20, hold_min=10)
    instance._now_fn = lambda: NOW

    evidence = make_evidence(screening_result=make_screen_result(score=35))
    candidate = instance.score_candidate(evidence)
    assert candidate.recommendation == RecommendationType.BUY


# --- Explainability -----------------------------------------------------------


def test_reasoning_mentions_recommendation_and_score(service: PortfolioRecommendationService) -> None:
    evidence = make_evidence(screening_result=make_screen_result(score=80))
    candidate = service.score_candidate(evidence)
    assert candidate.recommendation.value in candidate.reasoning
    assert str(candidate.overall_score) in candidate.reasoning


def test_reasoning_with_no_evidence_says_so(service: PortfolioRecommendationService) -> None:
    evidence = make_evidence()
    candidate = service.score_candidate(evidence)
    assert "no available data sources" in candidate.reasoning


def test_reasoning_mentions_component_contributions(service: PortfolioRecommendationService) -> None:
    evidence = make_evidence(screening_result=make_screen_result(score=80))
    candidate = service.score_candidate(evidence)
    assert "screening=80.0" in candidate.reasoning


def test_candidate_carries_identity_fields(service: PortfolioRecommendationService) -> None:
    evidence = make_evidence(
        ticker="AAPL", company_name="Apple", country="US", sector="Technology", industry="Hardware"
    )
    candidate = service.score_candidate(evidence)
    assert candidate.ticker == "AAPL"
    assert candidate.company_name == "Apple"
    assert candidate.country == "US"
    assert candidate.sector == "Technology"
    assert candidate.industry == "Hardware"


# --- Deterministic outputs -----------------------------------------------------------


def test_scoring_is_deterministic_for_identical_evidence(service: PortfolioRecommendationService) -> None:
    evidence = make_evidence(
        screening_result=make_screen_result(score=72),
        signals=(make_signal(score=65),),
        planning_score=50.0,
    )
    first = service.score_candidate(evidence)
    second = service.score_candidate(evidence)
    assert first.overall_score == second.overall_score
    assert first.confidence == second.confidence
    assert first.recommendation == second.recommendation
