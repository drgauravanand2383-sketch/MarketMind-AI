"""Tests for Milestone 14's additive `RiskAssessment.market_data_coverage`
— purely informational, computed from `RecommendationCandidate.
market_freshness`, never feeding into `overall_risk_score`/`risk_metrics`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.repositories.risk.postgres.models import Base
from app.repositories.risk.postgres.repository import PostgresRiskAnalyticsRepository
from app.risk.engine import RiskAnalyticsService
from app.risk.models import MarketDataCoverageStatus
from app.services.market_snapshot.models import MarketSnapshotStatus
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


async def test_no_market_freshness_anywhere_is_not_evaluated(service: RiskAnalyticsService) -> None:
    """Pre-Milestone-14 shape: candidates with no market_freshness at all."""
    request = await service.create_request("R", "p1", "rec-1")
    result = make_recommendation_result((make_candidate("A"), make_candidate("B")))

    assessment = await service.assess_portfolio(request, result)

    assert assessment.market_data_coverage.status == MarketDataCoverageStatus.NOT_EVALUATED
    assert assessment.market_data_coverage.not_evaluated_count == 2
    assert assessment.market_data_coverage.total_candidates == 2


async def test_empty_portfolio_is_not_evaluated(service: RiskAnalyticsService) -> None:
    request = await service.create_request("R", "p1", "rec-1")
    result = make_recommendation_result(())

    assessment = await service.assess_portfolio(request, result)

    assert assessment.market_data_coverage.status == MarketDataCoverageStatus.NOT_EVALUATED
    assert assessment.market_data_coverage.total_candidates == 0


async def test_all_candidates_fresh_is_full_coverage(service: RiskAnalyticsService) -> None:
    request = await service.create_request("R", "p1", "rec-1")
    result = make_recommendation_result(
        (
            make_candidate("A", market_freshness=MarketSnapshotStatus.FRESH),
            make_candidate("B", market_freshness=MarketSnapshotStatus.STALE),
        )
    )

    assessment = await service.assess_portfolio(request, result)

    assert assessment.market_data_coverage.status == MarketDataCoverageStatus.FULL
    assert assessment.market_data_coverage.fresh_count == 1
    assert assessment.market_data_coverage.stale_count == 1


async def test_mixed_fresh_and_not_evaluated_is_partial_coverage(service: RiskAnalyticsService) -> None:
    request = await service.create_request("R", "p1", "rec-1")
    result = make_recommendation_result(
        (make_candidate("A", market_freshness=MarketSnapshotStatus.FRESH), make_candidate("B"))
    )

    assessment = await service.assess_portfolio(request, result)

    assert assessment.market_data_coverage.status == MarketDataCoverageStatus.PARTIAL
    assert assessment.market_data_coverage.fresh_count == 1
    assert assessment.market_data_coverage.not_evaluated_count == 1


async def test_all_unavailable_is_none_coverage() -> None:
    """Every candidate was evaluated for market data but none came back
    FRESH/STALE (e.g. every ticker unmapped) -> NONE, distinct from
    NOT_EVALUATED (which means market data was never even attempted)."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    repository = PostgresRiskAnalyticsRepository(session_factory)
    service = RiskAnalyticsService(repository, now_fn=lambda: NOW)

    request = await service.create_request("R", "p1", "rec-1")
    result = make_recommendation_result(
        (
            make_candidate("A", market_freshness=MarketSnapshotStatus.ENTITY_NOT_MAPPED),
            make_candidate("B", market_freshness=MarketSnapshotStatus.PROVIDER_UNAVAILABLE),
        )
    )

    assessment = await service.assess_portfolio(request, result)

    assert assessment.market_data_coverage.status == MarketDataCoverageStatus.NONE
    assert assessment.market_data_coverage.unavailable_count == 2

    await engine.dispose()


async def test_market_data_coverage_never_changes_overall_risk_score(
    repository: PostgresRiskAnalyticsRepository,
) -> None:
    """Purely informational (§5): the same candidates, differing only in
    market_freshness, produce byte-identical overall_risk_score/risk_metrics."""
    service_a = RiskAnalyticsService(repository, now_fn=lambda: NOW)
    request_a = await service_a.create_request("A", "p1", "rec-a")
    result_without = make_recommendation_result((make_candidate("A", sector="Tech", country="US"),))
    assessment_without = await service_a.assess_portfolio(request_a, result_without)

    request_b = await service_a.create_request("B", "p1", "rec-b")
    result_with = make_recommendation_result(
        (make_candidate("A", sector="Tech", country="US", market_freshness=MarketSnapshotStatus.FRESH),)
    )
    assessment_with = await service_a.assess_portfolio(request_b, result_with)

    assert assessment_without.overall_risk_score == assessment_with.overall_risk_score
    assert assessment_without.risk_metrics == assessment_with.risk_metrics


async def test_market_data_coverage_persists_across_repository_round_trip(
    service: RiskAnalyticsService,
) -> None:
    request = await service.create_request("R", "p1", "rec-1")
    result = make_recommendation_result((make_candidate("A", market_freshness=MarketSnapshotStatus.FRESH),))

    await service.assess_portfolio(request, result)
    fetched = await service.get_assessment(request.id)

    assert fetched.market_data_coverage.status == MarketDataCoverageStatus.FULL
    assert fetched.market_data_coverage.fresh_count == 1
