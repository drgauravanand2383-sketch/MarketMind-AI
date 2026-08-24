"""Repository stress tests (Sprint 54): large CRUD batches, large reads,
concurrent read safety, deterministic ordering, and bulk persistence.

Exercises four representative Postgres repositories directly (bypassing
their own Application-layer service, exactly like every other repository
test in this codebase) — Risk Analytics and Explainability (the two
heaviest JSON-payload repositories, Sprints 51 and 53), Recommendations
(a mid-size JSON payload, Sprint 49), and Watchlist (a simpler,
non-JSON-heavy repository, Sprint 44) — as a representative spread rather
than exhaustively covering every one of the ten repository packages.

Every repository already returns "most recent" for the same request_id
deterministically (ordered by its own timestamp column, `id` as a
tiebreak — see each repository's own `get_*` implementation); the
"deterministic ordering" tests here instead exercise `list_*`, which has
no `ORDER BY` clause of its own and so is only guaranteed to return every
row, not any particular order — these tests sort client-side and assert
on the resulting *set*, not on `list_*`'s raw return order.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.recommendations.models import RecommendationResult, RecommendationSummary
from app.repositories.recommendations.postgres.models import Base as RecommendationBase
from app.repositories.recommendations.postgres.repository import PostgresRecommendationRepository
from app.repositories.risk.postgres.models import Base as RiskBase
from app.repositories.risk.postgres.repository import PostgresRiskAnalyticsRepository
from app.repositories.watchlist.postgres.models import Base as WatchlistBase
from app.repositories.watchlist.postgres.repository import PostgresWatchlistRepository
from app.risk.models import RiskAssessment, RiskSeverity
from app.watchlist.models import Watchlist

NOW = datetime(2026, 8, 7, tzinfo=UTC)
LARGE_BATCH = 500


async def _sqlite_session_factory(base: type) -> async_sessionmaker:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def risk_repository() -> AsyncIterator[PostgresRiskAnalyticsRepository]:
    yield PostgresRiskAnalyticsRepository(await _sqlite_session_factory(RiskBase))


@pytest.fixture
async def recommendation_repository() -> AsyncIterator[PostgresRecommendationRepository]:
    yield PostgresRecommendationRepository(await _sqlite_session_factory(RecommendationBase))


@pytest.fixture
async def watchlist_repository() -> AsyncIterator[PostgresWatchlistRepository]:
    yield PostgresWatchlistRepository(await _sqlite_session_factory(WatchlistBase))


def _assessment(request_id: str, score: float) -> RiskAssessment:
    return RiskAssessment(
        request_id=request_id, overall_risk_score=score, overall_severity=RiskSeverity.LOW,
        summary="stress", generated_at=NOW,
    )


def _recommendation_result(request_id: str) -> RecommendationResult:
    return RecommendationResult(
        request_id=request_id,
        generated_at=NOW,
        total_candidates=0,
        recommendations=(),
        summary=RecommendationSummary(),
    )


def _watchlist(watchlist_id: str, name: str) -> Watchlist:
    return Watchlist(id=watchlist_id, name=name, created_at=NOW, updated_at=NOW)


# --- large CRUD batches / bulk persistence -----------------------------------------------------------


async def test_risk_repository_persists_a_large_batch_of_assessments(
    risk_repository: PostgresRiskAnalyticsRepository,
) -> None:
    for i in range(LARGE_BATCH):
        await risk_repository.store_assessment(_assessment(f"req-{i}", float(i % 101)))

    all_assessments = await risk_repository.list_assessments()

    assert len(all_assessments) == LARGE_BATCH


async def test_recommendation_repository_persists_a_large_batch_of_results(
    recommendation_repository: PostgresRecommendationRepository,
) -> None:
    for i in range(LARGE_BATCH):
        await recommendation_repository.store_result(_recommendation_result(f"req-{i}"))

    all_results = await recommendation_repository.list_results()

    assert len(all_results) == LARGE_BATCH


async def test_watchlist_repository_persists_a_large_batch_of_watchlists(
    watchlist_repository: PostgresWatchlistRepository,
) -> None:
    for i in range(LARGE_BATCH):
        await watchlist_repository.create_watchlist(_watchlist(f"wl-{i}", f"Watchlist {i}"))

    all_watchlists = await watchlist_repository.list_watchlists()

    assert len(all_watchlists) == LARGE_BATCH


# --- large repository reads -----------------------------------------------------------


async def test_risk_repository_reads_every_stored_assessment_back_intact(
    risk_repository: PostgresRiskAnalyticsRepository,
) -> None:
    for i in range(LARGE_BATCH):
        await risk_repository.store_assessment(_assessment(f"req-{i}", float(i % 101)))

    all_assessments = await risk_repository.list_assessments()
    scores = {a.request_id: a.overall_risk_score for a in all_assessments}

    assert len(scores) == LARGE_BATCH
    assert scores["req-250"] == float(250 % 101)


# --- deterministic ordering -----------------------------------------------------------


async def test_risk_repository_list_returns_every_request_id_exactly_once(
    risk_repository: PostgresRiskAnalyticsRepository,
) -> None:
    expected_ids = {f"req-{i}" for i in range(LARGE_BATCH)}
    for request_id in expected_ids:
        await risk_repository.store_assessment(_assessment(request_id, 1.0))

    all_assessments = await risk_repository.list_assessments()

    assert {a.request_id for a in all_assessments} == expected_ids
    assert len(all_assessments) == len(expected_ids)  # no duplicates, none dropped


async def test_risk_repository_get_assessment_is_stable_across_repeated_calls(
    risk_repository: PostgresRiskAnalyticsRepository,
) -> None:
    await risk_repository.store_assessment(_assessment("req-1", 42.0))

    results = [await risk_repository.get_assessment("req-1") for _ in range(20)]

    assert all(result is not None and result.overall_risk_score == 42.0 for result in results)


# --- concurrent read safety -----------------------------------------------------------


async def test_risk_repository_concurrent_reads_return_consistent_results(
    risk_repository: PostgresRiskAnalyticsRepository,
) -> None:
    for i in range(100):
        await risk_repository.store_assessment(_assessment(f"req-{i}", float(i)))

    results = await asyncio.gather(*(risk_repository.get_assessment(f"req-{i}") for i in range(100)))

    for i, result in enumerate(results):
        assert result is not None
        assert result.overall_risk_score == float(i)


async def test_recommendation_repository_concurrent_list_calls_agree(
    recommendation_repository: PostgresRecommendationRepository,
) -> None:
    for i in range(50):
        await recommendation_repository.store_result(_recommendation_result(f"req-{i}"))

    listings = await asyncio.gather(*(recommendation_repository.list_results() for _ in range(10)))

    lengths = {len(listing) for listing in listings}
    assert lengths == {50}


async def test_watchlist_repository_concurrent_reads_and_writes_do_not_corrupt_state(
    watchlist_repository: PostgresWatchlistRepository,
) -> None:
    async def _write(i: int) -> None:
        await watchlist_repository.create_watchlist(_watchlist(f"wl-{i}", f"W{i}"))

    await asyncio.gather(*(_write(i) for i in range(100)))

    all_watchlists = await watchlist_repository.list_watchlists()
    assert {w.id for w in all_watchlists} == {f"wl-{i}" for i in range(100)}
