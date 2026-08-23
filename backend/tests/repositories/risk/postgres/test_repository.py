"""Tests for PostgresRiskAnalyticsRepository.

Run against an in-memory SQLite database via aiosqlite, exercising the
repository's own CRUD/health-check behavior directly (not through
RiskAnalyticsService) — no business rules (duplicate-name prevention) are
enforced at this layer.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.repositories.risk.postgres.models import Base
from app.repositories.risk.postgres.repository import PostgresRiskAnalyticsRepository
from app.risk.models import (
    PortfolioExposure,
    RiskAssessment,
    RiskAssessmentRequest,
    RiskCategory,
    RiskMetric,
    RiskSeverity,
)

NOW = datetime(2026, 8, 11, tzinfo=UTC)


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


def _request(request_id: str = "r1", name: str = "Value", **overrides: object) -> RiskAssessmentRequest:
    defaults: dict[str, object] = {
        "id": request_id, "request_name": name, "portfolio_id": "p1",
        "recommendation_result_id": "rec-1", "created_at": NOW,
    }
    defaults.update(overrides)
    return RiskAssessmentRequest(**defaults)


def _assessment(request_id: str = "r1", generated_at: datetime = NOW, **overrides: object) -> RiskAssessment:
    defaults: dict[str, object] = {
        "request_id": request_id, "generated_at": generated_at,
        "overall_risk_score": 0.0, "overall_severity": RiskSeverity.LOW, "summary": "x",
    }
    defaults.update(overrides)
    return RiskAssessment(**defaults)


# --- create_request / get_request -----------------------------------------------------------


async def test_create_request_then_get_returns_it(repository: PostgresRiskAnalyticsRepository) -> None:
    await repository.create_request(_request())

    fetched = await repository.get_request("r1")

    assert fetched is not None
    assert fetched.request_name == "Value"


async def test_get_request_missing_returns_none(repository: PostgresRiskAnalyticsRepository) -> None:
    assert await repository.get_request("does-not-exist") is None


async def test_create_request_persists_all_fields(repository: PostgresRiskAnalyticsRepository) -> None:
    request = _request(portfolio_id="my-portfolio", strategy_evaluation_id="strat-1", recommendation_result_id="rec-42")

    await repository.create_request(request)

    fetched = await repository.get_request("r1")
    assert fetched is not None
    assert fetched.portfolio_id == "my-portfolio"
    assert fetched.strategy_evaluation_id == "strat-1"
    assert fetched.recommendation_result_id == "rec-42"


async def test_create_request_with_no_strategy_evaluation_id(
    repository: PostgresRiskAnalyticsRepository,
) -> None:
    await repository.create_request(_request(strategy_evaluation_id=None))

    fetched = await repository.get_request("r1")
    assert fetched is not None
    assert fetched.strategy_evaluation_id is None


# --- list_requests -----------------------------------------------------------


async def test_list_requests_empty_initially(repository: PostgresRiskAnalyticsRepository) -> None:
    assert await repository.list_requests() == []


async def test_list_requests_returns_all(repository: PostgresRiskAnalyticsRepository) -> None:
    await repository.create_request(_request("r1", "A"))
    await repository.create_request(_request("r2", "B"))

    requests = await repository.list_requests()

    assert {r.request_name for r in requests} == {"A", "B"}


# --- store_assessment / get_assessment -----------------------------------------------------------


async def test_store_assessment_then_get_returns_it(repository: PostgresRiskAnalyticsRepository) -> None:
    await repository.store_assessment(_assessment())

    fetched = await repository.get_assessment("r1")

    assert fetched is not None
    assert fetched.request_id == "r1"


async def test_get_assessment_missing_returns_none(repository: PostgresRiskAnalyticsRepository) -> None:
    assert await repository.get_assessment("does-not-exist") is None


async def test_get_assessment_returns_most_recent_when_multiple_stored(
    repository: PostgresRiskAnalyticsRepository,
) -> None:
    await repository.store_assessment(_assessment(generated_at=NOW, overall_risk_score=10.0))
    await repository.store_assessment(_assessment(generated_at=NOW + timedelta(minutes=5), overall_risk_score=90.0))

    latest = await repository.get_assessment("r1")

    assert latest is not None
    assert latest.overall_risk_score == 90.0


async def test_store_assessment_persists_metrics_exposures_and_recommendations(
    repository: PostgresRiskAnalyticsRepository,
) -> None:
    metric = RiskMetric(
        metric_name="Holding Concentration", category=RiskCategory.CONCENTRATION, value=0.5,
        score=50.0, severity=RiskSeverity.HIGH, description="x",
    )
    exposure = PortfolioExposure(sector="Tech", weight=1.0, holding_count=2)
    assessment = _assessment(
        overall_risk_score=50.0, overall_severity=RiskSeverity.HIGH,
        risk_metrics=(metric,), exposures=(exposure,), recommendations=("Reduce concentration",),
    )

    await repository.store_assessment(assessment)

    fetched = await repository.get_assessment("r1")
    assert fetched is not None
    assert fetched.risk_metrics[0].metric_name == "Holding Concentration"
    assert fetched.exposures[0].sector == "Tech"
    assert fetched.recommendations == ("Reduce concentration",)


# --- list_assessments -----------------------------------------------------------


async def test_list_assessments_empty_initially(repository: PostgresRiskAnalyticsRepository) -> None:
    assert await repository.list_assessments() == []


async def test_list_assessments_returns_all_across_requests(
    repository: PostgresRiskAnalyticsRepository,
) -> None:
    await repository.store_assessment(_assessment("r1"))
    await repository.store_assessment(_assessment("r2"))

    assessments = await repository.list_assessments()

    assert {a.request_id for a in assessments} == {"r1", "r2"}


# --- health_check -----------------------------------------------------------


async def test_health_check_true_against_reachable_database(
    repository: PostgresRiskAnalyticsRepository,
) -> None:
    assert await repository.health_check() is True


async def test_health_check_false_when_database_unreachable() -> None:
    broken_engine = create_async_engine("sqlite+aiosqlite:///nonexistent/no/such/path.db")
    session_factory = async_sessionmaker(broken_engine, expire_on_commit=False)

    repository = PostgresRiskAnalyticsRepository(session_factory)

    assert await repository.health_check() is False
