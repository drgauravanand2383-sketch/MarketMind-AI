"""End-to-end tests for the Screening API (`/api/v1/screening`)."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.api.v1._auth_fixtures import make_authenticated_headers
from tests.api.v1.screening.conftest import ALL_SCREENING_PERMISSIONS


def _filter_payload(**overrides: object) -> dict:
    payload = {"id": "f1", "field": "market_cap", "operator": "GREATER_THAN", "value": 1_000_000}
    payload.update(overrides)
    return payload


def test_list_profiles_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/screening/profiles")
    assert response.status_code == 401


async def test_create_profile_requires_create_permission(
    client: TestClient, auth_repository, auth_service
) -> None:
    headers = await make_authenticated_headers(auth_repository, auth_service, permissions=("screening:read",))
    response = client.post("/api/v1/screening/profiles", json={"name": "X"}, headers=headers)
    assert response.status_code == 403


def test_create_list_and_update_profile(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post(
        "/api/v1/screening/profiles",
        json={"name": "Large Cap", "filters": [_filter_payload()]},
        headers=auth_headers,
    )
    assert created.status_code == 201
    profile_id = created.json()["data"]["id"]

    listed = client.get("/api/v1/screening/profiles", headers=auth_headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    updated = client.patch(
        f"/api/v1/screening/profiles/{profile_id}", json={"description": "updated"}, headers=auth_headers
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["description"] == "updated"
    assert updated.json()["data"]["name"] == "Large Cap"


def test_duplicate_profile(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post(
        "/api/v1/screening/profiles",
        json={"name": "Large Cap", "description": "orig", "filters": [_filter_payload()]},
        headers=auth_headers,
    )
    profile_id = created.json()["data"]["id"]

    duplicated = client.post(
        f"/api/v1/screening/profiles/{profile_id}/duplicate",
        json={"new_name": "Large Cap (copy)"},
        headers=auth_headers,
    )

    assert duplicated.status_code == 201
    body = duplicated.json()["data"]
    assert body["id"] != profile_id
    assert body["name"] == "Large Cap (copy)"
    assert body["description"] == "orig"
    assert len(body["filters"]) == 1

    listed = client.get("/api/v1/screening/profiles", headers=auth_headers)
    assert listed.json()["total"] == 2


def test_duplicate_profile_rejects_name_already_in_use(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post("/api/v1/screening/profiles", json={"name": "Large Cap"}, headers=auth_headers)
    profile_id = created.json()["data"]["id"]
    client.post("/api/v1/screening/profiles", json={"name": "Taken"}, headers=auth_headers)

    response = client.post(
        f"/api/v1/screening/profiles/{profile_id}/duplicate", json={"new_name": "Taken"}, headers=auth_headers
    )

    assert response.status_code == 409


def test_duplicate_unknown_profile_returns_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        f"/api/v1/screening/profiles/{uuid.uuid4()}/duplicate", json={"new_name": "X"}, headers=auth_headers
    )
    assert response.status_code == 404


async def test_duplicate_profile_requires_create_permission(
    client: TestClient, auth_repository, auth_service
) -> None:
    creator_headers = await make_authenticated_headers(
        auth_repository, auth_service, permissions=ALL_SCREENING_PERMISSIONS, username="creator"
    )
    created = client.post("/api/v1/screening/profiles", json={"name": "Large Cap"}, headers=creator_headers)
    profile_id = created.json()["data"]["id"]
    read_only_headers = await make_authenticated_headers(
        auth_repository, auth_service, permissions=("screening:read",), username="reader"
    )

    response = client.post(
        f"/api/v1/screening/profiles/{profile_id}/duplicate", json={"new_name": "X"}, headers=read_only_headers
    )

    assert response.status_code == 403


def test_filter_profiles_by_name(client: TestClient, auth_headers: dict[str, str]) -> None:
    client.post("/api/v1/screening/profiles", json={"name": "Large Cap Growth"}, headers=auth_headers)
    client.post("/api/v1/screening/profiles", json={"name": "Small Cap Value"}, headers=auth_headers)

    response = client.get("/api/v1/screening/profiles?name=large", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["data"][0]["name"] == "Large Cap Growth"

    response = client.get("/api/v1/screening/profiles?name=nonexistent", headers=auth_headers)
    assert response.json()["total"] == 0


def test_delete_profile(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post("/api/v1/screening/profiles", json={"name": "Large Cap"}, headers=auth_headers)
    profile_id = created.json()["data"]["id"]

    deleted = client.delete(f"/api/v1/screening/profiles/{profile_id}", headers=auth_headers)
    assert deleted.status_code == 204

    follow_up = client.patch(
        f"/api/v1/screening/profiles/{profile_id}", json={"description": "x"}, headers=auth_headers
    )
    assert follow_up.status_code == 404


def test_run_screening_then_fetch_cached_result(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post(
        "/api/v1/screening/profiles",
        json={"name": "Large Cap", "filters": [_filter_payload()]},
        headers=auth_headers,
    )
    profile_id = created.json()["data"]["id"]

    run = client.post(
        "/api/v1/screening/run",
        json={
            "profile_id": profile_id,
            "companies": [
                {"ticker": "AAPL", "company_name": "Apple", "market_cap": 2_000_000},
                {"ticker": "TINY", "company_name": "Tiny Co", "market_cap": 100},
            ],
        },
        headers=auth_headers,
    )
    assert run.status_code == 201
    body = run.json()["data"]
    result_id = body["result_id"]
    assert body["profile_id"] == profile_id
    passed = {r["ticker"]: r["passed"] for r in body["results"]}
    assert passed == {"AAPL": True, "TINY": False}

    fetched = client.get(f"/api/v1/screening/results/{result_id}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json()["data"]["result_id"] == result_id


def test_run_screening_unknown_profile_returns_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/screening/run",
        json={"profile_id": str(uuid.uuid4()), "companies": [{"ticker": "AAPL", "company_name": "Apple"}]},
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_get_unknown_screening_result_returns_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get(f"/api/v1/screening/results/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


def test_create_profile_rejects_unknown_fields(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post("/api/v1/screening/profiles", json={"name": "X", "bogus": True}, headers=auth_headers)
    assert response.status_code == 422
