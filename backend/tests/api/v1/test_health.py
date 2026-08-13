"""Tests for `GET /api/v1/health` and `GET /api/v1/ready`.

`client` (see `conftest.py`) overrides `get_repositories_map` with fast,
always-reachable fakes, so the "healthy" tests below are deterministic
and fast. `test_ready_returns_503_when_any_repository_is_unhealthy` uses
its own small, isolated probe app (real `HealthCheckService`, fake
*unhealthy* repositories) to exercise the not-ready path deterministically
too — without depending on this sandbox's real (and slow to fail)
PostgreSQL reachability.
"""

from __future__ import annotations

from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from app.api.v1.dependencies.state import get_health_check_service, get_repositories_map, get_services_map
from app.api.v1.router import router as v1_router
from app.operations.health.models import HealthState
from app.operations.health.service import HealthCheckService


def test_health_returns_a_success_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert "data" in body
    assert "meta" in body


def test_health_data_matches_application_health_shape(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    data = response.json()["data"]
    assert data["state"] in {s.value for s in HealthState}
    assert isinstance(data["repositories"], list)
    assert isinstance(data["services"], list)
    assert "checked_at" in data
    assert "summary" in data


def test_health_reports_healthy_when_every_repository_and_service_is_up(client: TestClient) -> None:
    data = client.get("/api/v1/health").json()["data"]

    assert data["state"] == HealthState.HEALTHY.value
    assert all(r["state"] == HealthState.HEALTHY.value for r in data["repositories"])
    assert all(s["state"] == HealthState.HEALTHY.value for s in data["services"])


def test_health_includes_every_wired_repository_and_service(client: TestClient) -> None:
    data = client.get("/api/v1/health").json()["data"]

    repository_names = {r["name"] for r in data["repositories"]}
    service_names = {s["name"] for s in data["services"]}

    assert "risk_repository" in repository_names
    assert "backtesting_repository" in repository_names
    assert "explainability_repository" in repository_names
    assert "risk_service" in service_names
    assert "explainability_service" in service_names


def test_health_response_has_a_request_id_and_timestamp(client: TestClient) -> None:
    meta = client.get("/api/v1/health").json()["meta"]

    assert meta["request_id"]
    assert meta["timestamp"]
    assert meta["api_version"] == "v1"


def test_ready_returns_ready_field_in_body(client: TestClient) -> None:
    response = client.get("/api/v1/ready")

    body = response.json()["data"]
    assert "ready" in body
    assert isinstance(body["ready"], bool)


def test_ready_returns_200_when_every_repository_and_service_is_up(client: TestClient) -> None:
    response = client.get("/api/v1/ready")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["data"]["ready"] is True
    assert response.json()["data"]["blocking_issues"] == []


def test_ready_includes_application_health(client: TestClient) -> None:
    body = client.get("/api/v1/ready").json()["data"]

    assert "application_health" in body
    assert body["application_health"]["state"] in {s.value for s in HealthState}


def test_health_reuses_health_check_service_never_recomputes(client: TestClient) -> None:
    """Two consecutive calls must independently reflect the live
    repository state (each call really invokes `health_check()` again),
    not a cached/stale snapshot."""
    first = client.get("/api/v1/health").json()["data"]["checked_at"]
    second = client.get("/api/v1/health").json()["data"]["checked_at"]

    assert first != second  # a fresh timestamp each call proves no caching


def test_health_missing_health_check_service_returns_503(bare_client: TestClient) -> None:
    response = bare_client.get("/api/v1/health")

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json()["error"] == "service_unavailable"


def test_ready_missing_health_check_service_returns_503(bare_client: TestClient) -> None:
    response = bare_client.get("/api/v1/ready")

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


# --- Not-ready path (isolated probe app, deterministic) -----------------------------------------------------------


class _FakeUnhealthyRepository:
    async def health_check(self) -> bool:
        return False


def test_ready_returns_503_when_any_repository_is_unhealthy() -> None:
    app = FastAPI()
    app.include_router(v1_router, prefix="/api/v1")
    app.dependency_overrides[get_health_check_service] = lambda: HealthCheckService()
    app.dependency_overrides[get_repositories_map] = lambda: {"risk_repository": _FakeUnhealthyRepository()}
    app.dependency_overrides[get_services_map] = lambda: {}

    with TestClient(app) as probe_client:
        response = probe_client.get("/api/v1/ready")

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    body = response.json()["data"]
    assert body["ready"] is False
    assert "risk_repository: unreachable" in body["blocking_issues"]


def test_health_reports_unhealthy_when_any_repository_is_down() -> None:
    app = FastAPI()
    app.include_router(v1_router, prefix="/api/v1")
    app.dependency_overrides[get_health_check_service] = lambda: HealthCheckService()
    app.dependency_overrides[get_repositories_map] = lambda: {"risk_repository": _FakeUnhealthyRepository()}
    app.dependency_overrides[get_services_map] = lambda: {}

    with TestClient(app) as probe_client:
        response = probe_client.get("/api/v1/health")

    assert response.status_code == status.HTTP_200_OK  # /health always 200; state reflects the problem in the body
    assert response.json()["data"]["state"] == HealthState.UNHEALTHY.value
