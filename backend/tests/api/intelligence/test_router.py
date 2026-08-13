"""Tests for the Intelligence Query API.

Covers: basic API behavior, request validation, dependency resolution
(including the 503 "not configured" path), and error handling. Every
request runs against an in-process FastAPI TestClient — no real HTTP,
database, or embedding API call occurs anywhere.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.intelligence.dependencies import get_morning_pipeline
from app.services.relationship_engine.engine import RelationshipEngine
from tests.api.intelligence.conftest import (
    build_client,
    build_configured_app,
    build_unconfigured_client,
)
from tests.workflows.morning_pipeline.conftest import build_pipeline

# --- API tests -----------------------------------------------------------


def test_company_research_endpoint_returns_report() -> None:
    client = build_client()

    response = client.post("/company/research", json={"company_name": "Apple"})

    assert response.status_code == 200
    body = response.json()
    assert body["report"]["company_overview"]["company_name"] == "Apple Inc."
    assert "execution_id" in body
    assert "trace_id" in body


def test_portfolio_research_endpoint_returns_report() -> None:
    client = build_client()

    response = client.post(
        "/portfolio/research",
        json={"portfolio_name": "My Portfolio", "companies": [{"company_name": "Apple"}]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["report"]["portfolio_overview"]["portfolio_name"] == "My Portfolio"
    assert body["report"]["portfolio_overview"]["holding_count"] == 1
    assert "execution_id" in body


def test_morning_run_endpoint_returns_pipeline_result() -> None:
    client = build_client()

    response = client.post("/morning/run", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert len(body["stage_metrics"]) == 8
    assert "execution_id" in body


def test_health_endpoint_returns_ok() -> None:
    client = build_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


# --- Validation tests -----------------------------------------------------------


def test_company_research_rejects_missing_company_name() -> None:
    client = build_client()

    response = client.post("/company/research", json={})

    assert response.status_code == 422


def test_company_research_rejects_extra_fields() -> None:
    client = build_client()

    response = client.post(
        "/company/research", json={"company_name": "Apple", "unexpected_field": "x"}
    )

    assert response.status_code == 422


def test_portfolio_research_rejects_missing_portfolio_name() -> None:
    client = build_client()

    response = client.post("/portfolio/research", json={"companies": []})

    assert response.status_code == 422


def test_portfolio_research_accepts_empty_holdings_list() -> None:
    client = build_client()

    response = client.post(
        "/portfolio/research", json={"portfolio_name": "Empty Portfolio", "companies": []}
    )

    assert response.status_code == 200
    assert response.json()["report"]["portfolio_overview"]["holding_count"] == 0


def test_morning_run_accepts_empty_body() -> None:
    client = build_client()

    response = client.post("/morning/run", json={})

    assert response.status_code == 200


# --- Dependency tests -----------------------------------------------------------


def test_company_research_returns_503_when_unconfigured() -> None:
    client = build_unconfigured_client()

    response = client.post("/company/research", json={"company_name": "Apple"})

    assert response.status_code == 503
    assert "not configured" in response.json()["detail"].lower()


def test_portfolio_research_returns_503_when_unconfigured() -> None:
    client = build_unconfigured_client()

    response = client.post(
        "/portfolio/research", json={"portfolio_name": "P", "companies": []}
    )

    assert response.status_code == 503


def test_morning_run_returns_503_when_unconfigured() -> None:
    client = build_unconfigured_client()

    response = client.post("/morning/run", json={})

    assert response.status_code == 503


def test_health_does_not_require_any_configuration() -> None:
    client = build_unconfigured_client()

    response = client.get("/health")

    assert response.status_code == 200


def test_dependency_override_is_used_instead_of_raising() -> None:
    """Confirms overriding get_company_research_agent bypasses the
    AgentRuntime/repository dependency chain entirely."""
    client = build_client()

    response = client.post("/company/research", json={"company_name": "Apple"})

    assert response.status_code == 200


# --- Error handling tests -----------------------------------------------------------


def test_morning_run_stage_failure_returns_200_with_failed_status_not_500() -> None:
    class _BrokenRelationshipEngine(RelationshipEngine):
        def build_graph(self, intelligence):  # noqa: ANN001
            raise RuntimeError("simulated relationship engine failure")

    app = build_configured_app()
    app.dependency_overrides[get_morning_pipeline] = lambda: build_pipeline(
        relationship_engine=_BrokenRelationshipEngine()
    )

    client = TestClient(app)
    response = client.post("/morning/run", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["failed_stage"] == "relationship_engine"


def test_company_research_unconfigured_returns_503_not_500() -> None:
    client = build_unconfigured_client()

    response = client.post("/company/research", json={"company_name": "Apple"})

    assert response.status_code == 503
    assert response.status_code != 500


def test_missing_company_returns_200_not_error() -> None:
    """A company with no matching records is not an API error — it's a
    normal, valid, deterministic report showing matched=False."""
    client = build_client()

    response = client.post("/company/research", json={"company_name": "Nonexistent Corp"})

    assert response.status_code == 200
    assert response.json()["report"]["company_overview"]["matched"] is False
