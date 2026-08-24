"""Tests for RiskAnalyticsService's risk calculations: diversification,
concentration, sector/geographic exposure, market-cap distribution,
volatility estimation, liquidity scoring, exposure aggregation, severity
mapping, explainability, and edge cases. Constructed directly against
`RiskAnalyticsService.__new__` where no repository is needed (every
calculation method is pure and synchronous) — request management and
`assess_portfolio` persistence tests live in `test_engine_requests.py`.
"""

from __future__ import annotations

import pytest

from app.risk.engine import RiskAnalyticsService
from app.risk.models import RiskCategory, RiskSeverity, RiskThresholds, RiskWeighting
from app.signals.models import SignalCategory
from tests.risk.conftest import make_candidate, make_signal


@pytest.fixture
def service() -> RiskAnalyticsService:
    instance = RiskAnalyticsService.__new__(RiskAnalyticsService)
    instance._weighting = RiskWeighting()
    instance._thresholds = RiskThresholds()
    instance._max_exposures = 20
    return instance


# --- Diversification -----------------------------------------------------------


def test_diversification_fully_concentrated_in_one_sector(service: RiskAnalyticsService) -> None:
    candidates = (make_candidate("A", sector="Tech"), make_candidate("B", sector="Tech"))
    metric = service.calculate_diversification(candidates)
    assert metric.score == 100.0
    assert metric.category == RiskCategory.DIVERSIFICATION


def test_diversification_evenly_spread_across_sectors(service: RiskAnalyticsService) -> None:
    candidates = tuple(make_candidate(f"T{i}", sector=f"Sector{i}") for i in range(5))
    metric = service.calculate_diversification(candidates)
    assert metric.score == 20.0  # 5 sectors at 20% each: HHI = 5*(0.2^2) = 0.2 -> 20


def test_diversification_no_sector_data_is_treated_as_maximally_undiversified(
    service: RiskAnalyticsService,
) -> None:
    candidates = (make_candidate("A", sector=None), make_candidate("B", sector=None))
    metric = service.calculate_diversification(candidates)
    assert metric.score == 100.0


# --- Concentration -----------------------------------------------------------


def test_concentration_single_holding_is_maximal(service: RiskAnalyticsService) -> None:
    metric = service.calculate_concentration((make_candidate("A"),))
    assert metric.score == 100.0
    assert metric.category == RiskCategory.CONCENTRATION


def test_concentration_decreases_with_more_holdings(service: RiskAnalyticsService) -> None:
    two = service.calculate_concentration((make_candidate("A"), make_candidate("B")))
    ten = service.calculate_concentration(tuple(make_candidate(f"T{i}") for i in range(10)))
    assert two.score == 50.0
    assert ten.score == 10.0
    assert ten.score < two.score


def test_concentration_empty_portfolio_is_maximal(service: RiskAnalyticsService) -> None:
    metric = service.calculate_concentration(())
    assert metric.score == 100.0


# --- Sector exposure risk -----------------------------------------------------------


def test_sector_exposure_reflects_largest_single_sector(service: RiskAnalyticsService) -> None:
    candidates = (
        make_candidate("A", sector="Technology"),
        make_candidate("B", sector="Technology"),
        make_candidate("C", sector="Energy"),
    )
    metric = service.calculate_sector_exposure(candidates)
    assert metric.score == pytest.approx(66.67, abs=0.01)
    assert metric.category == RiskCategory.SECTOR


def test_sector_exposure_with_no_sector_data(service: RiskAnalyticsService) -> None:
    metric = service.calculate_sector_exposure((make_candidate("A", sector=None),))
    assert metric.score == 0.0
    assert "No sector data" in metric.description


def test_sector_exposure_differs_from_diversification_for_uneven_distribution(
    service: RiskAnalyticsService,
) -> None:
    """4 sectors at 40/20/20/20 -- diversification (whole-distribution
    HHI) and sector (max-bucket-only) diverge, proving they measure
    different things."""
    candidates = (
        make_candidate("A", sector="S1"), make_candidate("B", sector="S1"),
        make_candidate("C", sector="S2"), make_candidate("D", sector="S3"), make_candidate("E", sector="S4"),
    )
    sector_metric = service.calculate_sector_exposure(candidates)
    diversification_metric = service.calculate_diversification(candidates)
    assert sector_metric.score == 40.0
    assert diversification_metric.score == 28.0  # HHI = 0.4^2+0.2^2*3 = 0.16+0.12 = 0.28
    assert sector_metric.score != diversification_metric.score


# --- Geographic exposure risk -----------------------------------------------------------


def test_geographic_exposure_reflects_largest_single_country(service: RiskAnalyticsService) -> None:
    candidates = (
        make_candidate("A", country="US"), make_candidate("B", country="US"), make_candidate("C", country="India")
    )
    metric = service.calculate_geographic_exposure(candidates)
    assert metric.score == pytest.approx(66.67, abs=0.01)
    assert metric.category == RiskCategory.GEOGRAPHIC


