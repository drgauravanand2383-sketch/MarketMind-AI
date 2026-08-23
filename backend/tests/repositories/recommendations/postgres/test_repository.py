"""Tests for PostgresRecommendationRepository.

Run against an in-memory SQLite database via aiosqlite, exercising the
repository's own CRUD/health-check behavior directly (not through
PortfolioRecommendationService) — no business rules (duplicate-name
prevention) are enforced at this layer.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.recommendations.models import (
    RecommendationRequest,
    RecommendationResult,
    RecommendationSummary,
)
from app.repositories.recommendations.postgres.models import Base
from app.repositories.recommendations.postgres.repository import PostgresRecommendationRepository

NOW = datetime(2026, 8, 9, tzinfo=UTC)


@pytest.fixture
async def repository() -> AsyncIterator[PostgresRecommendationRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PostgresRecommendationRepository(session_factory)
    finally:
        await engine.dispose()


def _request(request_id: str = "r1", name: str = "Value", **overrides: object) -> RecommendationRequest:
    defaults: dict[str, object] = {"id": request_id, "request_name": name, "created_at": NOW}
    defaults.update(overrides)
    return RecommendationRequest(**defaults)


def _result(request_id: str = "r1", generated_at: datetime = NOW, **overrides: object) -> RecommendationResult:
    defaults: dict[str, object] = {
        "request_id": request_id,
        "generated_at": generated_at,
        "total_candidates": 0,
        "summary": RecommendationSummary(),
    }
    defaults.update(overrides)
    return RecommendationResult(**defaults)


# --- create_request / get_request -----------------------------------------------------------


async def test_create_request_then_get_returns_it(repository: PostgresRecommendationRepository) -> None:
    await repository.create_request(_request())

    fetched = await repository.get_request("r1")

    assert fetched is not None
    assert fetched.request_name == "Value"


async def test_get_request_missing_returns_none(repository: PostgresRecommendationRepository) -> None:
    assert await repository.get_request("does-not-exist") is None


async def test_create_request_persists_id_lists_and_context(
    repository: PostgresRecommendationRepository,
) -> None:
    request = _request(
        watchlist_ids=("wl-1", "wl-2"),
        screening_profile_ids=("sp-1",),
        signal_definition_ids=("sd-1",),
        alert_rule_ids=("ar-1",),
        planning_context={"objective": "growth", "horizon": 12},
        max_recommendations=15,
        minimum_score=25.0,
    )

    await repository.create_request(request)

    fetched = await repository.get_request("r1")
    assert fetched is not None
    assert fetched.watchlist_ids == ("wl-1", "wl-2")
    assert fetched.planning_context == {"objective": "growth", "horizon": 12}
    assert fetched.max_recommendations == 15
    assert fetched.minimum_score == 25.0


# --- list_requests -----------------------------------------------------------


async def test_list_requests_empty_initially(repository: PostgresRecommendationRepository) -> None:
    assert await repository.list_requests() == []


async def test_list_requests_returns_all(repository: PostgresRecommendationRepository) -> None:
    await repository.create_request(_request("r1", "A"))
    await repository.create_request(_request("r2", "B"))

    requests = await repository.list_requests()

    assert {r.request_name for r in requests} == {"A", "B"}


# --- store_result / get_result -----------------------------------------------------------


async def test_store_result_then_get_returns_it(repository: PostgresRecommendationRepository) -> None:
    await repository.store_result(_result())

    fetched = await repository.get_result("r1")

    assert fetched is not None
    assert fetched.request_id == "r1"


async def test_get_result_missing_returns_none(repository: PostgresRecommendationRepository) -> None:
    assert await repository.get_result("does-not-exist") is None


async def test_get_result_returns_most_recent_when_multiple_stored(
    repository: PostgresRecommendationRepository,
) -> None:
    await repository.store_result(_result(generated_at=NOW, total_candidates=1))
    await repository.store_result(_result(generated_at=NOW + timedelta(minutes=5), total_candidates=2))

    latest = await repository.get_result("r1")

    assert latest is not None
    assert latest.total_candidates == 2


async def test_store_result_persists_recommendations_and_summary(
    repository: PostgresRecommendationRepository,
) -> None:
    from app.recommendations.models import RecommendationCandidate, RecommendationType

    candidate = RecommendationCandidate(
        ticker="AAPL",
        overall_score=80.0,
        confidence=90.0,
        recommendation=RecommendationType.BUY,
        reasoning="matched",
        created_at=NOW,
    )
    result = _result(
        total_candidates=1,
        recommendations=(candidate,),
        summary=RecommendationSummary(buy=1, average_score=80.0, average_confidence=90.0),
    )

    await repository.store_result(result)

    fetched = await repository.get_result("r1")
    assert fetched is not None
    assert fetched.recommendations[0].ticker == "AAPL"
    assert fetched.summary.buy == 1


# --- list_results -----------------------------------------------------------


async def test_list_results_empty_initially(repository: PostgresRecommendationRepository) -> None:
    assert await repository.list_results() == []


async def test_list_results_returns_all_across_requests(repository: PostgresRecommendationRepository) -> None:
    await repository.store_result(_result("r1"))
    await repository.store_result(_result("r2"))

    results = await repository.list_results()

    assert {r.request_id for r in results} == {"r1", "r2"}


# --- health_check -----------------------------------------------------------


async def test_health_check_true_against_reachable_database(
    repository: PostgresRecommendationRepository,
) -> None:
    assert await repository.health_check() is True


async def test_health_check_false_when_database_unreachable() -> None:
    broken_engine = create_async_engine("sqlite+aiosqlite:///nonexistent/no/such/path.db")
    session_factory = async_sessionmaker(broken_engine, expire_on_commit=False)

    repository = PostgresRecommendationRepository(session_factory)

    assert await repository.health_check() is False
