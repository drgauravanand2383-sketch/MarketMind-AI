"""End-to-end tests for the Portfolio API (`/api/v1/portfolio`).

By product decision, "portfolio" has no domain entity of its own — a
`portfolio_id` is a `watchlist_id`. Watchlists/recommendation
requests/risk requests are seeded directly through their real services
(no HTTP round-trip needed for setup — those services aren't the thing
under test here), then the portfolio endpoints are exercised through the
real router, real auth middleware, and real authorization.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.ws.connection_manager.manager import ConnectionManager
from app.api.ws.event_models.event_type import EventType
from app.api.ws.event_models.events import EventEnvelope
from app.api.ws.subscriptions.models import Subscription
from app.auth.models.authentication import AuthenticatedPrincipal
from app.auth.repositories.postgres.repository import PostgresAuthRepository
from app.auth.services.authentication import AuthenticationService
from app.recommendations.engine import PortfolioRecommendationService
from app.recommendations.models import CandidateEvidence
from app.risk.engine import RiskAnalyticsService
from app.watchlist.models import WatchlistItem
from app.watchlist.service import WatchlistService
from tests.api.v1.portfolio.conftest import make_authenticated_headers
from tests.api.ws.fakes import FakeWebSocket


async def make_watchlist(watchlist_service: WatchlistService, name: str = "Tech Growth") -> str:
    watchlist = await watchlist_service.create_watchlist(name)
    watchlist = await watchlist_service.add_company(
        watchlist.id,
        WatchlistItem(
            ticker="AAPL", company_name="Apple", sector="Technology", added_at=datetime.now(timezone.utc)
        ),
    )
    return watchlist.id


# --------------------------------------------------------------------------
# Authentication / authorization
# --------------------------------------------------------------------------


def test_list_portfolios_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/portfolio")
    assert response.status_code == 401


async def test_summary_requires_permission(
    client: TestClient, auth_repository: PostgresAuthRepository, auth_service: AuthenticationService
) -> None:
    headers = await make_authenticated_headers(auth_repository, auth_service, permissions=())
    response = client.get(f"/api/v1/portfolio/summary?portfolio_id={uuid.uuid4()}", headers=headers)
    assert response.status_code == 403


async def test_create_recommendations_requires_recommend_permission(
    client: TestClient, auth_repository: PostgresAuthRepository, auth_service: AuthenticationService
) -> None:
    headers = await make_authenticated_headers(auth_repository, auth_service, permissions=("portfolio:read",))
    response = client.post(
        "/api/v1/portfolio/recommendations",
        json={"portfolio_id": str(uuid.uuid4()), "evidence": []},
        headers=headers,
    )
    assert response.status_code == 403


# --------------------------------------------------------------------------
# List / get (portfolio == watchlist)
# --------------------------------------------------------------------------


async def test_list_portfolios(
    client: TestClient, auth_headers: dict[str, str], watchlist_service: WatchlistService
) -> None:
    await make_watchlist(watchlist_service, "A")
    await make_watchlist(watchlist_service, "B")

    response = client.get("/api/v1/portfolio", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 2


async def test_get_portfolio(
    client: TestClient, auth_headers: dict[str, str], watchlist_service: WatchlistService
) -> None:
    portfolio_id = await make_watchlist(watchlist_service)
    response = client.get(f"/api/v1/portfolio/{portfolio_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["id"] == portfolio_id


def test_get_portfolio_invalid_uuid_returns_422(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/api/v1/portfolio/not-a-uuid", headers=auth_headers)
    assert response.status_code == 422


def test_get_portfolio_unknown_uuid_returns_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get(f"/api/v1/portfolio/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


def test_unknown_sort_field_returns_422(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/api/v1/portfolio?sort=bogus_field", headers=auth_headers)
    assert response.status_code == 422


# --------------------------------------------------------------------------
# Summary — literal route must not be shadowed by /{portfolio_id}
# --------------------------------------------------------------------------


async def test_portfolio_summary(
    client: TestClient, auth_headers: dict[str, str], watchlist_service: WatchlistService
) -> None:
    portfolio_id = await make_watchlist(watchlist_service)
    response = client.get(f"/api/v1/portfolio/summary?portfolio_id={portfolio_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["total_companies"] == 1
    assert response.json()["data"]["watchlist_id"] == portfolio_id


def test_portfolio_summary_missing_portfolio_id_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get("/api/v1/portfolio/summary", headers=auth_headers)
    assert response.status_code == 422


def test_portfolio_summary_unknown_portfolio_returns_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get(f"/api/v1/portfolio/summary?portfolio_id={uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


# --------------------------------------------------------------------------
# Intelligence (stub agent)
# --------------------------------------------------------------------------


async def test_portfolio_intelligence(
    client: TestClient, auth_headers: dict[str, str], watchlist_service: WatchlistService
) -> None:
    portfolio_id = await make_watchlist(watchlist_service)
    response = client.get(f"/api/v1/portfolio/intelligence?portfolio_id={portfolio_id}", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["portfolio_overview"]["holding_count"] == 1
    assert body["request"]["companies"][0]["ticker"] == "AAPL"


async def test_portfolio_intelligence_attaches_market_snapshot(
    client: TestClient, auth_headers: dict[str, str], watchlist_service: WatchlistService
) -> None:
    """Milestone 14 §10/§34: the agent itself never fetches market data —
    the router attaches it via PortfolioMarketSnapshotService afterward.
    The test fixture has no entity resolver configured, so AAPL correctly
    comes back ENTITY_NOT_MAPPED rather than a fabricated price."""
    portfolio_id = await make_watchlist(watchlist_service)
    response = client.get(f"/api/v1/portfolio/intelligence?portfolio_id={portfolio_id}", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["market_snapshot"] is not None
    assert body["market_snapshot"]["portfolio_id"] == str(portfolio_id)
    assert body["market_snapshot"]["entity_not_mapped_count"] == 1
    assert body["market_snapshot"]["valuation_status"] == "VALUATION_UNAVAILABLE"


async def test_portfolio_intelligence_publishes_portfolio_intelligence_updated_event(
    client: TestClient,
    auth_headers: dict[str, str],
    watchlist_service: WatchlistService,
    connection_manager: ConnectionManager,
) -> None:
    """Milestone 14 §11: GET /portfolio/intelligence is a real trigger
    point — a subscribed WebSocket client actually receives the event."""
    ws = FakeWebSocket()
    principal = AuthenticatedPrincipal(user_id="u1", username="u1", roles=(), permissions=(), token_id="t1")
    connection_id = await connection_manager.connect(ws, principal)
    connection_manager.subscribe(
        connection_id, Subscription(event_types=frozenset({EventType.PORTFOLIO_INTELLIGENCE_UPDATED}))
    )

    portfolio_id = await make_watchlist(watchlist_service)
    response = client.get(f"/api/v1/portfolio/intelligence?portfolio_id={portfolio_id}", headers=auth_headers)

    assert response.status_code == 200
    assert len(ws.sent) == 1
    envelope = EventEnvelope.model_validate_json(ws.sent[0])
    assert envelope.event.event_type == EventType.PORTFOLIO_INTELLIGENCE_UPDATED


def test_portfolio_intelligence_unknown_portfolio_returns_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get(
        f"/api/v1/portfolio/intelligence?portfolio_id={uuid.uuid4()}", headers=auth_headers
    )
    assert response.status_code == 404


# --------------------------------------------------------------------------
# Risk — read-only lookup of the most recently stored assessment
# --------------------------------------------------------------------------


async def test_portfolio_risk_no_data_returns_404(
    client: TestClient, auth_headers: dict[str, str], watchlist_service: WatchlistService
) -> None:
    portfolio_id = await make_watchlist(watchlist_service)
    response = client.get(f"/api/v1/portfolio/risk?portfolio_id={portfolio_id}", headers=auth_headers)
    assert response.status_code == 404


async def test_portfolio_risk_returns_most_recent_assessment(
    client: TestClient,
    auth_headers: dict[str, str],
    watchlist_service: WatchlistService,
    recommendation_service: PortfolioRecommendationService,
    risk_service: RiskAnalyticsService,
) -> None:
    portfolio_id = await make_watchlist(watchlist_service)

    rec_request_1 = await recommendation_service.create_request("rec-1", watchlist_ids=(portfolio_id,))
    rec_result_1 = await recommendation_service.generate_recommendations(
        rec_request_1, [CandidateEvidence(ticker="AAPL")]
    )
    risk_request_1 = await risk_service.create_request(
        "risk-1", portfolio_id=portfolio_id, recommendation_result_id=rec_result_1.request_id
    )
    await risk_service.assess_portfolio(risk_request_1, rec_result_1)

    rec_request_2 = await recommendation_service.create_request("rec-2", watchlist_ids=(portfolio_id,))
    rec_result_2 = await recommendation_service.generate_recommendations(
        rec_request_2, [CandidateEvidence(ticker="AAPL"), CandidateEvidence(ticker="MSFT")]
    )
    risk_request_2 = await risk_service.create_request(
        "risk-2", portfolio_id=portfolio_id, recommendation_result_id=rec_result_2.request_id
    )
    latest_assessment = await risk_service.assess_portfolio(risk_request_2, rec_result_2)

    response = client.get(f"/api/v1/portfolio/risk?portfolio_id={portfolio_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["request_id"] == latest_assessment.request_id


# --------------------------------------------------------------------------
# Recommendations — read (most recent) and generate (create)
# --------------------------------------------------------------------------


async def test_portfolio_recommendations_get_no_data_returns_404(
    client: TestClient, auth_headers: dict[str, str], watchlist_service: WatchlistService
) -> None:
    portfolio_id = await make_watchlist(watchlist_service)
    response = client.get(
        f"/api/v1/portfolio/recommendations?portfolio_id={portfolio_id}", headers=auth_headers
    )
    assert response.status_code == 404


async def test_portfolio_recommendations_get_returns_most_recent_result(
    client: TestClient,
    auth_headers: dict[str, str],
    watchlist_service: WatchlistService,
    recommendation_service: PortfolioRecommendationService,
) -> None:
    portfolio_id = await make_watchlist(watchlist_service)

    request_1 = await recommendation_service.create_request("rec-1", watchlist_ids=(portfolio_id,))
    await recommendation_service.generate_recommendations(request_1, [CandidateEvidence(ticker="AAPL")])

    request_2 = await recommendation_service.create_request("rec-2", watchlist_ids=(portfolio_id,))
    latest_result = await recommendation_service.generate_recommendations(
        request_2, [CandidateEvidence(ticker="AAPL"), CandidateEvidence(ticker="MSFT")]
    )

    response = client.get(
        f"/api/v1/portfolio/recommendations?portfolio_id={portfolio_id}", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["data"]["request_id"] == latest_result.request_id
    assert response.json()["data"]["total_candidates"] == 2


async def test_create_portfolio_recommendations(
    client: TestClient, auth_headers: dict[str, str], watchlist_service: WatchlistService
) -> None:
    portfolio_id = await make_watchlist(watchlist_service)

    response = client.post(
        "/api/v1/portfolio/recommendations",
        json={
            "portfolio_id": portfolio_id,
            "evidence": [{"ticker": "AAPL", "sector": "Technology"}],
            "max_recommendations": 5,
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    body = response.json()["data"]
    assert body["total_candidates"] == 1
    assert body["recommendations"][0]["ticker"] == "AAPL"


def test_create_portfolio_recommendations_rejects_unknown_fields(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/portfolio/recommendations",
        json={"portfolio_id": str(uuid.uuid4()), "evidence": [], "bogus": True},
        headers=auth_headers,
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------
# Initial analysis (v1.2 Priority 8)
# --------------------------------------------------------------------------


async def test_analysis_status_unavailable_for_empty_watchlist(
    client: TestClient, auth_headers: dict[str, str], watchlist_service: WatchlistService
) -> None:
    watchlist = await watchlist_service.create_watchlist("Empty")
    response = client.get(f"/api/v1/portfolio/{watchlist.id}/analysis-status", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "UNAVAILABLE"


def test_analysis_status_unknown_portfolio_returns_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get(f"/api/v1/portfolio/{uuid.uuid4()}/analysis-status", headers=auth_headers)
    assert response.status_code == 404


async def test_analysis_status_requires_read_permission(
    client: TestClient, auth_repository: PostgresAuthRepository, auth_service: AuthenticationService
) -> None:
    headers = await make_authenticated_headers(auth_repository, auth_service, permissions=())
    response = client.get(f"/api/v1/portfolio/{uuid.uuid4()}/analysis-status", headers=headers)
    assert response.status_code == 403


async def test_trigger_analysis_runs_the_job_and_populates_risk_and_recommendations(
    client: TestClient,
    auth_headers: dict[str, str],
    watchlist_service: WatchlistService,
    recommendation_service: PortfolioRecommendationService,
    risk_service: RiskAnalyticsService,
) -> None:
    portfolio_id = await make_watchlist(watchlist_service)

    response = client.post(f"/api/v1/portfolio/{portfolio_id}/analysis", headers=auth_headers)
    assert response.status_code == 202

    # BackgroundTasks run synchronously, in-process, before TestClient
    # returns control here (Starlette's own documented test behavior) —
    # no polling needed.
    status_response = client.get(f"/api/v1/portfolio/{portfolio_id}/analysis-status", headers=auth_headers)
    assert status_response.json()["data"]["status"] in ("READY", "PARTIAL")

    recommendation_requests = [r for r in await recommendation_service.list_requests() if portfolio_id in r.watchlist_ids]
    risk_requests = [r for r in await risk_service.list_requests() if r.portfolio_id == portfolio_id]
    assert len(recommendation_requests) == 1
    assert len(risk_requests) == 1


async def test_trigger_analysis_is_idempotent_over_repeated_calls(
    client: TestClient,
    auth_headers: dict[str, str],
    watchlist_service: WatchlistService,
    recommendation_service: PortfolioRecommendationService,
) -> None:
    portfolio_id = await make_watchlist(watchlist_service)

    client.post(f"/api/v1/portfolio/{portfolio_id}/analysis", headers=auth_headers)
    client.post(f"/api/v1/portfolio/{portfolio_id}/analysis", headers=auth_headers)

    assert len([r for r in await recommendation_service.list_requests() if portfolio_id in r.watchlist_ids]) == 1


def test_trigger_analysis_unknown_portfolio_returns_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(f"/api/v1/portfolio/{uuid.uuid4()}/analysis", headers=auth_headers)
    assert response.status_code == 404


async def test_trigger_analysis_requires_recommend_permission(
    client: TestClient, auth_repository: PostgresAuthRepository, auth_service: AuthenticationService
) -> None:
    headers = await make_authenticated_headers(auth_repository, auth_service, permissions=("portfolio:read",))
    response = client.post(f"/api/v1/portfolio/{uuid.uuid4()}/analysis", headers=headers)
    assert response.status_code == 403


# --------------------------------------------------------------------------
# Dependency injection / 503
# --------------------------------------------------------------------------


async def test_returns_503_when_risk_service_not_configured(
    auth_repository: PostgresAuthRepository,
    auth_service: AuthenticationService,
    authorization_service,
    watchlist_service: WatchlistService,
) -> None:
    from app.auth.middleware import AuthenticationMiddleware
    from app.auth.policies import PolicyEvaluator
    from app.api.v1.exception_handlers import register_exception_handlers
    from app.api.v1.portfolio import router as portfolio_router

    headers = await make_authenticated_headers(auth_repository, auth_service)
    portfolio_id = await make_watchlist(watchlist_service)

    app = FastAPI()
    app.state.authentication_service = auth_service
    app.state.authorization_service = authorization_service
    app.state.policy_evaluator = PolicyEvaluator()
    app.state.watchlist_service = watchlist_service
    # deliberately no app.state.risk_service
    app.add_middleware(AuthenticationMiddleware)
    app.include_router(portfolio_router, prefix="/api/v1")
    register_exception_handlers(app)

    with TestClient(app) as bare_client:
        response = bare_client.get(f"/api/v1/portfolio/risk?portfolio_id={portfolio_id}", headers=headers)
    assert response.status_code == 503


# --------------------------------------------------------------------------
# OpenAPI
# --------------------------------------------------------------------------


def test_openapi_documents_portfolio_with_tags_and_schemas(app: FastAPI) -> None:
    schema = app.openapi()
    summary_op = schema["paths"]["/api/v1/portfolio/summary"]["get"]
    assert summary_op["tags"] == ["Portfolio"]

    post_op = schema["paths"]["/api/v1/portfolio/recommendations"]["post"]
    assert "GenerateRecommendationsRequest" in schema["components"]["schemas"]
    assert post_op["responses"]["201"]
