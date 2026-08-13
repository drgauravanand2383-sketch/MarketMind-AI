"""End-to-end tests for the Signal Detection API (`/api/v1/signals`)."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.api.v1._auth_fixtures import make_authenticated_headers


def _condition_payload(**overrides: object) -> dict:
    payload = {"id": "c1", "field": "quote.price", "operator": "GREATER_THAN", "value": 100}
    payload.update(overrides)
    return payload


def test_list_definitions_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/signals/definitions")
    assert response.status_code == 401


async def test_create_definition_requires_update_permission(
    client: TestClient, auth_repository, auth_service
) -> None:
    headers = await make_authenticated_headers(auth_repository, auth_service, permissions=("signals:read",))
    response = client.post("/api/v1/signals/definitions", json={"name": "X"}, headers=headers)
    assert response.status_code == 403


def test_create_list_and_update_definition(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post(
        "/api/v1/signals/definitions",
        json={"name": "Price Breakout", "conditions": [_condition_payload()]},
        headers=auth_headers,
    )
    assert created.status_code == 201
    definition_id = created.json()["data"]["id"]

    listed = client.get("/api/v1/signals/definitions", headers=auth_headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    updated = client.patch(
        f"/api/v1/signals/definitions/{definition_id}", json={"enabled": False}, headers=auth_headers
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["enabled"] is False
    assert updated.json()["data"]["name"] == "Price Breakout"


def test_delete_definition(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post("/api/v1/signals/definitions", json={"name": "Price Breakout"}, headers=auth_headers)
    definition_id = created.json()["data"]["id"]

    deleted = client.delete(f"/api/v1/signals/definitions/{definition_id}", headers=auth_headers)
    assert deleted.status_code == 204

    follow_up = client.patch(
        f"/api/v1/signals/definitions/{definition_id}", json={"enabled": False}, headers=auth_headers
    )
    assert follow_up.status_code == 404


def test_evaluate_signals_then_fetch_cached_result(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post(
        "/api/v1/signals/definitions",
        json={"name": "Price Breakout", "conditions": [_condition_payload()]},
        headers=auth_headers,
    )
    definition_id = created.json()["data"]["id"]

    evaluated = client.post(
        "/api/v1/signals/evaluate",
        json={"definition_id": definition_id, "snapshots": [{"ticker": "AAPL", "company_name": "Apple"}]},
        headers=auth_headers,
    )
    assert evaluated.status_code == 201
    body = evaluated.json()["data"]
    result_id = body["result_id"]
    assert body["definition_id"] == definition_id
    assert body["batch_result"]["evaluated"] == 1

    fetched = client.get(f"/api/v1/signals/results/{result_id}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json()["data"]["result_id"] == result_id


def test_evaluate_signals_unknown_definition_returns_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/signals/evaluate",
        json={"definition_id": str(uuid.uuid4()), "snapshots": [{"ticker": "AAPL"}]},
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_get_unknown_signal_result_returns_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get(f"/api/v1/signals/results/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


def test_create_definition_rejects_unknown_fields(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post("/api/v1/signals/definitions", json={"name": "X", "bogus": True}, headers=auth_headers)
    assert response.status_code == 422
