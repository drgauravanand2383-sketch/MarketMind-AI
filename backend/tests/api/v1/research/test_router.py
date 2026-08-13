"""End-to-end tests for the Company Research API (`/api/v1/research`)."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.api.v1._auth_fixtures import make_authenticated_headers


def test_create_company_research_requires_authentication(client: TestClient) -> None:
    response = client.post("/api/v1/research/company", json={"company_name": "Apple"})
    assert response.status_code == 401


async def test_create_company_research_requires_run_permission(
    client: TestClient, auth_repository, auth_service
) -> None:
    headers = await make_authenticated_headers(auth_repository, auth_service, permissions=("research:read",))
    response = client.post("/api/v1/research/company", json={"company_name": "Apple"}, headers=headers)
    assert response.status_code == 403


def test_create_and_fetch_company_research(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/research/company", json={"company_name": "Apple", "ticker": "AAPL"}, headers=auth_headers
    )
    assert response.status_code == 201
    body = response.json()["data"]
    request_id = body["request_id"]
    uuid.UUID(request_id)
    assert body["report"]["company_overview"]["company_name"] == "Apple"

    fetched = client.get(f"/api/v1/research/{request_id}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json()["data"]["request_id"] == request_id


def test_batch_company_research(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/research/batch",
        json={"companies": [{"company_name": "Apple"}, {"company_name": "Microsoft"}]},
        headers=auth_headers,
    )
    assert response.status_code == 201
    envelopes = response.json()["data"]
    assert len(envelopes) == 2
    assert {e["report"]["company_overview"]["company_name"] for e in envelopes} == {"Apple", "Microsoft"}
    # each report was cached under its own distinct id
    assert envelopes[0]["request_id"] != envelopes[1]["request_id"]


def test_get_unknown_research_report_returns_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get(f"/api/v1/research/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


def test_create_company_research_missing_company_name_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post("/api/v1/research/company", json={}, headers=auth_headers)
    assert response.status_code == 422


def test_batch_company_research_requires_at_least_one_company(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post("/api/v1/research/batch", json={"companies": []}, headers=auth_headers)
    assert response.status_code == 422
