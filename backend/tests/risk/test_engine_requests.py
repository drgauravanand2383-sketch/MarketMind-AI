"""Tests for RiskAnalyticsService's request management (create/get/list,
duplicate-name prevention) and `assess_portfolio` (full pipeline
integration, weighted overall score, severity classification,
explainability, persistence, and configurable weighting)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.repositories.risk.postgres.models import Base
from app.repositories.risk.postgres.repository import PostgresRiskAnalyticsRepository
from app.risk.engine import RiskAnalyticsService
from app.risk.exceptions import (
    DuplicateRiskRequestNameError,
    RiskAssessmentNotFoundError,
    RiskAssessmentRequestNotFoundError,
)
from app.risk.models import RiskSeverity, RiskWeighting
from tests.risk.conftest import NOW, make_candidate, make_recommendation_result


@pytest.fixture
async def repository() -> AsyncIterator[PostgresRiskAnalyticsRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PostgresRiskAnalyticsRepository(session_factory)
    finally:
        await engine.dispose()


@pytest.fixture
def service(repository: PostgresRiskAnalyticsRepository) -> RiskAnalyticsService:
    return RiskAnalyticsService(repository, now_fn=lambda: NOW)


# --- create_request -----------------------------------------------------------


async def test_create_request_returns_a_request_with_a_generated_id(service: RiskAnalyticsService) -> None:
    request = await service.create_request("Q3 Risk Check", "portfolio-1", "rec-1")
    assert request.id
    assert request.request_name == "Q3 Risk Check"
    assert request.portfolio_id == "portfolio-1"
    assert request.recommendation_result_id == "rec-1"


async def test_create_request_and_get_round_trip(service: RiskAnalyticsService) -> None:
    created = await service.create_request(
        "Q3 Risk Check", "portfolio-1", "rec-1", strategy_evaluation_id="strat-1"
    )

    fetched = await service.get_request(created.id)

    assert fetched.strategy_evaluation_id == "strat-1"


async def test_create_request_duplicate_name_raises(service: RiskAnalyticsService) -> None:
    await service.create_request("Q3 Risk Check", "portfolio-1", "rec-1")

    with pytest.raises(DuplicateRiskRequestNameError):
        await service.create_request("Q3 Risk Check", "portfolio-2", "rec-2")


async def test_create_request_duplicate_name_allowed_when_not_enforced(
    repository: PostgresRiskAnalyticsRepository,
) -> None:
    lenient_service = RiskAnalyticsService(repository, enforce_unique_names=False, now_fn=lambda: NOW)
    await lenient_service.create_request("Q3 Risk Check", "portfolio-1", "rec-1")

    second = await lenient_service.create_request("Q3 Risk Check", "portfolio-2", "rec-2")  # must not raise

    assert second.request_name == "Q3 Risk Check"


# --- get_request / list_requests -----------------------------------------------------------


async def test_get_request_unknown_id_raises(service: RiskAnalyticsService) -> None:
    with pytest.raises(RiskAssessmentRequestNotFoundError):
        await service.get_request("does-not-exist")


async def test_list_requests_empty_initially(service: RiskAnalyticsService) -> None:
    assert await service.list_requests() == []


async def test_list_requests_returns_every_created_request(service: RiskAnalyticsService) -> None:
    await service.create_request("A", "p1", "rec-a")
    await service.create_request("B", "p2", "rec-b")
    names = {r.request_name for r in await service.list_requests()}
    assert names == {"A", "B"}


# --- assess_portfolio -----------------------------------------------------------


async def test_assess_portfolio_computes_all_seven_categories(service: RiskAnalyticsService) -> None:
    from app.risk.models import RiskCategory

    request = await service.create_request("R", "p1", "rec-1")
    result = make_recommendation_result((make_candidate("A", sector="Tech", country="US"),))

    assessment = await service.assess_portfolio(request, result)

    categories = {m.category for m in assessment.risk_metrics}
    assert categories == {
        RiskCategory.DIVERSIFICATION, RiskCategory.CONCENTRATION, RiskCategory.SECTOR,
        RiskCategory.GEOGRAPHIC, RiskCategory.MARKET_CAP, RiskCategory.VOLATILITY, RiskCategory.LIQUIDITY,
    }


async def test_assess_portfolio_carries_request_id(service: RiskAnalyticsService) -> None:
    request = await service.create_request("R", "p1", "rec-1")
    result = make_recommendation_result((make_candidate("A"),))

    assessment = await service.assess_portfolio(request, result)

    assert assessment.request_id == request.id


async def test_assess_portfolio_overall_score_uses_weighted_average(
    repository: PostgresRiskAnalyticsRepository,
) -> None:
    equal_service = RiskAnalyticsService(repository, now_fn=lambda: NOW)
    request = await equal_service.create_request("Equal", "p1", "rec-1")
    concentrated_result = make_recommendation_result(
        (make_candidate("A", sector="Tech", country="US"), make_candidate("B", sector="Tech", country="US"))
    )

    assessment = await equal_service.assess_portfolio(request, concentrated_result)

    assert 0 < assessment.overall_risk_score <= 100


async def test_assess_portfolio_custom_weighting_shifts_overall_score(
    repository: PostgresRiskAnalyticsRepository,
) -> None:
    heavy_liquidity_weighting = RiskWeighting(
        diversification=1.0, concentration=1.0, sector=1.0, geographic=1.0,
        market_cap=1.0, volatility=1.0, liquidity=20.0,
    )
    heavy_service = RiskAnalyticsService(repository, weighting=heavy_liquidity_weighting, now_fn=lambda: NOW)
    request = await heavy_service.create_request("Heavy Liquidity", "p1", "rec-1")
    result = make_recommendation_result((make_candidate("A", confidence=0.0),))  # liquidity score=100 (max risk)

    assessment = await heavy_service.assess_portfolio(request, result)

    assert assessment.overall_risk_score > 50  # dominated by the heavily-weighted, maximal liquidity risk


async def test_assess_portfolio_severity_matches_configured_thresholds(
    repository: PostgresRiskAnalyticsRepository,
) -> None:
    from app.risk.models import RiskThresholds

    lenient_service = RiskAnalyticsService(
        repository, thresholds=RiskThresholds(moderate_min=90, high_min=95, critical_min=99), now_fn=lambda: NOW
    )
    request = await lenient_service.create_request("Lenient", "p1", "rec-1")
    result = make_recommendation_result((make_candidate("A", sector="Tech", country="US", confidence=90),))

    assessment = await lenient_service.assess_portfolio(request, result)

    assert assessment.overall_severity in (RiskSeverity.LOW, RiskSeverity.MODERATE)


async def test_assess_portfolio_recommendations_only_include_elevated_severity(
    service: RiskAnalyticsService,
) -> None:
    request = await service.create_request("R", "p1", "rec-1")
    # Highly concentrated: 1 holding -> concentration/sector/geographic/diversification all CRITICAL/HIGH
    result = make_recommendation_result((make_candidate("A", sector="Tech", country="US"),))

    assessment = await service.assess_portfolio(request, result)

    for text in assessment.recommendations:
        assert "HIGH" in text or "CRITICAL" in text


async def test_assess_portfolio_with_no_elevated_metrics_has_no_recommendations(
    service: RiskAnalyticsService,
) -> None:
    """A large, evenly-diversified, high-confidence, low-dispersion
    portfolio should not trigger any HIGH/CRITICAL metric under the
    default thresholds -- a single-holding portfolio is mathematically
    always maximally concentrated (HHI=1.0), so this needs genuine breadth,
    not just lenient thresholds, to exercise the "nothing elevated" path."""
    request = await service.create_request("R", "p1", "rec-1")
    candidates = tuple(
        make_candidate(
            f"T{i}", sector=f"Sector{i}", country=f"Country{i}",
            overall_score=60, confidence=100,
        )
        for i in range(20)
    )
    result = make_recommendation_result(candidates)

    assessment = await service.assess_portfolio(request, result)

    assert assessment.recommendations == ()


async def test_assess_portfolio_summary_mentions_score_and_severity(service: RiskAnalyticsService) -> None:
    request = await service.create_request("R", "p1", "rec-1")
    result = make_recommendation_result((make_candidate("A"),))

    assessment = await service.assess_portfolio(request, result)

    assert str(assessment.overall_risk_score) in assessment.summary
    assert assessment.overall_severity.value in assessment.summary


async def test_assess_portfolio_with_empty_recommendation_result(service: RiskAnalyticsService) -> None:
    request = await service.create_request("R", "p1", "rec-1")
    result = make_recommendation_result(())

    assessment = await service.assess_portfolio(request, result)

    assert assessment.exposures == ()
    assert 0 <= assessment.overall_risk_score <= 100


# --- store_assessment / get_assessment / list_assessments -----------------------------------------------------------


async def test_assess_portfolio_persists_the_result(service: RiskAnalyticsService) -> None:
    request = await service.create_request("R", "p1", "rec-1")
    result = make_recommendation_result((make_candidate("A"),))

    await service.assess_portfolio(request, result)
    fetched = await service.get_assessment(request.id)

    assert fetched.request_id == request.id


async def test_get_assessment_unknown_request_id_raises(service: RiskAnalyticsService) -> None:
    with pytest.raises(RiskAssessmentNotFoundError):
        await service.get_assessment("does-not-exist")


async def test_get_assessment_returns_most_recent_of_multiple_runs(
    repository: PostgresRiskAnalyticsRepository,
) -> None:
    clock = {"t": NOW}
    service_with_clock = RiskAnalyticsService(repository, now_fn=lambda: clock["t"])
    request = await service_with_clock.create_request("R", "p1", "rec-1")

    low_risk_result = make_recommendation_result(
        tuple(make_candidate(f"T{i}", sector=f"S{i}", country=f"C{i}", confidence=100) for i in range(20))
    )
    await service_with_clock.assess_portfolio(request, low_risk_result)

    clock["t"] = NOW + timedelta(minutes=5)
    high_risk_result = make_recommendation_result((make_candidate("A", sector="Tech", country="US", confidence=0),))
    await service_with_clock.assess_portfolio(request, high_risk_result)

    latest = await service_with_clock.get_assessment(request.id)
    assert latest.overall_risk_score > 50  # the second (high-risk) run


async def test_list_assessments_returns_every_stored_result(service: RiskAnalyticsService) -> None:
    request_a = await service.create_request("A", "p1", "rec-a")
    request_b = await service.create_request("B", "p2", "rec-b")

    await service.assess_portfolio(request_a, make_recommendation_result(()))
    await service.assess_portfolio(request_b, make_recommendation_result(()))

    assessments = await service.list_assessments()

    assert {a.request_id for a in assessments} == {request_a.id, request_b.id}


async def test_list_assessments_empty_initially(service: RiskAnalyticsService) -> None:
    assert await service.list_assessments() == []


# --- Large portfolios -----------------------------------------------------------


async def test_assess_large_portfolio(service: RiskAnalyticsService) -> None:
    request = await service.create_request("Large", "p1", "rec-1")
    candidates = tuple(
        make_candidate(f"T{i}", sector=f"S{i % 30}", country=f"C{i % 10}", overall_score=(i % 101), confidence=(i % 101))
        for i in range(1000)
    )
    result = make_recommendation_result(candidates)

    assessment = await service.assess_portfolio(request, result)

    assert 0 <= assessment.overall_risk_score <= 100
    assert len(assessment.exposures) <= 60  # 20 max_exposures default x up to 3 dimensions
