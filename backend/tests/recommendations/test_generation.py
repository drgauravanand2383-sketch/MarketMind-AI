"""Tests for PortfolioRecommendationService's request/result management
and `generate_recommendations`: ranking, deterministic ordering,
minimum_score filtering, max_recommendations truncation, summary
aggregation, request/result persistence, duplicate-name prevention, edge
cases, and large candidate sets."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.recommendations.engine import PortfolioRecommendationService
from app.recommendations.exceptions import (
    DuplicateRequestNameError,
    RecommendationRequestNotFoundError,
    RecommendationResultNotFoundError,
)
from app.repositories.recommendations.postgres.models import Base
from app.repositories.recommendations.postgres.repository import PostgresRecommendationRepository
from tests.recommendations.conftest import NOW, make_evidence, make_screen_result


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


@pytest.fixture
def service(repository: PostgresRecommendationRepository) -> PortfolioRecommendationService:
    return PortfolioRecommendationService(repository, now_fn=lambda: NOW)


# --- create_request -----------------------------------------------------------


async def test_create_request_returns_a_request_with_a_generated_id(
    service: PortfolioRecommendationService,
) -> None:
    request = await service.create_request("Q3 Growth")
    assert request.id
    assert request.request_name == "Q3 Growth"


async def test_create_request_and_get_round_trip(service: PortfolioRecommendationService) -> None:
    created = await service.create_request(
        "Q3 Growth",
        watchlist_ids=("wl-1",),
        screening_profile_ids=("sp-1",),
        signal_definition_ids=("sd-1",),
        alert_rule_ids=("ar-1",),
        planning_context={"objective": "growth"},
        max_recommendations=5,
        minimum_score=20.0,
    )

    fetched = await service.get_request(created.id)

    assert fetched.watchlist_ids == ("wl-1",)
    assert fetched.screening_profile_ids == ("sp-1",)
    assert fetched.signal_definition_ids == ("sd-1",)
    assert fetched.alert_rule_ids == ("ar-1",)
    assert fetched.planning_context == {"objective": "growth"}
    assert fetched.max_recommendations == 5
    assert fetched.minimum_score == 20.0


async def test_create_request_duplicate_name_raises(service: PortfolioRecommendationService) -> None:
    await service.create_request("Q3 Growth")
    with pytest.raises(DuplicateRequestNameError):
        await service.create_request("Q3 Growth")


async def test_create_request_duplicate_name_allowed_when_not_enforced(
    repository: PostgresRecommendationRepository,
) -> None:
    lenient_service = PortfolioRecommendationService(repository, enforce_unique_names=False, now_fn=lambda: NOW)
    await lenient_service.create_request("Q3 Growth")
    second = await lenient_service.create_request("Q3 Growth")  # must not raise
    assert second.request_name == "Q3 Growth"


# --- get_request / list_requests -----------------------------------------------------------


async def test_get_request_unknown_id_raises(service: PortfolioRecommendationService) -> None:
    with pytest.raises(RecommendationRequestNotFoundError):
        await service.get_request("does-not-exist")


async def test_list_requests_empty_initially(service: PortfolioRecommendationService) -> None:
    assert await service.list_requests() == []


async def test_list_requests_returns_every_created_request(service: PortfolioRecommendationService) -> None:
    await service.create_request("A")
    await service.create_request("B")
    names = {r.request_name for r in await service.list_requests()}
    assert names == {"A", "B"}


# --- generate_recommendations: filtering / ranking / truncation -------------------------------------


async def test_generate_recommendations_ranks_by_score_descending(
    service: PortfolioRecommendationService,
) -> None:
    request = await service.create_request("R", max_recommendations=10, minimum_score=0.0)
    evidence = [
        make_evidence(ticker="LOW", screening_result=make_screen_result(ticker="LOW", score=10)),
        make_evidence(ticker="HIGH", screening_result=make_screen_result(ticker="HIGH", score=90)),
        make_evidence(ticker="MID", screening_result=make_screen_result(ticker="MID", score=50)),
    ]

    result = await service.generate_recommendations(request, evidence)

    assert [c.ticker for c in result.recommendations] == ["HIGH", "MID", "LOW"]


async def test_generate_recommendations_deterministic_tiebreak_by_ticker(
    service: PortfolioRecommendationService,
) -> None:
    request = await service.create_request("R", max_recommendations=10, minimum_score=0.0)
    evidence = [
        make_evidence(ticker="ZEBRA", screening_result=make_screen_result(ticker="ZEBRA", score=50)),
        make_evidence(ticker="ALPHA", screening_result=make_screen_result(ticker="ALPHA", score=50)),
        make_evidence(ticker="MID", screening_result=make_screen_result(ticker="MID", score=50)),
    ]

    result = await service.generate_recommendations(request, evidence)

    assert [c.ticker for c in result.recommendations] == ["ALPHA", "MID", "ZEBRA"]


async def test_generate_recommendations_ordering_is_independent_of_input_order(
    service: PortfolioRecommendationService,
) -> None:
    request = await service.create_request("R", max_recommendations=10, minimum_score=0.0)
    evidence_forward = [
        make_evidence(ticker="A", screening_result=make_screen_result(ticker="A", score=30)),
        make_evidence(ticker="B", screening_result=make_screen_result(ticker="B", score=70)),
    ]
    evidence_reversed = list(reversed(evidence_forward))

    result_forward = await service.generate_recommendations(request, evidence_forward)
    result_reversed = await service.generate_recommendations(request, evidence_reversed)

    assert [c.ticker for c in result_forward.recommendations] == [c.ticker for c in result_reversed.recommendations]


async def test_generate_recommendations_filters_below_minimum_score(
    service: PortfolioRecommendationService,
) -> None:
    request = await service.create_request("R", max_recommendations=10, minimum_score=50.0)
    evidence = [
        make_evidence(ticker="BELOW", screening_result=make_screen_result(ticker="BELOW", score=40)),
        make_evidence(ticker="AT", screening_result=make_screen_result(ticker="AT", score=50)),
        make_evidence(ticker="ABOVE", screening_result=make_screen_result(ticker="ABOVE", score=60)),
    ]

    result = await service.generate_recommendations(request, evidence)

    assert {c.ticker for c in result.recommendations} == {"AT", "ABOVE"}
    assert result.total_candidates == 3  # total_candidates counts everything evaluated, filtered or not


async def test_generate_recommendations_truncates_to_max_recommendations(
    service: PortfolioRecommendationService,
) -> None:
    request = await service.create_request("R", max_recommendations=2, minimum_score=0.0)
    evidence = [
        make_evidence(ticker=f"T{i}", screening_result=make_screen_result(ticker=f"T{i}", score=i))
        for i in range(10)
    ]

    result = await service.generate_recommendations(request, evidence)

    assert len(result.recommendations) == 2
    assert result.total_candidates == 10


async def test_generate_recommendations_with_empty_evidence(service: PortfolioRecommendationService) -> None:
    request = await service.create_request("R")
    result = await service.generate_recommendations(request, [])
    assert result.total_candidates == 0
    assert result.recommendations == ()
    assert result.summary.average_score == 0.0


# --- Summary aggregation -----------------------------------------------------------


async def test_summary_counts_by_recommendation_type(service: PortfolioRecommendationService) -> None:
    request = await service.create_request("R", max_recommendations=10, minimum_score=0.0)
    evidence = [
        make_evidence(ticker="SB", screening_result=make_screen_result(ticker="SB", score=95)),
        make_evidence(ticker="B", screening_result=make_screen_result(ticker="B", score=80)),
        make_evidence(ticker="W", screening_result=make_screen_result(ticker="W", score=65)),
        make_evidence(ticker="H", screening_result=make_screen_result(ticker="H", score=45)),
        make_evidence(ticker="A", screening_result=make_screen_result(ticker="A", score=5)),
    ]

    result = await service.generate_recommendations(request, evidence)

    assert result.summary.strong_buy == 1
    assert result.summary.buy == 1
    assert result.summary.watch == 1
    assert result.summary.hold == 1
    assert result.summary.avoid == 1


async def test_summary_average_score_and_confidence(service: PortfolioRecommendationService) -> None:
    request = await service.create_request("R", max_recommendations=10, minimum_score=0.0)
    evidence = [
        make_evidence(ticker="A", screening_result=make_screen_result(ticker="A", score=100)),
        make_evidence(ticker="B", screening_result=make_screen_result(ticker="B", score=0)),
    ]

    result = await service.generate_recommendations(request, evidence)

    assert result.summary.average_score == 50.0


# --- store_result / get_result / list_results -----------------------------------------------------------


async def test_generate_recommendations_persists_the_result(service: PortfolioRecommendationService) -> None:
    request = await service.create_request("R")
    evidence = [make_evidence(ticker="A", screening_result=make_screen_result(ticker="A", score=80))]

    await service.generate_recommendations(request, evidence)
    fetched = await service.get_result(request.id)

    assert fetched.request_id == request.id
    assert len(fetched.recommendations) == 1


async def test_get_result_unknown_request_id_raises(service: PortfolioRecommendationService) -> None:
    with pytest.raises(RecommendationResultNotFoundError):
        await service.get_result("does-not-exist")


async def test_get_result_returns_the_most_recent_of_multiple_runs(
    repository: PostgresRecommendationRepository,
) -> None:
    clock = {"t": NOW}
    service_with_clock = PortfolioRecommendationService(repository, now_fn=lambda: clock["t"])
    request = await service_with_clock.create_request("R")

    await service_with_clock.generate_recommendations(
        request, [make_evidence(ticker="A", screening_result=make_screen_result(ticker="A", score=10))]
    )
    clock["t"] = NOW + timedelta(minutes=5)
    await service_with_clock.generate_recommendations(
        request, [make_evidence(ticker="B", screening_result=make_screen_result(ticker="B", score=90))]
    )

    latest = await service_with_clock.get_result(request.id)
    assert latest.recommendations[0].ticker == "B"


async def test_list_results_returns_every_stored_result(service: PortfolioRecommendationService) -> None:
    request_a = await service.create_request("A")
    request_b = await service.create_request("B")
    await service.generate_recommendations(request_a, [])
    await service.generate_recommendations(request_b, [])

    results = await service.list_results()

    assert {r.request_id for r in results} == {request_a.id, request_b.id}


async def test_list_results_empty_initially(service: PortfolioRecommendationService) -> None:
    assert await service.list_results() == []


# --- Large candidate sets -----------------------------------------------------------


async def test_large_candidate_set(service: PortfolioRecommendationService) -> None:
    request = await service.create_request("R", max_recommendations=25, minimum_score=0.0)
    evidence = [
        make_evidence(ticker=f"T{i}", screening_result=make_screen_result(ticker=f"T{i}", score=(i % 101)))
        for i in range(1000)
    ]

    result = await service.generate_recommendations(request, evidence)

    assert result.total_candidates == 1000
    assert len(result.recommendations) == 25
    scores = [c.overall_score for c in result.recommendations]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] == 100.0  # highest possible score present in the set


# --- Different weighting configurations -----------------------------------------------------------


async def test_different_weight_configurations_change_ranking(
    repository: PostgresRecommendationRepository,
) -> None:
    from app.recommendations.models import ScoringWeights

    evidence = [
        make_evidence(
            ticker="SCREEN_HEAVY",
            screening_result=make_screen_result(ticker="SCREEN_HEAVY", score=100),
            planning_score=0.0,
        ),
        make_evidence(
            ticker="PLAN_HEAVY",
            screening_result=make_screen_result(ticker="PLAN_HEAVY", score=0),
            planning_score=100.0,
        ),
    ]

    screening_favoring_service = PortfolioRecommendationService(
        repository,
        weights=ScoringWeights(screening=10.0, planning=1.0, signals=1.0, research=1.0, portfolio=1.0, alerts=1.0),
        now_fn=lambda: NOW,
    )
    request = await screening_favoring_service.create_request("Screening Favored")
    result = await screening_favoring_service.generate_recommendations(request, evidence)
    assert result.recommendations[0].ticker == "SCREEN_HEAVY"

    planning_favoring_service = PortfolioRecommendationService(
        repository,
        weights=ScoringWeights(screening=1.0, planning=10.0, signals=1.0, research=1.0, portfolio=1.0, alerts=1.0),
        now_fn=lambda: NOW,
    )
    request2 = await planning_favoring_service.create_request("Planning Favored")
    result2 = await planning_favoring_service.generate_recommendations(request2, evidence)
    assert result2.recommendations[0].ticker == "PLAN_HEAVY"


# --- Deterministic outputs -----------------------------------------------------------


async def test_generate_recommendations_is_deterministic(service: PortfolioRecommendationService) -> None:
    request = await service.create_request("R", max_recommendations=10, minimum_score=0.0)
    evidence = [
        make_evidence(ticker="A", screening_result=make_screen_result(ticker="A", score=80)),
        make_evidence(ticker="B", screening_result=make_screen_result(ticker="B", score=60)),
    ]

    first = await service.generate_recommendations(request, evidence)
    second = await service.generate_recommendations(request, evidence)

    first_scores = [(c.ticker, c.overall_score) for c in first.recommendations]
    second_scores = [(c.ticker, c.overall_score) for c in second.recommendations]
    assert first_scores == second_scores
