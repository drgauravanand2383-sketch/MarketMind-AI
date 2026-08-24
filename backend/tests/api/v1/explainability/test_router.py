"""End-to-end tests for the Explainability API (`/api/v1/explainability`)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.recommendations.models import (
    RecommendationCandidate,
    RecommendationResult,
    RecommendationSummary,
    RecommendationType,
)
from app.repositories.recommendations.postgres.repository import PostgresRecommendationRepository
from tests.api.v1._auth_fixtures import make_authenticated_headers

NOW = datetime(2026, 8, 8, tzinfo=UTC)


def _make_recommendation_result(request_id: str) -> RecommendationResult:
    candidate = RecommendationCandidate(
        ticker="AAPL", overall_score=70.0, confidence=80.0, recommendation=RecommendationType.BUY,
        reasoning="x", created_at=NOW,
    )
    return RecommendationResult(
        request_id=request_id, generated_at=NOW, total_candidates=1, recommendations=(candidate,),
        summary=RecommendationSummary(),
    )


def test_create_explanation_requires_authentication(client: TestClient) -> None:
    response = client.post("/api/v1/explainability", json={})
    assert response.status_code == 401


async def test_create_explanation_requires_generate_permission(
    client: TestClient, auth_repository, auth_service
) -> None:
    headers = await make_authenticated_headers(auth_repository, auth_service, permissions=("explainability:read",))
    response = client.post("/api/v1/explainability", json={}, headers=headers)
    assert response.status_code == 403


async def test_create_and_fetch_explanation(
    client: TestClient, auth_headers: dict[str, str], recommendation_repository: PostgresRecommendationRepository
) -> None:
    await recommendation_repository.store_result(_make_recommendation_result("rec-1"))

    response = client.post(
        "/api/v1/explainability",
        json={"name": "Explain AAPL", "recommendation_result_id": "rec-1"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    body = response.json()["data"]
    request_id = body["request_id"]
    assert body["recommendation_explanations"]

    get_response = client.get(f"/api/v1/explainability/{request_id}", headers=auth_headers)
    assert get_response.status_code == 200
    assert get_response.json()["data"]["request_id"] == request_id


def test_get_unknown_explanation_returns_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get(f"/api/v1/explainability/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


async def test_create_explanation_with_invalid_reference_returns_400(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/explainability",
        json={"name": "Bad Explain", "recommendation_result_id": "does-not-exist"},
        headers=auth_headers,
    )
    assert response.status_code == 400


def test_create_explanation_missing_required_field_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post("/api/v1/explainability", json={"name": "X"}, headers=auth_headers)
    assert response.status_code == 422
