"""Integration tests for ExplainabilityService.explain(): full resolution
via injected Recommendation/Strategy/Risk/Backtesting services,
performance attribution, validation, determinism, and edge cases."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.backtesting.engine import BacktestingService
from app.backtesting.models import HistoricalSnapshot
from app.explainability.engine import ExplainabilityService
from app.explainability.exceptions import InvalidReferenceError
from app.explainability.models import AttributionCategory
from app.risk.models import PortfolioExposure
from tests.explainability.conftest import (
    NOW,
    make_candidate,
    make_recommendation_result,
    make_risk_assessment,
    make_risk_metric,
    make_rule_alignment,
    make_strategy_evaluation_result,
    make_strategy_match,
)

# --- Basic orchestration -----------------------------------------------------------


async def test_explain_returns_and_persists_result(
    service: ExplainabilityService, recommendation_repository
) -> None:
    await recommendation_repository.store_result(make_recommendation_result("rec-1", (make_candidate("A"),)))
    request = await service.create_request("Explain1", "rec-1")

    result = await service.explain(request)

    assert result.request_id == request.id
    fetched = await service.get_result(request.id)
    assert fetched == result


async def test_explain_produces_one_explanation_per_candidate(
    service: ExplainabilityService, recommendation_repository
) -> None:
    candidates = (make_candidate("A"), make_candidate("B"), make_candidate("C"))
    await recommendation_repository.store_result(make_recommendation_result("rec-1", candidates))
    request = await service.create_request("Explain1", "rec-1")

    result = await service.explain(request)

    assert len(result.recommendation_explanations) == 3
    assert {e.ticker for e in result.recommendation_explanations} == {"A", "B", "C"}


async def test_explain_with_only_recommendation_result_id_leaves_others_empty(
    service: ExplainabilityService, recommendation_repository
) -> None:
    await recommendation_repository.store_result(make_recommendation_result("rec-1", (make_candidate("A"),)))
    request = await service.create_request("Minimal", "rec-1")

    result = await service.explain(request)

    assert result.strategy_explanations == ()
    assert result.risk_explanation is None
    assert result.performance_attribution is None


async def test_explain_with_strategy_evaluation_id_populates_strategy_explanations(
    service: ExplainabilityService, recommendation_repository, strategy_repository
) -> None:
    await recommendation_repository.store_result(make_recommendation_result("rec-1", (make_candidate("A"),)))
    match = make_strategy_match("s1", "Value", 80.0)
    await strategy_repository.store_evaluation(make_strategy_evaluation_result("strat-1", (match,)))
    request = await service.create_request("Explain1", "rec-1", strategy_evaluation_id="strat-1")

    result = await service.explain(request)

    assert len(result.strategy_explanations) == 1
    assert result.strategy_explanations[0].strategy_name == "Value"


async def test_explain_with_risk_assessment_id_populates_risk_explanation(
    service: ExplainabilityService, recommendation_repository, risk_repository
) -> None:
    await recommendation_repository.store_result(make_recommendation_result("rec-1", (make_candidate("A"),)))
    await risk_repository.store_assessment(make_risk_assessment("risk-1", overall_risk_score=55.0))
    request = await service.create_request("Explain1", "rec-1", risk_assessment_id="risk-1")

    result = await service.explain(request)

    assert result.risk_explanation is not None
    assert result.risk_explanation.overall_risk_score == 55.0


# --- Performance attribution -----------------------------------------------------------


async def _run_backtest(
    backtesting_service: BacktestingService, recommendation_repository, rec_id_1: str, rec_id_2: str
) -> str:
    request = await backtesting_service.create_request(
        "BT", date(2026, 1, 1), date(2026, 1, 31), 100000.0, "SPY"
    )
    snapshots = [
        HistoricalSnapshot(timestamp=NOW - timedelta(days=1), recommendation_result_id=rec_id_1, benchmark_value=100.0),
        HistoricalSnapshot(timestamp=NOW, recommendation_result_id=rec_id_2, benchmark_value=110.0),
    ]
    await backtesting_service.run_backtest(request, snapshots)
    return request.id


async def test_explain_with_backtest_run_id_populates_performance_attribution(
    service: ExplainabilityService, recommendation_repository, backtesting_service
) -> None:
    await recommendation_repository.store_result(make_recommendation_result("rec-low", (make_candidate("A", 20.0),)))
    await recommendation_repository.store_result(make_recommendation_result("rec-high", (make_candidate("A", 80.0),)))
    backtest_run_id = await _run_backtest(backtesting_service, recommendation_repository, "rec-low", "rec-high")
    request = await service.create_request("Explain1", "rec-high", backtest_run_id=backtest_run_id)

    result = await service.explain(request)

    assert result.performance_attribution is not None
    assert result.performance_attribution.benchmark_return == 10.0


async def test_performance_attribution_returns_copied_verbatim_from_backtest_result(
    service: ExplainabilityService, recommendation_repository, backtesting_service
) -> None:
    await recommendation_repository.store_result(make_recommendation_result("rec-low", (make_candidate("A", 20.0),)))
    await recommendation_repository.store_result(make_recommendation_result("rec-high", (make_candidate("A", 80.0),)))
    backtest_run_id = await _run_backtest(backtesting_service, recommendation_repository, "rec-low", "rec-high")
    backtest_result = await backtesting_service.get_result(backtest_run_id)
    request = await service.create_request("Explain1", "rec-high", backtest_run_id=backtest_run_id)

    result = await service.explain(request)

    assert result.performance_attribution.portfolio_return == backtest_result.portfolio_return
    assert result.performance_attribution.benchmark_return == backtest_result.benchmark_return
    assert result.performance_attribution.excess_return == backtest_result.excess_return


async def test_performance_attribution_includes_strategy_and_risk_categories_when_resolved(
    service: ExplainabilityService, recommendation_repository, strategy_repository, risk_repository, backtesting_service
) -> None:
    await recommendation_repository.store_result(make_recommendation_result("rec-1", (make_candidate("A", 60.0),)))
    await strategy_repository.store_evaluation(make_strategy_evaluation_result("strat-1", overall_alignment=85.0))
    await risk_repository.store_assessment(make_risk_assessment("risk-1", overall_risk_score=25.0))
    backtest_run_id = await _run_backtest(backtesting_service, recommendation_repository, "rec-1", "rec-1")
    request = await service.create_request(
        "Explain1", "rec-1", strategy_evaluation_id="strat-1", risk_assessment_id="risk-1",
        backtest_run_id=backtest_run_id,
    )

    result = await service.explain(request)

    categories = {c.category for c in result.performance_attribution.contribution_breakdown}
    assert AttributionCategory.STRATEGY in categories
    assert AttributionCategory.RISK in categories


async def test_performance_attribution_includes_exposure_categories_when_risk_resolved(
    service: ExplainabilityService, recommendation_repository, risk_repository, backtesting_service
) -> None:
    await recommendation_repository.store_result(make_recommendation_result("rec-1", (make_candidate("A", 60.0),)))
    exposures = (
        PortfolioExposure(sector="Tech", weight=0.7, holding_count=1),
        PortfolioExposure(country="US", weight=1.0, holding_count=1),
        PortfolioExposure(industry="Software", weight=0.5, holding_count=1),
    )
    await risk_repository.store_assessment(make_risk_assessment("risk-1", exposures=exposures))
    backtest_run_id = await _run_backtest(backtesting_service, recommendation_repository, "rec-1", "rec-1")
    request = await service.create_request(
        "Explain1", "rec-1", risk_assessment_id="risk-1", backtest_run_id=backtest_run_id
    )

    result = await service.explain(request)

    categories = {c.category for c in result.performance_attribution.contribution_breakdown}
    assert AttributionCategory.SECTOR in categories
    assert AttributionCategory.COUNTRY in categories
    assert AttributionCategory.INDUSTRY in categories


async def test_performance_attribution_period_describes_first_and_last_snapshot(
    service: ExplainabilityService, recommendation_repository, backtesting_service
) -> None:
    await recommendation_repository.store_result(make_recommendation_result("rec-1", (make_candidate("A"),)))
    backtest_run_id = await _run_backtest(backtesting_service, recommendation_repository, "rec-1", "rec-1")
    request = await service.create_request("Explain1", "rec-1", backtest_run_id=backtest_run_id)

    result = await service.explain(request)

    assert "2 period" in result.performance_attribution.period


# --- Validation -----------------------------------------------------------


async def test_explain_with_invalid_recommendation_reference_raises(service: ExplainabilityService) -> None:
    request = await service.create_request("Bad", "does-not-exist")

    with pytest.raises(InvalidReferenceError):
        await service.explain(request)


async def test_explain_with_invalid_strategy_reference_raises(
    service: ExplainabilityService, recommendation_repository
) -> None:
    await recommendation_repository.store_result(make_recommendation_result("rec-1", (make_candidate("A"),)))
    request = await service.create_request("Bad", "rec-1", strategy_evaluation_id="does-not-exist")

    with pytest.raises(InvalidReferenceError):
        await service.explain(request)


async def test_explain_with_invalid_risk_reference_raises(
    service: ExplainabilityService, recommendation_repository
) -> None:
    await recommendation_repository.store_result(make_recommendation_result("rec-1", (make_candidate("A"),)))
    request = await service.create_request("Bad", "rec-1", risk_assessment_id="does-not-exist")

    with pytest.raises(InvalidReferenceError):
        await service.explain(request)


async def test_explain_with_invalid_backtest_reference_raises(
    service: ExplainabilityService, recommendation_repository
) -> None:
    await recommendation_repository.store_result(make_recommendation_result("rec-1", (make_candidate("A"),)))
    request = await service.create_request("Bad", "rec-1", backtest_run_id="does-not-exist")

    with pytest.raises(InvalidReferenceError):
        await service.explain(request)


# --- Determinism -----------------------------------------------------------


async def test_repeated_explain_calls_produce_identical_outputs(
    service: ExplainabilityService, recommendation_repository, strategy_repository, risk_repository, backtesting_service
) -> None:
    await recommendation_repository.store_result(
        make_recommendation_result("rec-1", (make_candidate("A", 60.0), make_candidate("B", 40.0)))
    )
    await strategy_repository.store_evaluation(
        make_strategy_evaluation_result(
            "strat-1", (make_strategy_match(matched_rules=(make_rule_alignment("r1"),)),)
        )
    )
    await risk_repository.store_assessment(
        make_risk_assessment("risk-1", risk_metrics=(make_risk_metric(),))
    )
    backtest_run_id = await _run_backtest(backtesting_service, recommendation_repository, "rec-1", "rec-1")
    request = await service.create_request(
        "Explain1", "rec-1", strategy_evaluation_id="strat-1", risk_assessment_id="risk-1",
        backtest_run_id=backtest_run_id,
    )

    first = await service.explain(request)
    second = await service.explain(request)

    assert first.recommendation_explanations == second.recommendation_explanations
    assert first.strategy_explanations == second.strategy_explanations
    assert first.risk_explanation == second.risk_explanation
    assert first.performance_attribution == second.performance_attribution


# --- Edge cases -----------------------------------------------------------


async def test_explain_with_zero_candidates_produces_empty_explanations(
    service: ExplainabilityService, recommendation_repository
) -> None:
    await recommendation_repository.store_result(make_recommendation_result("rec-1", ()))
    request = await service.create_request("Empty", "rec-1")

    result = await service.explain(request)

    assert result.recommendation_explanations == ()


async def test_explain_with_no_strategy_matches_produces_empty_strategy_explanations(
    service: ExplainabilityService, recommendation_repository, strategy_repository
) -> None:
    await recommendation_repository.store_result(make_recommendation_result("rec-1", (make_candidate("A"),)))
    await strategy_repository.store_evaluation(make_strategy_evaluation_result("strat-1", ()))
    request = await service.create_request("Explain1", "rec-1", strategy_evaluation_id="strat-1")

    result = await service.explain(request)

    assert result.strategy_explanations == ()


# --- Large datasets -----------------------------------------------------------


async def test_large_recommendation_result_produces_matching_explanation_count(
    service: ExplainabilityService, recommendation_repository
) -> None:
    candidates = tuple(make_candidate(f"T{i}", overall_score=float(i % 101)) for i in range(300))
    await recommendation_repository.store_result(make_recommendation_result("rec-1", candidates))
    request = await service.create_request("Large", "rec-1")

    result = await service.explain(request)

    assert len(result.recommendation_explanations) == 300


# --- Configurable max_categories -----------------------------------------------------------


async def test_max_categories_truncates_contributing_components(
    explainability_repository, recommendation_service, strategy_service, risk_service, backtesting_service,
    recommendation_repository,
) -> None:
    tight_service = ExplainabilityService(
        explainability_repository, recommendation_service, strategy_service, risk_service, backtesting_service,
        max_categories=2,
    )
    await recommendation_repository.store_result(
        make_recommendation_result(
            "rec-1",
            (
                make_candidate(
                    "A", screening_score=80.0, planning_score=60.0, research_score=90.0, portfolio_score=50.0,
                    signal_score=70.0, alert_score=40.0,
                ),
            ),
        )
    )
    request = await tight_service.create_request("Explain1", "rec-1")

    result = await tight_service.explain(request)

    assert len(result.recommendation_explanations[0].contributing_components) == 2
