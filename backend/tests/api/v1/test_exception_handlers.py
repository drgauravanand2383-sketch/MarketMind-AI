"""Tests for centralized exception handling: `RequestValidationError`,
`HTTPException` (unknown routes, unsupported methods, and the 503s raised
by `app.api.v1.dependencies.state`), domain exception base classes, and
the generic unhandled-exception fallback.

None of Sprint 55's own six endpoints accept a request body or a typed
query/path parameter (every one is a bare `GET` with no input) — the
validation-error and domain-error tests below mount a small,
purpose-built router of their own (registered against the exact same
`register_exception_handlers`) so the *real* handler pipeline is
exercised end-to-end, not the handler functions called directly in
isolation.
"""

from __future__ import annotations

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.api.v1.exception_handlers import register_exception_handlers
from app.risk.exceptions import DuplicateRiskRequestNameError, RiskAnalyticsError, RiskAssessmentNotFoundError
from app.watchlist.exceptions import WatchlistServiceError


@pytest.fixture
def probe_app() -> FastAPI:
    router = APIRouter()

    @router.get("/echo")
    async def echo(count: int) -> dict:
        return {"count": count}

    @router.get("/raise-not-found")
    async def raise_not_found() -> None:
        raise RiskAssessmentNotFoundError("req-1")

    @router.get("/raise-duplicate")
    async def raise_duplicate() -> None:
        raise DuplicateRiskRequestNameError("My Request")

    @router.get("/raise-domain-error")
    async def raise_domain_error() -> None:
        raise RiskAnalyticsError("something went wrong")

    @router.get("/raise-other-domain-error")
    async def raise_other_domain_error() -> None:
        raise WatchlistServiceError("watchlist trouble")

    @router.get("/raise-unhandled")
    async def raise_unhandled() -> None:
        raise ValueError("boom")

    app = FastAPI()
    app.include_router(router)
    register_exception_handlers(app)
    return app


@pytest.fixture
def probe_client(probe_app: FastAPI) -> TestClient:
    return TestClient(probe_app, raise_server_exceptions=False)


# --- validation errors -----------------------------------------------------------


def test_validation_error_returns_422(probe_client: TestClient) -> None:
    response = probe_client.get("/echo", params={"count": "not-an-int"})

    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "validation_error"
    assert len(body["details"]) >= 1
    assert body["details"][0]["location"]
    assert body["details"][0]["type"]


def test_validation_error_missing_required_param(probe_client: TestClient) -> None:
    response = probe_client.get("/echo")

    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"


def test_valid_request_does_not_trigger_validation_handler(probe_client: TestClient) -> None:
    response = probe_client.get("/echo", params={"count": 5})

    assert response.status_code == 200
    assert response.json() == {"count": 5}


# --- unknown routes / unsupported methods -----------------------------------------------------------


def test_unknown_route_returns_404_error_envelope(probe_client: TestClient) -> None:
    response = probe_client.get("/this-route-does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "not_found"
    assert "meta" in body


def test_unsupported_method_returns_405_error_envelope(probe_client: TestClient) -> None:
    response = probe_client.post("/echo", params={"count": 1})

    assert response.status_code == 405
    assert response.json()["error"] == "method_not_allowed"


# --- domain exceptions -----------------------------------------------------------


def test_not_found_domain_exception_maps_to_404(probe_client: TestClient) -> None:
    response = probe_client.get("/raise-not-found")

    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "not_found"
    assert "req-1" in body["message"]


def test_duplicate_domain_exception_maps_to_409(probe_client: TestClient) -> None:
    response = probe_client.get("/raise-duplicate")

    assert response.status_code == 409
    body = response.json()
    assert body["error"] == "conflict"


def test_generic_domain_exception_maps_to_400(probe_client: TestClient) -> None:
    response = probe_client.get("/raise-domain-error")

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "domain_error"
    assert body["message"] == "something went wrong"


def test_a_different_package_domain_exception_is_also_handled(probe_client: TestClient) -> None:
    """Confirms the handler is registered per-package, not just for Risk."""
    response = probe_client.get("/raise-other-domain-error")

    assert response.status_code == 400
    assert response.json()["error"] == "domain_error"


# --- unhandled exceptions -----------------------------------------------------------


def test_unhandled_exception_returns_500_without_leaking_internals(probe_client: TestClient) -> None:
    response = probe_client.get("/raise-unhandled")

    assert response.status_code == 500
    body = response.json()
    assert body["error"] == "internal_error"
    assert "boom" not in body["message"]
    assert "ValueError" not in body["message"]


def test_every_error_response_includes_metadata(probe_client: TestClient) -> None:
    for path in ("/raise-not-found", "/raise-domain-error", "/raise-unhandled", "/nonexistent"):
        body = probe_client.get(path).json()
        assert "meta" in body
        assert body["meta"]["request_id"]
        assert body["meta"]["api_version"] == "v1"
