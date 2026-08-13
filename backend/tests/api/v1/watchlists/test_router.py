"""End-to-end tests for the Watchlist API (`/api/v1/watchlists`).

Every test exercises the real router through a real `AuthenticationMiddleware`
+ real `AuthorizationService` + real `WatchlistService` (all backed by
in-memory SQLite) — no mocks. Domain exceptions are never caught by the
router, so 404/409/400 mapping is verified end-to-end through the
centralized `handle_domain_error`, not asserted against the service layer
directly.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.exception_handlers import register_exception_handlers
from app.api.v1.watchlists import router as watchlists_router
from app.auth.middleware import AuthenticationMiddleware
from app.auth.policies import PolicyEvaluator
from app.auth.repositories.postgres.repository import PostgresAuthRepository
from app.auth.services.authentication import AuthenticationService
from app.auth.services.authorization import AuthorizationService
from tests.api.v1.watchlists.conftest import make_authenticated_headers


# --------------------------------------------------------------------------
# Authentication / authorization
# --------------------------------------------------------------------------


def test_list_watchlists_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/watchlists")
    assert response.status_code == 401


async def test_list_watchlists_requires_permission(
    client: TestClient, auth_repository: PostgresAuthRepository, auth_service: AuthenticationService
) -> None:
    headers = await make_authenticated_headers(auth_repository, auth_service, permissions=())
    response = client.get("/api/v1/watchlists", headers=headers)
    assert response.status_code == 403


async def test_create_watchlist_requires_create_permission(
    client: TestClient, auth_repository: PostgresAuthRepository, auth_service: AuthenticationService
) -> None:
    headers = await make_authenticated_headers(auth_repository, auth_service, permissions=("watchlist:read",))
    response = client.post("/api/v1/watchlists", json={"name": "X"}, headers=headers)
    assert response.status_code == 403


# --------------------------------------------------------------------------
# CRUD
# --------------------------------------------------------------------------


def test_create_watchlist(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/watchlists", json={"name": "Tech Growth", "description": "High growth"}, headers=auth_headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["data"]["name"] == "Tech Growth"
    assert body["data"]["description"] == "High growth"
    assert body["data"]["items"] == []
    uuid.UUID(body["data"]["id"])
    assert "meta" in body and "request_id" in body["meta"]


def test_create_watchlist_blank_name_is_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post("/api/v1/watchlists", json={"name": ""}, headers=auth_headers)
    assert response.status_code == 422


def test_create_watchlist_rejects_unknown_fields(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post("/api/v1/watchlists", json={"name": "X", "bogus": "y"}, headers=auth_headers)
    assert response.status_code == 422


def test_list_watchlists(client: TestClient, auth_headers: dict[str, str]) -> None:
    client.post("/api/v1/watchlists", json={"name": "A"}, headers=auth_headers)
    client.post("/api/v1/watchlists", json={"name": "B"}, headers=auth_headers)

    response = client.get("/api/v1/watchlists", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert len(body["data"]) == 2


def test_get_watchlist(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post("/api/v1/watchlists", json={"name": "A"}, headers=auth_headers).json()["data"]
    response = client.get(f"/api/v1/watchlists/{created['id']}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["id"] == created["id"]


def test_get_watchlist_invalid_uuid_returns_422(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/api/v1/watchlists/not-a-uuid", headers=auth_headers)
    assert response.status_code == 422


def test_get_watchlist_unknown_uuid_returns_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get(f"/api/v1/watchlists/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_rename_watchlist(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post("/api/v1/watchlists", json={"name": "A"}, headers=auth_headers).json()["data"]
    response = client.patch(
        f"/api/v1/watchlists/{created['id']}", json={"name": "A Renamed"}, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "A Renamed"


def test_rename_unknown_watchlist_returns_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.patch(
        f"/api/v1/watchlists/{uuid.uuid4()}", json={"name": "X"}, headers=auth_headers
    )
    assert response.status_code == 404


def test_delete_watchlist(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post("/api/v1/watchlists", json={"name": "A"}, headers=auth_headers).json()["data"]
    response = client.delete(f"/api/v1/watchlists/{created['id']}", headers=auth_headers)
    assert response.status_code == 204

    follow_up = client.get(f"/api/v1/watchlists/{created['id']}", headers=auth_headers)
    assert follow_up.status_code == 404


# --------------------------------------------------------------------------
# Companies
# --------------------------------------------------------------------------


def test_add_company(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post("/api/v1/watchlists", json={"name": "A"}, headers=auth_headers).json()["data"]
    response = client.post(
        f"/api/v1/watchlists/{created['id']}/companies",
        json={"ticker": "aapl", "company_name": "Apple", "sector": "Technology"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["ticker"] == "AAPL"
    assert items[0]["added_at"] is not None


def test_add_company_rejects_added_at_from_client(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post("/api/v1/watchlists", json={"name": "A"}, headers=auth_headers).json()["data"]
    response = client.post(
        f"/api/v1/watchlists/{created['id']}/companies",
        json={"ticker": "AAPL", "added_at": "2020-01-01T00:00:00Z"},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_add_duplicate_ticker_returns_409(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post("/api/v1/watchlists", json={"name": "A"}, headers=auth_headers).json()["data"]
    client.post(
        f"/api/v1/watchlists/{created['id']}/companies", json={"ticker": "AAPL"}, headers=auth_headers
    )
    response = client.post(
        f"/api/v1/watchlists/{created['id']}/companies", json={"ticker": "AAPL"}, headers=auth_headers
    )
    assert response.status_code == 409


def test_remove_company(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post("/api/v1/watchlists", json={"name": "A"}, headers=auth_headers).json()["data"]
    client.post(
        f"/api/v1/watchlists/{created['id']}/companies", json={"ticker": "AAPL"}, headers=auth_headers
    )
    response = client.delete(f"/api/v1/watchlists/{created['id']}/companies/AAPL", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["items"] == []


def test_remove_unknown_ticker_returns_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post("/api/v1/watchlists", json={"name": "A"}, headers=auth_headers).json()["data"]
    response = client.delete(f"/api/v1/watchlists/{created['id']}/companies/MSFT", headers=auth_headers)
    assert response.status_code == 404


def test_remove_company_with_invalid_ticker_format_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    created = client.post("/api/v1/watchlists", json={"name": "A"}, headers=auth_headers).json()["data"]
    response = client.delete(
        f"/api/v1/watchlists/{created['id']}/companies/TOO-LONG-TICKER", headers=auth_headers
    )
    assert response.status_code == 422


def test_update_company_notes(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post("/api/v1/watchlists", json={"name": "A"}, headers=auth_headers).json()["data"]
    client.post(
        f"/api/v1/watchlists/{created['id']}/companies", json={"ticker": "AAPL"}, headers=auth_headers
    )

    response = client.patch(
        f"/api/v1/watchlists/{created['id']}/companies/AAPL/notes",
        json={"notes": "Watching for Q3 earnings."},
        headers=auth_headers,
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["notes"] == "Watching for Q3 earnings."


def test_update_company_notes_can_clear_existing_notes(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post("/api/v1/watchlists", json={"name": "A"}, headers=auth_headers).json()["data"]
    client.post(
        f"/api/v1/watchlists/{created['id']}/companies",
        json={"ticker": "AAPL", "notes": "Initial note"},
        headers=auth_headers,
    )

    response = client.patch(
        f"/api/v1/watchlists/{created['id']}/companies/AAPL/notes", json={}, headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["notes"] == ""


def test_update_notes_for_unknown_ticker_returns_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post("/api/v1/watchlists", json={"name": "A"}, headers=auth_headers).json()["data"]

    response = client.patch(
        f"/api/v1/watchlists/{created['id']}/companies/MSFT/notes",
        json={"notes": "x"},
        headers=auth_headers,
    )

    assert response.status_code == 404


def test_update_notes_for_unknown_watchlist_returns_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.patch(
        f"/api/v1/watchlists/{uuid.uuid4()}/companies/AAPL/notes", json={"notes": "x"}, headers=auth_headers
    )

    assert response.status_code == 404


def test_update_notes_rejects_unknown_fields(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post("/api/v1/watchlists", json={"name": "A"}, headers=auth_headers).json()["data"]
    client.post(
        f"/api/v1/watchlists/{created['id']}/companies", json={"ticker": "AAPL"}, headers=auth_headers
    )

    response = client.patch(
        f"/api/v1/watchlists/{created['id']}/companies/AAPL/notes",
        json={"notes": "x", "bogus": "y"},
        headers=auth_headers,
    )

    assert response.status_code == 422


async def test_update_notes_requires_update_permission(
    client: TestClient, auth_repository: PostgresAuthRepository, auth_service: AuthenticationService
) -> None:
    owner_headers = await make_authenticated_headers(auth_repository, auth_service, username="owner")
    created = client.post("/api/v1/watchlists", json={"name": "A"}, headers=owner_headers).json()["data"]
    client.post(
        f"/api/v1/watchlists/{created['id']}/companies", json={"ticker": "AAPL"}, headers=owner_headers
    )
    read_only_headers = await make_authenticated_headers(
        auth_repository, auth_service, permissions=("watchlist:read",), username="reader"
    )

    response = client.patch(
        f"/api/v1/watchlists/{created['id']}/companies/AAPL/notes", json={"notes": "x"}, headers=read_only_headers
    )

    assert response.status_code == 403


def test_get_watchlist_snapshot(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post("/api/v1/watchlists", json={"name": "A"}, headers=auth_headers).json()["data"]
    client.post(
        f"/api/v1/watchlists/{created['id']}/companies", json={"ticker": "AAPL"}, headers=auth_headers
    )
    response = client.get(f"/api/v1/watchlists/{created['id']}/snapshot", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["watchlist_id"] == created["id"]
    assert response.json()["data"]["total_companies"] == 1


# --------------------------------------------------------------------------
# Filtering
# --------------------------------------------------------------------------


def test_filter_by_sector(client: TestClient, auth_headers: dict[str, str]) -> None:
    tech = client.post("/api/v1/watchlists", json={"name": "Tech"}, headers=auth_headers).json()["data"]
    client.post(
        f"/api/v1/watchlists/{tech['id']}/companies",
        json={"ticker": "AAPL", "sector": "Technology"},
        headers=auth_headers,
    )
    client.post("/api/v1/watchlists", json={"name": "Empty"}, headers=auth_headers)

    response = client.get("/api/v1/watchlists?sector=Technology", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 1

    response = client.get("/api/v1/watchlists?sector=Healthcare", headers=auth_headers)
    assert response.json()["total"] == 0


def test_filter_by_name(client: TestClient, auth_headers: dict[str, str]) -> None:
    client.post("/api/v1/watchlists", json={"name": "Tech Growth"}, headers=auth_headers)
    client.post("/api/v1/watchlists", json={"name": "Healthcare Value"}, headers=auth_headers)

    response = client.get("/api/v1/watchlists?name=tech", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["data"][0]["name"] == "Tech Growth"

    response = client.get("/api/v1/watchlists?name=nonexistent", headers=auth_headers)
    assert response.json()["total"] == 0


def test_filter_by_ticker(client: TestClient, auth_headers: dict[str, str]) -> None:
    watchlist = client.post("/api/v1/watchlists", json={"name": "Tech"}, headers=auth_headers).json()["data"]
    client.post(
        f"/api/v1/watchlists/{watchlist['id']}/companies", json={"ticker": "AAPL"}, headers=auth_headers
    )

    response = client.get("/api/v1/watchlists?ticker=AAPL", headers=auth_headers)
    assert response.json()["total"] == 1

    response = client.get("/api/v1/watchlists?ticker=MSFT", headers=auth_headers)
    assert response.json()["total"] == 0


def test_filter_created_after_greater_than_created_before_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get(
        "/api/v1/watchlists?created_after=2026-06-01T00:00:00Z&created_before=2026-01-01T00:00:00Z",
        headers=auth_headers,
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------
# Pagination / sorting validation
# --------------------------------------------------------------------------


def test_page_size_exceeds_maximum_returns_422(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/api/v1/watchlists?page_size=101", headers=auth_headers)
    assert response.status_code == 422


def test_page_below_one_returns_422(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/api/v1/watchlists?page=0", headers=auth_headers)
    assert response.status_code == 422


def test_unknown_sort_field_returns_422(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/api/v1/watchlists?sort=bogus_field", headers=auth_headers)
    assert response.status_code == 422


def test_sort_by_name_descending(client: TestClient, auth_headers: dict[str, str]) -> None:
    client.post("/api/v1/watchlists", json={"name": "Alpha"}, headers=auth_headers)
    client.post("/api/v1/watchlists", json={"name": "Beta"}, headers=auth_headers)

    response = client.get("/api/v1/watchlists?sort=name&direction=desc", headers=auth_headers)
    assert response.status_code == 200
    names = [item["name"] for item in response.json()["data"]]
    assert names == ["Beta", "Alpha"]


# --------------------------------------------------------------------------
# Dependency injection / 503
# --------------------------------------------------------------------------


async def test_returns_503_when_watchlist_service_not_configured(
    auth_repository: PostgresAuthRepository,
    auth_service: AuthenticationService,
    authorization_service: AuthorizationService,
) -> None:
    headers = await make_authenticated_headers(auth_repository, auth_service)

    app = FastAPI()
    app.state.authentication_service = auth_service
    app.state.authorization_service = authorization_service
    app.state.policy_evaluator = PolicyEvaluator()
    # deliberately no app.state.watchlist_service
    app.add_middleware(AuthenticationMiddleware)
    app.include_router(watchlists_router, prefix="/api/v1")
    register_exception_handlers(app)

    with TestClient(app) as bare_client:
        response = bare_client.get("/api/v1/watchlists", headers=headers)
    assert response.status_code == 503


# --------------------------------------------------------------------------
# OpenAPI
# --------------------------------------------------------------------------


def test_openapi_documents_watchlists_with_tags_and_schemas(app: FastAPI) -> None:
    # No endpoint in this codebase populates OpenAPI's `security` array —
    # `require_policy` enforces auth via a plain `Depends`, not FastAPI's
    # `Security()`/`HTTPBearer` scheme integration (a pre-existing Sprint 56
    # auth-framework choice, unrelated to this router) — so that omission
    # is not asserted here; auth enforcement itself is covered by the 401
    # and 403 tests above.
    schema = app.openapi()
    list_op = schema["paths"]["/api/v1/watchlists"]["get"]
    assert list_op["tags"] == ["Watchlists"]

    create_op = schema["paths"]["/api/v1/watchlists"]["post"]
    assert "CreateWatchlistRequest" in schema["components"]["schemas"]
    assert create_op["responses"]["201"]
