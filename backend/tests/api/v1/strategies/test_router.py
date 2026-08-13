"""End-to-end tests for the Strategy Evaluation API (`/api/v1/strategies`)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

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


def test_list_strategies_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/strategies")
    assert response.status_code == 401


async def test_create_strategy_requires_update_permission(
    client: TestClient, auth_repository, auth_service
) -> None:
    headers = await make_authenticated_headers(auth_repository, auth_service, permissions=("strategy:read",))
    response = client.post("/api/v1/strategies", json={"name": "X"}, headers=headers)
    assert response.status_code == 403


def test_create_list_and_get_strategy(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post("/api/v1/strategies", json={"name": "Value Strategy"}, headers=auth_headers)
    assert created.status_code == 201
    strategy_id = created.json()["data"]["id"]

    listed = client.get("/api/v1/strategies", headers=auth_headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["data"][0]["id"] == strategy_id


def test_update_strategy_partial_patch(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post("/api/v1/strategies", json={"name": "Value Strategy"}, headers=auth_headers)
    strategy_id = created.json()["data"]["id"]

    updated = client.patch(f"/api/v1/strategies/{strategy_id}", json={"enabled": False}, headers=auth_headers)
    assert updated.status_code == 200
    assert updated.json()["data"]["enabled"] is False
    assert updated.json()["data"]["name"] == "Value Strategy"


def test_delete_strategy(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post("/api/v1/strategies", json={"name": "Value Strategy"}, headers=auth_headers)
    strategy_id = created.json()["data"]["id"]

    deleted = client.delete(f"/api/v1/strategies/{strategy_id}", headers=auth_headers)
    assert deleted.status_code == 204

    follow_up = client.patch(f"/api/v1/strategies/{strategy_id}", json={"enabled": False}, headers=auth_headers)
    assert follow_up.status_code == 404


async def test_evaluate_strategies_against_all(
    client: TestClient,
    auth_headers: dict[str, str],
    recommendation_repository: PostgresRecommendationRepository,
) -> None:
    await recommendation_repository.store_result(_make_recommendation_result("rec-1"))
    client.post("/api/v1/strategies", json={"name": "Value Strategy"}, headers=auth_headers)

    response = client.post(
        "/api/v1/strategies/evaluate", json={"recommendation_result_id": "rec-1"}, headers=auth_headers
    )
    assert response.status_code == 201
    body = response.json()["data"]
    result_id = body["request_id"]
    assert len(body["strategy_matches"]) == 1

    fetched = client.get(f"/api/v1/strategies/results/{result_id}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json()["data"]["request_id"] == result_id


def test_get_unknown_strategy_evaluation_returns_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get(f"/api/v1/strategies/results/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


def test_create_strategy_rejects_unknown_fields(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post("/api/v1/strategies", json={"name": "X", "bogus": True}, headers=auth_headers)
    assert response.status_code == 422
