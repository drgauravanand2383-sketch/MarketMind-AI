"""End-to-end tests for the Alert API (`/api/v1/alerts`)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.alerts.engine import AlertService
from app.alerts.models import AlertCondition, AlertOperator
from tests.api.v1._auth_fixtures import make_authenticated_headers

NOW = datetime(2026, 8, 8, tzinfo=UTC)


def _signal_payload(**overrides: object) -> dict:
    payload = {
        "ticker": "AAPL",
        "company_name": "Apple",
        "signal_name": "Value Signal",
        "category": "VALUATION",
        "triggered": True,
        "confidence": 90.0,
        "score": 80.0,
        "priority": "HIGH",
        "reason": "matched",
        "timestamp": NOW.isoformat(),
    }
    payload.update(overrides)
    return payload


def test_list_alerts_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/alerts")
    assert response.status_code == 401


async def test_evaluate_alerts_requires_evaluate_permission(
    client: TestClient, auth_repository, auth_service
) -> None:
    headers = await make_authenticated_headers(auth_repository, auth_service, permissions=("alerts:read",))
    response = client.post("/api/v1/alerts/evaluate", json={"signals": [_signal_payload()]}, headers=headers)
    assert response.status_code == 403


async def test_evaluate_alerts_against_all_enabled_rules_then_list_and_get(
    client: TestClient, auth_headers: dict[str, str], alert_service: AlertService
) -> None:
    await alert_service.create_rule(
        "Value Rule",
        conditions=(AlertCondition(id="c1", field="score", operator=AlertOperator.GREATER_THAN, value=50),),
    )

    response = client.post("/api/v1/alerts/evaluate", json={"signals": [_signal_payload()]}, headers=auth_headers)
    assert response.status_code == 201
    batch = response.json()["data"]
    assert batch["generated"] == 1
    alert_id = batch["alerts"][0]["id"]

    listed = client.get("/api/v1/alerts", headers=auth_headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    fetched = client.get(f"/api/v1/alerts/{alert_id}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json()["data"]["id"] == alert_id


async def test_evaluate_alerts_with_no_matching_conditions_produces_no_alerts(
    client: TestClient, auth_headers: dict[str, str], alert_service: AlertService
) -> None:
    await alert_service.create_rule(
        "Strict Rule",
        conditions=(AlertCondition(id="c1", field="score", operator=AlertOperator.GREATER_THAN, value=999),),
    )

    response = client.post("/api/v1/alerts/evaluate", json={"signals": [_signal_payload()]}, headers=auth_headers)
    assert response.status_code == 201
    body = response.json()["data"]
    assert body["generated"] == 0
    assert body["suppressed"] == 0
    assert body["alerts"] == []


def test_get_unknown_alert_returns_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get(f"/api/v1/alerts/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


def test_evaluate_alerts_requires_at_least_one_signal(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post("/api/v1/alerts/evaluate", json={"signals": []}, headers=auth_headers)
    assert response.status_code == 422
