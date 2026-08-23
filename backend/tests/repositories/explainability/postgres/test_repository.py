"""Tests for PostgresExplainabilityRepository.

Run against an in-memory SQLite database via aiosqlite, exercising the
repository's own CRUD/health-check behavior directly (not through
ExplainabilityService) — no business rules (duplicate-name prevention,
explanation generation) are enforced at this layer.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.explainability.models import ExplainabilityRequest, ExplainabilityResult
from app.repositories.explainability.postgres.models import Base
from app.repositories.explainability.postgres.repository import PostgresExplainabilityRepository

NOW = datetime(2026, 8, 7, tzinfo=UTC)


@pytest.fixture
async def repository() -> AsyncIterator[PostgresExplainabilityRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PostgresExplainabilityRepository(session_factory)
    finally:
        await engine.dispose()


def _request(request_id: str = "r1", name: str = "Explain", **overrides: object) -> ExplainabilityRequest:
    defaults: dict[str, object] = {
        "id": request_id, "name": name, "recommendation_result_id": "rec-1", "created_at": NOW,
    }
    defaults.update(overrides)
    return ExplainabilityRequest(**defaults)


def _result(request_id: str = "r1", generated_at: datetime = NOW, **overrides: object) -> ExplainabilityResult:
    defaults: dict[str, object] = {"request_id": request_id, "generated_at": generated_at, "overall_summary": "x"}
    defaults.update(overrides)
    return ExplainabilityResult(**defaults)


# --- create_request / get_request -----------------------------------------------------------


async def test_create_request_then_get_returns_it(repository: PostgresExplainabilityRepository) -> None:
    await repository.create_request(_request())

    fetched = await repository.get_request("r1")

    assert fetched is not None
    assert fetched.name == "Explain"


async def test_get_request_missing_returns_none(repository: PostgresExplainabilityRepository) -> None:
    assert await repository.get_request("does-not-exist") is None


async def test_create_request_persists_all_optional_references(
    repository: PostgresExplainabilityRepository,
) -> None:
    request = _request(strategy_evaluation_id="s1", risk_assessment_id="k1", backtest_run_id="b1")

    await repository.create_request(request)

    fetched = await repository.get_request("r1")
    assert fetched is not None
    assert fetched.strategy_evaluation_id == "s1"
    assert fetched.risk_assessment_id == "k1"
    assert fetched.backtest_run_id == "b1"


# --- list_requests -----------------------------------------------------------


async def test_list_requests_empty_initially(repository: PostgresExplainabilityRepository) -> None:
    assert await repository.list_requests() == []


async def test_list_requests_returns_all(repository: PostgresExplainabilityRepository) -> None:
    await repository.create_request(_request("r1", "A"))
    await repository.create_request(_request("r2", "B"))

    requests = await repository.list_requests()

    assert {r.name for r in requests} == {"A", "B"}


# --- store_result / get_result -----------------------------------------------------------


async def test_store_result_then_get_returns_it(repository: PostgresExplainabilityRepository) -> None:
    await repository.store_result(_result())

    fetched = await repository.get_result("r1")

    assert fetched is not None
    assert fetched.request_id == "r1"


async def test_get_result_missing_returns_none(repository: PostgresExplainabilityRepository) -> None:
    assert await repository.get_result("does-not-exist") is None


async def test_get_result_returns_most_recent_when_multiple_stored(
    repository: PostgresExplainabilityRepository,
) -> None:
    await repository.store_result(_result(generated_at=NOW, overall_summary="first"))
    await repository.store_result(_result(generated_at=NOW + timedelta(minutes=5), overall_summary="second"))

    latest = await repository.get_result("r1")

    assert latest is not None
    assert latest.overall_summary == "second"


# --- list_results -----------------------------------------------------------


async def test_list_results_empty_initially(repository: PostgresExplainabilityRepository) -> None:
    assert await repository.list_results() == []


async def test_list_results_returns_all_across_requests(repository: PostgresExplainabilityRepository) -> None:
    await repository.store_result(_result("r1"))
    await repository.store_result(_result("r2"))

    results = await repository.list_results()

    assert {r.request_id for r in results} == {"r1", "r2"}


# --- health_check -----------------------------------------------------------


async def test_health_check_true_against_reachable_database(
    repository: PostgresExplainabilityRepository,
) -> None:
    assert await repository.health_check() is True


async def test_health_check_false_when_database_unreachable() -> None:
    broken_engine = create_async_engine("sqlite+aiosqlite:///nonexistent/no/such/path.db")
    session_factory = async_sessionmaker(broken_engine, expire_on_commit=False)

    repository = PostgresExplainabilityRepository(session_factory)

    assert await repository.health_check() is False
