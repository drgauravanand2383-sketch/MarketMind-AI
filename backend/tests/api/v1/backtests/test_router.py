"""End-to-end tests for the Backtesting API (`/api/v1/backtests`)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

from app.recommendations.models import RecommendationCandidate, RecommendationResult, RecommendationSummary, RecommendationType
from app.repositories.recommendations.postgres.repository import PostgresRecommendationRepository
from tests.api.v1._auth_fixtures import make_authenticated_headers

NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


def _make_recommendation_result(request_id: str) -> RecommendationResult:
    candidate = RecommendationCandidate(
        ticker="AAPL", overall_score=70.0, confidence=80.0, recommendation=RecommendationType.BUY,
        reasoning="x", created_at=NOW,
    )
    return RecommendationResult(
        request_id=request_id, generated_at=NOW, total_candidates=1, recommendations=(candidate,),
        summary=RecommendationSummary(),
    )


def test_create_backtest_requires_authentication(client: TestClient) -> None:
    response = client.post("/api/v1/backtests", json={})
    assert response.status_code == 401


async def test_create_backtest_requires_run_permission(
    client: TestClient, auth_repository, auth_service
) -> None:
    headers = await make_authenticated_headers(auth_repository, auth_service, permissions=("backtest:read",))
    response = client.post("/api/v1/backtests", json={}, headers=headers)
    assert response.status_code == 403


async def test_create_and_fetch_backtest(
    client: TestClient, auth_headers: dict[str, str], recommendation_repository: PostgresRecommendationRepository
) -> None:
    await recommendation_repository.store_result(_make_recommendation_result("rec-1"))

    response = client.post(
        "/api/v1/backtests",
        json={
            "name": "Q1 Backtest",
            "start_date": "2026-01-01",
            "end_date": "2026-03-31",
            "initial_capital": 100000.0,
            "benchmark": "SPY",
            "snapshots": [{"timestamp": NOW.isoformat(), "recommendation_result_id": "rec-1"}],
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    body = response.json()["data"]
    run_id = body["request_id"]
    assert body["total_periods"] == 1

    run_response = client.get(f"/api/v1/backtests/{run_id}", headers=auth_headers)
    assert run_response.status_code == 200
    assert run_response.json()["data"]["request_id"] == run_id

    results_response = client.get(f"/api/v1/backtests/{run_id}/results", headers=auth_headers)
    assert results_response.status_code == 200
    assert results_response.json()["data"]["request_id"] == run_id


def test_get_unknown_backtest_run_returns_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get(f"/api/v1/backtests/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


async def test_create_backtest_with_invalid_snapshot_reference_returns_400(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/backtests",
        json={
            "name": "Bad Backtest",
            "start_date": "2026-01-01",
            "end_date": "2026-03-31",
            "initial_capital": 100000.0,
            "benchmark": "SPY",
            "snapshots": [{"timestamp": NOW.isoformat(), "recommendation_result_id": "does-not-exist"}],
        },
        headers=auth_headers,
    )
    assert response.status_code == 400


def test_create_backtest_missing_required_field_returns_422(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/backtests",
        json={"start_date": "2026-01-01", "end_date": "2026-03-31", "initial_capital": 100000.0, "benchmark": "SPY"},
        headers=auth_headers,
    )
    assert response.status_code == 422
