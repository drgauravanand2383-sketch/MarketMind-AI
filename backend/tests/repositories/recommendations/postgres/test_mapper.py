"""Tests for the Recommendation Postgres mapper: purely structural
round-trips, plus the naive-datetime normalization `_ensure_aware`
performs (mirrors the Alert Postgres mapper's own regression test, Sprint 48)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.recommendations.models import (
    RecommendationCandidate,
    RecommendationRequest,
    RecommendationResult,
    RecommendationSummary,
    RecommendationType,
)
from app.repositories.recommendations.postgres.mapper import (
    model_to_request,
    model_to_result,
    request_to_model,
    result_to_model,
)
from app.repositories.recommendations.postgres.models import (
    RecommendationRequestModel,
    RecommendationResultModel,
)

NOW = datetime(2026, 8, 9, tzinfo=timezone.utc)


def test_request_round_trips() -> None:
    request = RecommendationRequest(
        id="r1",
        request_name="Value",
        watchlist_ids=("wl-1",),
        screening_profile_ids=("sp-1",),
        signal_definition_ids=("sd-1",),
        alert_rule_ids=("ar-1",),
        planning_context={"objective": "growth"},
        max_recommendations=15,
        minimum_score=25.0,
        created_at=NOW,
    )

    model = request_to_model(request)
    restored = model_to_request(model)

    assert restored == request


def test_request_with_no_ids_or_context_round_trips() -> None:
    request = RecommendationRequest(id="r1", request_name="Empty", created_at=NOW)

    model = request_to_model(request)
    restored = model_to_request(model)

    assert restored.watchlist_ids == ()
    assert restored.planning_context == {}


def test_result_with_candidates_round_trips() -> None:
    candidate = RecommendationCandidate(
        ticker="AAPL",
        company_name="Apple",
        overall_score=85.5,
        confidence=90.0,
        recommendation=RecommendationType.BUY,
        reasoning="matched",
        screening_score=80.0,
        planning_score=None,
        created_at=NOW,
    )
    result = RecommendationResult(
        request_id="r1",
        generated_at=NOW,
        total_candidates=1,
        recommendations=(candidate,),
        summary=RecommendationSummary(buy=1, average_score=85.5, average_confidence=90.0),
    )

    model = result_to_model(result)
    restored = model_to_result(model)

    assert restored == result


def test_result_with_no_candidates_round_trips() -> None:
    result = RecommendationResult(
        request_id="r1", generated_at=NOW, total_candidates=0, summary=RecommendationSummary()
    )

    model = result_to_model(result)
    restored = model_to_result(model)

    assert restored.recommendations == ()


def test_model_to_request_normalizes_naive_datetime_to_utc() -> None:
    model = RecommendationRequestModel(
        id="r1", request_name="X", watchlist_ids=[], screening_profile_ids=[],
        signal_definition_ids=[], alert_rule_ids=[], planning_context={},
        max_recommendations=10, minimum_score=0.0,
        created_at=datetime(2026, 1, 1),  # naive, as SQLite round-trips it
    )

    restored = model_to_request(model)

    assert restored.created_at.tzinfo is not None


def test_model_to_result_normalizes_naive_datetime_to_utc() -> None:
    model = RecommendationResultModel(
        request_id="r1", total_candidates=0, recommendations=[], summary={},
        generated_at=datetime(2026, 1, 1),  # naive
    )

    restored = model_to_result(model)

    assert restored.generated_at.tzinfo is not None
