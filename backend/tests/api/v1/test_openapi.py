"""Tests for OpenAPI generation and API startup."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_app_starts_and_serves_requests(client: TestClient) -> None:
    response = client.get("/api/v1/version")
    assert response.status_code == 200


def test_openapi_schema_generates_without_error(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "MarketMind AI"


def test_openapi_includes_every_v1_path(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = set(schema["paths"].keys())

    for path in (
        "/api/v1/health", "/api/v1/ready", "/api/v1/version",
        "/api/v1/configuration", "/api/v1/capabilities", "/api/v1/services",
    ):
        assert path in paths


def test_openapi_preserves_existing_intelligence_routes(client: TestClient) -> None:
    """`/api/v1` is additive — the pre-existing, unversioned Intelligence
    Query API must still be present in the schema."""
    schema = client.get("/openapi.json").json()
    paths = set(schema["paths"].keys())

    assert "/health" in paths
    assert "/company/research" in paths
    assert "/portfolio/research" in paths
    assert "/morning/run" in paths


def test_openapi_declares_the_health_and_system_tags() -> None:
    from app.main import OPENAPI_TAGS_METADATA

    tag_names = {tag["name"] for tag in OPENAPI_TAGS_METADATA}
    assert tag_names == {
        "Auth",
        "Health",
        "System",
        "Watchlists",
        "Portfolio",
        "Company Research",
        "Screening",
        "Signal Detection",
        "Alerts",
        "Strategy Evaluation",
        "Backtesting",
        "Explainability",
        "Real-Time Events",
    }
    assert all(tag["description"] for tag in OPENAPI_TAGS_METADATA)


def test_openapi_declares_a_bearer_security_scheme(client: TestClient) -> None:
    """Sprint 58: Swagger UI's Authorize button is driven by this scheme
    being present in `components.securitySchemes`."""
    schema = client.get("/openapi.json").json()
    schemes = schema["components"]["securitySchemes"]
    assert "BearerAuth" in schemes
    assert schemes["BearerAuth"]["type"] == "http"
    assert schemes["BearerAuth"]["scheme"] == "bearer"


def test_every_require_policy_protected_endpoint_advertises_bearer_auth(client: TestClient) -> None:
    """Every `/api/v1` endpoint other than the unauthenticated system/health
    probes must declare `security: [{"BearerAuth": []}]` in its OpenAPI
    operation — this is what makes Swagger's Authorize button apply to it."""
    unauthenticated_paths = {
        "/api/v1/health",
        "/api/v1/ready",
        "/api/v1/version",
        "/api/v1/configuration",
        "/api/v1/capabilities",
        "/api/v1/services",
        # Neither endpoint can require a token: login issues the first
        # one, and refresh exchanges a refresh token (not a Bearer
        # access token) for a new pair.
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
    }
    schema = client.get("/openapi.json").json()
    for path, methods in schema["paths"].items():
        if not path.startswith("/api/v1") or path in unauthenticated_paths:
            continue
        for method, operation in methods.items():
            assert operation.get("security") == [{"BearerAuth": []}], f"{method.upper()} {path} is missing Bearer security metadata"


def test_every_v1_endpoint_is_tagged(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    for path, methods in schema["paths"].items():
        if not path.startswith("/api/v1"):
            continue
        for operation in methods.values():
            assert operation.get("tags"), f"{path} has no OpenAPI tag"


def test_every_v1_endpoint_declares_a_response_model(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    for path, methods in schema["paths"].items():
        if not path.startswith("/api/v1"):
            continue
        for method, operation in methods.items():
            if method.lower() != "get":
                continue
            assert "200" in operation["responses"]
            assert "content" in operation["responses"]["200"]


def test_every_v1_endpoint_has_a_summary_and_description(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    for path, methods in schema["paths"].items():
        if not path.startswith("/api/v1"):
            continue
        for operation in methods.values():
            assert operation.get("summary")
            assert operation.get("description")