def test_geographic_exposure_with_no_country_data(service: RiskAnalyticsService) -> None:
    metric = service.calculate_geographic_exposure((make_candidate("A", country=None),))
    assert metric.score == 0.0
    assert "No country data" in metric.description


# --- Market-cap distribution (always insufficient data) -----------------------------------------------------------


def test_market_cap_distribution_always_reports_insufficient_data(service: RiskAnalyticsService) -> None:
    metric = service.calculate_market_cap_distribution((make_candidate("A"),))
    assert metric.score == 0.0
    assert metric.severity == RiskSeverity.LOW
    assert metric.category == RiskCategory.MARKET_CAP
    assert "market-cap data is available" in metric.description.lower() or "no market" in metric.description.lower()


def test_market_cap_distribution_never_fabricates_data_regardless_of_candidate_count(
    service: RiskAnalyticsService,
) -> None:
    small = service.calculate_market_cap_distribution((make_candidate("A"),))
    large = service.calculate_market_cap_distribution(tuple(make_candidate(f"T{i}") for i in range(100)))
    assert small.score == large.score == 0.0


# --- Volatility estimation -----------------------------------------------------------


def test_volatility_zero_dispersion_and_no_signals_scores_zero(service: RiskAnalyticsService) -> None:
    candidates = (make_candidate("A", overall_score=50), make_candidate("B", overall_score=50))
    metric = service.estimate_volatility(candidates)
    assert metric.score == 0.0
    assert metric.category == RiskCategory.VOLATILITY


def test_volatility_high_score_dispersion_increases_score(service: RiskAnalyticsService) -> None:
    candidates = (make_candidate("A", overall_score=100), make_candidate("B", overall_score=0))
    metric = service.estimate_volatility(candidates)
    assert metric.score > 0.0


def test_volatility_triggered_signal_contributes_to_score(service: RiskAnalyticsService) -> None:
    candidates = (
        make_candidate(
            "A", overall_score=50, supporting_signals=(make_signal(SignalCategory.VOLATILITY, triggered=True),)
        ),
        make_candidate("B", overall_score=50),
    )
    metric = service.estimate_volatility(candidates)
    assert metric.score == 25.0  # dispersion=0, fraction=1/2 -> 0.5*0 + 0.5*50 = 25


def test_volatility_untriggered_signal_does_not_contribute(service: RiskAnalyticsService) -> None:
    candidates = (
        make_candidate(
            "A", overall_score=50, supporting_signals=(make_signal(SignalCategory.VOLATILITY, triggered=False),)
        ),
    )
    metric = service.estimate_volatility(candidates)
    assert metric.score == 0.0


def test_volatility_non_volatility_category_signal_does_not_contribute(service: RiskAnalyticsService) -> None:
    candidates = (
        make_candidate(
            "A", overall_score=50, supporting_signals=(make_signal(SignalCategory.MOMENTUM, triggered=True),)
        ),
    )
    metric = service.estimate_volatility(candidates)
    assert metric.score == 0.0


def test_volatility_with_empty_portfolio(service: RiskAnalyticsService) -> None:
    metric = service.estimate_volatility(())
    assert metric.score == 0.0


def test_volatility_dispersion_capped_at_100(service: RiskAnalyticsService) -> None:
    candidates = tuple(make_candidate(f"T{i}", overall_score=(0 if i % 2 == 0 else 100)) for i in range(20))
    metric = service.estimate_volatility(candidates)
    assert metric.score <= 100.0


# --- Liquidity scoring -----------------------------------------------------------


def test_liquidity_high_confidence_yields_low_risk_score(service: RiskAnalyticsService) -> None:
    metric = service.calculate_liquidity((make_candidate("A", confidence=100),))
    assert metric.score == 0.0
    assert metric.category == RiskCategory.LIQUIDITY


def test_liquidity_low_confidence_yields_high_risk_score(service: RiskAnalyticsService) -> None:
    metric = service.calculate_liquidity((make_candidate("A", confidence=10),))
    assert metric.score == 90.0


def test_liquidity_averages_across_candidates(service: RiskAnalyticsService) -> None:
    metric = service.calculate_liquidity((make_candidate("A", confidence=90), make_candidate("B", confidence=70)))
    assert metric.value == 80.0
    assert metric.score == 20.0


def test_liquidity_with_empty_portfolio(service: RiskAnalyticsService) -> None:
    metric = service.calculate_liquidity(())
    assert metric.score == 0.0


# --- Exposure aggregation -----------------------------------------------------------


