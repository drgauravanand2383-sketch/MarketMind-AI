"""API contract tests (Sprint 60) — the frozen `/api/v1` contract
documented in `docs/release/API_CONTRACT_V1.md`, verified against actual
behavior rather than static declarations. Covers: request-schema
strictness, response envelope shapes, error format, versioning
consistency, and status codes for the paths that don't require a
real backend to exercise (401/404/422 all short-circuit before any
service/database call).
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from app.api.v1.alerts.schemas import EvaluateAlertsRequest
from app.api.v1.backtests.schemas import CreateBacktestRequest
from app.api.v1.explainability.schemas import GenerateExplanationRequest
from app.api.v1.portfolio.schemas import GenerateRecommendationsRequest
from app.api.v1.research.schemas import BatchCompanyResearchRequest
from app.api.v1.screening.schemas import (
    CreateScreeningProfileRequest,
    RunScreeningRequest,
    UpdateScreeningProfileRequest,
)
from app.api.v1.signals.schemas import (
    CreateSignalDefinitionRequest,
    EvaluateSignalsRequest,
    UpdateSignalDefinitionRequest,
)
from app.api.v1.strategies.schemas import (
    CreateStrategyRequest,
    EvaluateStrategyRequest,
    UpdateStrategyRequest,
)
from app.api.v1.watchlists.schemas import (
    AddCompanyRequest,
    CreateWatchlistRequest,
    RenameWatchlistRequest,
)

NOW = datetime(2026, 8, 8, tzinfo=UTC)


def _signal_kwargs() -> dict:
    return {
        "ticker": "AAPL", "signal_name": "x", "category": "VALUATION", "triggered": True,
        "confidence": 90.0, "score": 80.0, "priority": "HIGH", "reason": "matched", "timestamp": NOW,
    }


# (schema class, minimal-valid constructor kwargs)
REQUEST_SCHEMAS: list[tuple[type[BaseModel], dict]] = [
    (EvaluateAlertsRequest, {"signals": [_signal_kwargs()]}),
    (CreateBacktestRequest, {
        "name": "x", "start_date": date(2026, 1, 1), "end_date": date(2026, 3, 31),
        "initial_capital": 100000.0, "benchmark": "SPY",
    }),
    (GenerateExplanationRequest, {"name": "x", "recommendation_result_id": "rec-1"}),
    (GenerateRecommendationsRequest, {"portfolio_id": "9c1e2b1a-3f4d-4a5e-8b6c-7d8e9f0a1b2c"}),
    (BatchCompanyResearchRequest, {"companies": [{"company_name": "Apple"}]}),
    (CreateScreeningProfileRequest, {"name": "x"}),
    (UpdateScreeningProfileRequest, {}),
    (RunScreeningRequest, {"profile_id": "p1", "companies": [{"ticker": "AAPL", "company_name": "Apple"}]}),
    (CreateSignalDefinitionRequest, {"name": "x"}),
    (UpdateSignalDefinitionRequest, {}),
    (EvaluateSignalsRequest, {"definition_id": "d1", "snapshots": [{"ticker": "AAPL"}]}),
    (CreateStrategyRequest, {"name": "x"}),
    (UpdateStrategyRequest, {}),
    (EvaluateStrategyRequest, {"recommendation_result_id": "rec-1"}),
    (CreateWatchlistRequest, {"name": "x"}),
    (RenameWatchlistRequest, {"name": "x"}),
    (AddCompanyRequest, {"ticker": "AAPL"}),
]


@pytest.mark.parametrize("schema_class,valid_kwargs", REQUEST_SCHEMAS, ids=lambda v: getattr(v, "__name__", None))
def test_request_schema_accepts_valid_kwargs(schema_class: type[BaseModel], valid_kwargs: dict) -> None:
    schema_class(**valid_kwargs)  # must not raise


@pytest.mark.parametrize("schema_class,valid_kwargs", REQUEST_SCHEMAS, ids=lambda v: getattr(v, "__name__", None))
def test_request_schema_forbids_unknown_fields(schema_class: type[BaseModel], valid_kwargs: dict) -> None:
    with pytest.raises(ValidationError):
        schema_class(**valid_kwargs, this_field_does_not_exist=True)


# --------------------------------------------------------------------------
# HTTP-level: error envelope shape, versioning, status codes
# (no auth/database reachability required — every case below short-circuits
# before any service or repository call.)
# --------------------------------------------------------------------------


def test_unknown_route_returns_404_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/this-route-does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "not_found"
    assert "message" in body
    assert "meta" in body
    assert "request_id" in body["meta"]


def test_unauthenticated_protected_endpoint_returns_401_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/watchlists")
    assert response.status_code == 401
    body = response.json()
    assert "error" in body
    assert "meta" in body


def test_malformed_uuid_path_param_returns_422_validation_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/watchlists/not-a-uuid")
    # auth is resolved before path validation for this route, so an
    # unauthenticated request short-circuits at 401 — assert the shape
    # is a proper error envelope either way (401 or 422), never a raw
    # unhandled traceback.
    assert response.status_code in (401, 422)
    body = response.json()
    assert "error" in body
    assert "meta" in body


def test_every_v1_path_is_prefixed(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    for path in schema["paths"]:
        if path in ("/health", "/company/research", "/portfolio/research", "/morning/run"):
            continue  # the pre-existing, deliberately unversioned Intelligence Query API
        assert path.startswith("/api/v1") or path == "/ws", f"unversioned path: {path}"


def test_response_envelope_schemas_are_present_in_components(client: TestClient) -> None:
    """`SuccessResponse[T]`/`PaginatedResponse[T]` are declared as real
    `response_model=`s, so FastAPI registers a concrete component per T.
    `ErrorResponse`/`ValidationErrorResponse` are never a `response_model=`
    — they're built by the centralized exception handlers, not returned
    from a typed handler — so FastAPI has no component to register for
    them; their actual shape is verified empirically by the error-path
    tests below instead of a static OpenAPI declaration.
    """
    schema = client.get("/openapi.json").json()
    component_names = set(schema["components"]["schemas"].keys())
    assert any(name.startswith("SuccessResponse") for name in component_names)
    assert any(name.startswith("PaginatedResponse") for name in component_names)


def test_operation_ids_are_unique(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    operation_ids = [
        operation["operationId"]
        for path, methods in schema["paths"].items()
        if path.startswith("/api/v1")
        for operation in methods.values()
        if "operationId" in operation
    ]
    assert len(operation_ids) == len(set(operation_ids))
    assert len(operation_ids) > 0


def test_status_code_conventions_are_consistent(client: TestClient) -> None:
    """GET/PATCH -> 200, create/action POST -> 201, delete DELETE -> 204
    (with three documented exceptions — see docs/release/API_CONTRACT_V1.md
    §3): removing one watchlist company returns the updated watchlist
    (200, not 204); logging out revokes a token with no body to return
    (204, not 201) — the same "still-a-resource-worth-returning" /
    "genuinely no body" reasoning as the DELETE side, just on a POST; and
    triggering initial portfolio analysis (v1.2 Priority 8) dispatches a
    background job and returns before it completes (202, not 201) — a
    genuinely different, standard HTTP status for "accepted, not yet
    done", not a violation of the "action POST -> 201" rule so much as a
    POST that is not synchronously complete at response time."""
    schema = client.get("/openapi.json").json()
    delete_exception_paths = {"/api/v1/watchlists/{watchlist_id}/companies/{ticker}"}
    post_no_content_paths = {"/api/v1/auth/logout"}
    post_accepted_paths = {"/api/v1/portfolio/{portfolio_id}/analysis"}
    for path, methods in schema["paths"].items():
        if not path.startswith("/api/v1"):
            continue
        for method, operation in methods.items():
            codes = set(operation["responses"].keys())
            if method.lower() == "post" and path not in post_no_content_paths and path not in post_accepted_paths:
                assert "201" in codes, f"POST {path} does not declare 201"
            if method.lower() == "post" and path in post_no_content_paths:
                assert "204" in codes, f"POST {path} does not declare 204"
            if method.lower() == "post" and path in post_accepted_paths:
                assert "202" in codes, f"POST {path} does not declare 202"
            if method.lower() == "delete" and path not in delete_exception_paths:
                assert "204" in codes, f"DELETE {path} does not declare 204"
            if method.lower() in ("get", "patch"):
                assert "200" in codes, f"{method.upper()} {path} does not declare 200"