def test_calculate_exposures_produces_sector_country_industry_buckets(
    service: RiskAnalyticsService,
) -> None:
    candidates = (make_candidate("A", sector="Tech", country="US", industry="Software"),)
    exposures = service.calculate_exposures(candidates)
    dimensions_present = {"sector" if e.sector else ("country" if e.country else "industry") for e in exposures}
    assert dimensions_present == {"sector", "country", "industry"}


def test_calculate_exposures_weight_is_equal_per_candidate(service: RiskAnalyticsService) -> None:
    candidates = (
        make_candidate("A", sector="Tech"), make_candidate("B", sector="Tech"), make_candidate("C", sector="Energy")
    )
    exposures = service.calculate_exposures(candidates)
    tech_exposure = next(e for e in exposures if e.sector == "Tech")
    assert tech_exposure.weight == pytest.approx(0.6667, abs=0.001)
    assert tech_exposure.holding_count == 2


def test_calculate_exposures_deterministic_ordering_by_weight_descending(
    service: RiskAnalyticsService,
) -> None:
    candidates = (
        make_candidate("A", sector="Small"),
        make_candidate("B", sector="Big"), make_candidate("C", sector="Big"), make_candidate("D", sector="Big"),
    )
    exposures = service.calculate_exposures(candidates)
    sector_exposures = [e for e in exposures if e.sector is not None]
    assert sector_exposures[0].sector == "Big"
    assert sector_exposures[1].sector == "Small"


def test_calculate_exposures_deterministic_tiebreak_by_value_name(service: RiskAnalyticsService) -> None:
    candidates = (make_candidate("A", sector="Zebra"), make_candidate("B", sector="Alpha"))
    exposures = service.calculate_exposures(candidates)
    sector_exposures = [e.sector for e in exposures if e.sector is not None]
    assert sector_exposures == ["Alpha", "Zebra"]


def test_calculate_exposures_respects_max_exposures() -> None:
    instance = RiskAnalyticsService.__new__(RiskAnalyticsService)
    instance._max_exposures = 2
    candidates = tuple(make_candidate(f"T{i}", sector=f"Sector{i}") for i in range(5))
    exposures = instance.calculate_exposures(candidates)
    sector_exposures = [e for e in exposures if e.sector is not None]
    assert len(sector_exposures) == 2


def test_calculate_exposures_empty_portfolio(service: RiskAnalyticsService) -> None:
    assert service.calculate_exposures(()) == ()


def test_calculate_exposures_ignores_candidates_missing_a_dimension(service: RiskAnalyticsService) -> None:
    candidates = (make_candidate("A", sector="Tech"), make_candidate("B", sector=None))
    exposures = service.calculate_exposures(candidates)
    sector_exposures = [e for e in exposures if e.sector is not None]
    assert len(sector_exposures) == 1
    assert sector_exposures[0].holding_count == 1


# --- Severity mapping -----------------------------------------------------------


def test_severity_matches_configured_thresholds() -> None:
    instance = RiskAnalyticsService.__new__(RiskAnalyticsService)
    instance._thresholds = RiskThresholds(moderate_min=10, high_min=40, critical_min=80)
    candidates = (make_candidate("A"), make_candidate("B"))  # concentration score = 50
    metric = instance.calculate_concentration(candidates)
    assert metric.score == 50.0
    assert metric.severity == RiskSeverity.HIGH  # 40 <= 50 < 80


# --- Explainability -----------------------------------------------------------


def test_every_metric_has_a_non_empty_description(service: RiskAnalyticsService) -> None:
    candidates = (make_candidate("A", sector="Tech", country="US"),)
    for fn in (
        service.calculate_diversification, service.calculate_concentration, service.calculate_sector_exposure,
        service.calculate_geographic_exposure, service.calculate_market_cap_distribution,
        service.estimate_volatility, service.calculate_liquidity,
    ):
        metric = fn(candidates)
        assert metric.description
        assert metric.metric_name


# --- Deterministic outputs -----------------------------------------------------------


def test_calculations_are_deterministic_for_identical_inputs(service: RiskAnalyticsService) -> None:
    candidates = (
        make_candidate("A", overall_score=70, confidence=80, sector="Tech", country="US"),
        make_candidate("B", overall_score=40, confidence=60, sector="Energy", country="India"),
    )
    first = service.calculate_diversification(candidates)
    second = service.calculate_diversification(candidates)
    assert first == second


# --- Edge cases / large portfolios -----------------------------------------------------------


def test_large_portfolio_diversification_and_concentration(service: RiskAnalyticsService) -> None:
    candidates = tuple(make_candidate(f"T{i}", sector=f"Sector{i % 20}") for i in range(1000))
    diversification = service.calculate_diversification(candidates)
    concentration = service.calculate_concentration(candidates)
    assert diversification.score == 5.0  # 20 even sectors: HHI=20*(0.05^2)=0.05 -> 5
    assert concentration.score == 0.1  # 1000 equal holdings: HHI=1/1000 -> 0.1
