"""Integration tests proving the Sprint 59 router wiring actually works
end-to-end: a real REST action (POST /alerts/evaluate, POST /backtests,
...) triggers a real WebSocket event delivery to a subscribed connection
— not just the isolated `EventPublisher`/`ConnectionManager` unit tests
above. Each test builds a composite app mounting both the relevant
`/api/v1` router and the `/ws` router, sharing one `ConnectionManager`/
`EventPublisher` pair via `app.state`, exactly as `app.main.create_app()`
wires them in production.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.alerts.engine import AlertService
from app.alerts.models import AlertCondition, AlertOperator
from app.api.v1.alerts import router as alerts_router
from app.api.v1.backtests import router as backtests_router
from app.api.v1.exception_handlers import register_exception_handlers
from app.api.v1.explainability import router as explainability_router
from app.api.v1.portfolio import router as portfolio_router
from app.api.v1.routers.health import router as health_router
from app.api.v1.strategies import router as strategies_router
from app.api.ws import router as ws_router
from app.api.ws.connection_manager.manager import ConnectionManager
from app.api.ws.publishers.event_publisher import EventPublisher
from app.auth.middleware import AuthenticationMiddleware
from app.auth.policies import PolicyEvaluator
from app.auth.services.authentication import AuthenticationService
from app.auth.services.authorization import AuthorizationService
from app.backtesting.engine import BacktestingService
from app.explainability.engine import ExplainabilityService
from app.operations.health.service import HealthCheckService
from app.recommendations.engine import PortfolioRecommendationService
from app.repositories.alerts.postgres.models import Base as AlertsBase
from app.repositories.alerts.postgres.repository import PostgresAlertRepository, PostgresAlertRuleRepository
from app.repositories.backtesting.postgres.models import Base as BacktestingBase
from app.repositories.backtesting.postgres.repository import PostgresBacktestingRepository
from app.repositories.explainability.postgres.models import Base as ExplainabilityBase
from app.repositories.explainability.postgres.repository import PostgresExplainabilityRepository
from app.repositories.recommendations.postgres.models import Base as RecommendationBase
from app.repositories.recommendations.postgres.repository import PostgresRecommendationRepository
from app.repositories.risk.postgres.models import Base as RiskBase
from app.repositories.risk.postgres.repository import PostgresRiskAnalyticsRepository
from app.repositories.strategy.postgres.models import Base as StrategyBase
from app.repositories.strategy.postgres.repository import PostgresStrategyRepository
from app.repositories.watchlist.postgres.models import Base as WatchlistBase
from app.repositories.watchlist.postgres.repository import PostgresWatchlistRepository
from app.risk.engine import RiskAnalyticsService
from app.strategy.engine import StrategyEvaluationService
from app.watchlist.service import WatchlistService
from tests.api.v1._auth_fixtures import (  # noqa: F401 - re-exported as fixtures
    auth_repository,
    auth_service,
    authorization_service,
    make_authenticated_headers,
)

NOW = datetime(2026, 8, 8, tzinfo=UTC)


async def _sqlite_session_factory(base: type) -> async_sessionmaker:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def watchlist_service() -> AsyncIterator[WatchlistService]:
    session_factory = await _sqlite_session_factory(WatchlistBase)
    yield WatchlistService(PostgresWatchlistRepository(session_factory))


@pytest.fixture
async def recommendation_repository() -> AsyncIterator[PostgresRecommendationRepository]:
    session_factory = await _sqlite_session_factory(RecommendationBase)
    yield PostgresRecommendationRepository(session_factory)


@pytest.fixture
def recommendation_service(
    recommendation_repository: PostgresRecommendationRepository,
) -> PortfolioRecommendationService:
    return PortfolioRecommendationService(recommendation_repository, now_fn=lambda: NOW)


@pytest.fixture
async def strategy_service() -> AsyncIterator[StrategyEvaluationService]:
    session_factory = await _sqlite_session_factory(StrategyBase)
    yield StrategyEvaluationService(PostgresStrategyRepository(session_factory), now_fn=lambda: NOW)


@pytest.fixture
async def risk_service() -> AsyncIterator[RiskAnalyticsService]:
    session_factory = await _sqlite_session_factory(RiskBase)
    yield RiskAnalyticsService(PostgresRiskAnalyticsRepository(session_factory), now_fn=lambda: NOW)


@pytest.fixture
async def backtesting_service(
    recommendation_service: PortfolioRecommendationService,
    strategy_service: StrategyEvaluationService,
    risk_service: RiskAnalyticsService,
) -> AsyncIterator[BacktestingService]:
    session_factory = await _sqlite_session_factory(BacktestingBase)
    yield BacktestingService(
        PostgresBacktestingRepository(session_factory), recommendation_service, strategy_service, risk_service,
        now_fn=lambda: NOW,
    )


@pytest.fixture
async def explainability_service(
    recommendation_service: PortfolioRecommendationService,
    strategy_service: StrategyEvaluationService,
    risk_service: RiskAnalyticsService,
    backtesting_service: BacktestingService,
) -> AsyncIterator[ExplainabilityService]:
    session_factory = await _sqlite_session_factory(ExplainabilityBase)
    yield ExplainabilityService(
        PostgresExplainabilityRepository(session_factory), recommendation_service, strategy_service, risk_service,
        backtesting_service, now_fn=lambda: NOW,
    )


@pytest.fixture
async def alert_service() -> AsyncIterator[AlertService]:
    rule_session_factory = await _sqlite_session_factory(AlertsBase)
    rule_repository = PostgresAlertRuleRepository(rule_session_factory)
    alert_repository = PostgresAlertRepository(rule_session_factory)
    yield AlertService(rule_repository, alert_repository, now_fn=lambda: NOW)


@pytest.fixture
def connection_manager() -> ConnectionManager:
    return ConnectionManager()


@pytest.fixture
def event_publisher(connection_manager: ConnectionManager) -> EventPublisher:
    return EventPublisher(connection_manager)


@pytest.fixture
def app(
    auth_service: AuthenticationService,
    authorization_service: AuthorizationService,
    connection_manager: ConnectionManager,
    event_publisher: EventPublisher,
    watchlist_service: WatchlistService,
    recommendation_service: PortfolioRecommendationService,
    strategy_service: StrategyEvaluationService,
    risk_service: RiskAnalyticsService,
    backtesting_service: BacktestingService,
    explainability_service: ExplainabilityService,
    alert_service: AlertService,
) -> FastAPI:
    application = FastAPI()
    application.state.authentication_service = auth_service
    application.state.authorization_service = authorization_service
    application.state.policy_evaluator = PolicyEvaluator()
    application.state.connection_manager = connection_manager
    application.state.event_publisher = event_publisher
    application.state.watchlist_service = watchlist_service
    application.state.recommendation_service = recommendation_service
    application.state.strategy_service = strategy_service
    application.state.risk_service = risk_service
    application.state.backtesting_service = backtesting_service
    application.state.explainability_service = explainability_service
    application.state.alert_service = alert_service
    application.state.health_check_service = HealthCheckService()
    application.add_middleware(AuthenticationMiddleware)
    application.include_router(alerts_router, prefix="/api/v1")
    application.include_router(backtests_router, prefix="/api/v1")
    application.include_router(portfolio_router, prefix="/api/v1")
    application.include_router(strategies_router, prefix="/api/v1")
    application.include_router(explainability_router, prefix="/api/v1")
    application.include_router(health_router, prefix="/api/v1")
    application.include_router(ws_router)
    register_exception_handlers(application)
    return application


@pytest.fixture
def client(app: FastAPI):
    with TestClient(app) as test_client:
        yield test_client


ALL_PERMISSIONS = (
    "alerts:read", "alerts:evaluate", "backtest:run", "backtest:read", "portfolio:read", "portfolio:recommend",
    "strategy:read", "strategy:update", "strategy:evaluate", "explainability:generate", "explainability:read",
)


@pytest.fixture
async def headers(auth_repository, auth_service) -> dict[str, str]:
    return await make_authenticated_headers(auth_repository, auth_service, permissions=ALL_PERMISSIONS)


@pytest.fixture
async def ws_token(auth_repository, auth_service) -> str:
    headers = await make_authenticated_headers(
        auth_repository, auth_service, permissions=ALL_PERMISSIONS, username="ws-subscriber"
    )
    return headers["Authorization"].removeprefix("Bearer ")


async def test_evaluate_alerts_publishes_alert_generated_event(
    client: TestClient, headers: dict[str, str], ws_token: str, alert_service: AlertService
) -> None:
    await alert_service.create_rule(
        "Rule", conditions=(AlertCondition(id="c1", field="score", operator=AlertOperator.GREATER_THAN, value=50),)
    )

    with client.websocket_connect(f"/ws?token={ws_token}") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "event_types": ["ALERT_GENERATED"]})
        ws.receive_json()

        response = client.post(
            "/api/v1/alerts/evaluate",
            json={"signals": [{
                "ticker": "AAPL", "signal_name": "x", "category": "VALUATION", "triggered": True,
                "confidence": 90.0, "score": 80.0, "priority": "HIGH", "reason": "matched",
                "timestamp": NOW.isoformat(),
            }]},
            headers=headers,
        )
        assert response.status_code == 201

        event_message = ws.receive_json()
        assert event_message["type"] == "event"
        assert event_message["event"]["event_type"] == "ALERT_GENERATED"
        assert event_message["event"]["payload"]["ticker"] == "AAPL"


async def test_create_backtest_publishes_started_and_completed_events(
    client: TestClient,
    headers: dict[str, str],
    ws_token: str,
    recommendation_repository: PostgresRecommendationRepository,
) -> None:
    from app.recommendations.models import (
        RecommendationCandidate,
        RecommendationResult,
        RecommendationSummary,
        RecommendationType,
    )

    candidate = RecommendationCandidate(
        ticker="AAPL", overall_score=70.0, confidence=80.0, recommendation=RecommendationType.BUY,
        reasoning="x", created_at=NOW,
    )
    result = RecommendationResult(
        request_id="rec-1", generated_at=NOW, total_candidates=1, recommendations=(candidate,),
        summary=RecommendationSummary(),
    )
    await recommendation_repository.store_result(result)

    with client.websocket_connect(f"/ws?token={ws_token}") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "event_types": ["BACKTEST_STARTED", "BACKTEST_COMPLETED"]})
        ws.receive_json()

        response = client.post(
            "/api/v1/backtests",
            json={
                "name": "Integration Backtest", "start_date": "2026-01-01", "end_date": "2026-03-31",
                "initial_capital": 100000.0, "benchmark": "SPY",
                "snapshots": [{"timestamp": NOW.isoformat(), "recommendation_result_id": "rec-1"}],
            },
            headers=headers,
        )
        assert response.status_code == 201

        started = ws.receive_json()
        assert started["event"]["event_type"] == "BACKTEST_STARTED"
        completed = ws.receive_json()
        assert completed["event"]["event_type"] == "BACKTEST_COMPLETED"
        assert started["event"]["correlation_id"] == completed["event"]["correlation_id"]


async def test_create_portfolio_recommendations_publishes_event(
    client: TestClient, headers: dict[str, str], ws_token: str, watchlist_service: WatchlistService
) -> None:
    watchlist = await watchlist_service.create_watchlist("Tech")

    with client.websocket_connect(f"/ws?token={ws_token}") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "event_types": ["RECOMMENDATION_GENERATED"]})
        ws.receive_json()

        response = client.post(
            "/api/v1/portfolio/recommendations",
            json={"portfolio_id": watchlist.id, "evidence": [{"ticker": "AAPL"}]},
            headers=headers,
        )
        assert response.status_code == 201

        event_message = ws.receive_json()
        assert event_message["event"]["event_type"] == "RECOMMENDATION_GENERATED"


async def test_evaluate_strategies_publishes_event(
    client: TestClient,
    headers: dict[str, str],
    ws_token: str,
    recommendation_repository: PostgresRecommendationRepository,
) -> None:
    from app.recommendations.models import (
        RecommendationCandidate,
        RecommendationResult,
        RecommendationSummary,
        RecommendationType,
    )

    candidate = RecommendationCandidate(
        ticker="AAPL", overall_score=70.0, confidence=80.0, recommendation=RecommendationType.BUY,
        reasoning="x", created_at=NOW,
    )
    await recommendation_repository.store_result(
        RecommendationResult(
            request_id="rec-2", generated_at=NOW, total_candidates=1, recommendations=(candidate,),
            summary=RecommendationSummary(),
        )
    )

    with client.websocket_connect(f"/ws?token={ws_token}") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "event_types": ["STRATEGY_EVALUATION_COMPLETED"]})
        ws.receive_json()

        response = client.post(
            "/api/v1/strategies/evaluate", json={"recommendation_result_id": "rec-2"}, headers=headers
        )
        assert response.status_code == 201

        event_message = ws.receive_json()
        assert event_message["event"]["event_type"] == "STRATEGY_EVALUATION_COMPLETED"


async def test_create_explanation_publishes_event(
    client: TestClient,
    headers: dict[str, str],
    ws_token: str,
    recommendation_repository: PostgresRecommendationRepository,
) -> None:
    from app.recommendations.models import (
        RecommendationCandidate,
        RecommendationResult,
        RecommendationSummary,
        RecommendationType,
    )

    candidate = RecommendationCandidate(
        ticker="AAPL", overall_score=70.0, confidence=80.0, recommendation=RecommendationType.BUY,
        reasoning="x", created_at=NOW,
    )
    await recommendation_repository.store_result(
        RecommendationResult(
            request_id="rec-3", generated_at=NOW, total_candidates=1, recommendations=(candidate,),
            summary=RecommendationSummary(),
        )
    )

    with client.websocket_connect(f"/ws?token={ws_token}") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "event_types": ["EXPLAINABILITY_COMPLETED"]})
        ws.receive_json()

        response = client.post(
            "/api/v1/explainability",
            json={"name": "Explain rec-3", "recommendation_result_id": "rec-3"},
            headers=headers,
        )
        assert response.status_code == 201

        event_message = ws.receive_json()
        assert event_message["event"]["event_type"] == "EXPLAINABILITY_COMPLETED"


async def test_health_status_change_publishes_event_on_second_call(
    client: TestClient, ws_token: str
) -> None:
    with client.websocket_connect(f"/ws?token={ws_token}") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "event_types": ["HEALTH_STATUS_CHANGED"]})
        ws.receive_json()

        # First call always "changes" state from None -> whatever it computes.
        first = client.get("/api/v1/health")
        assert first.status_code == 200
        first_event = ws.receive_json()
        assert first_event["event"]["event_type"] == "HEALTH_STATUS_CHANGED"

        # Second call with unchanged state must NOT publish again — confirm
        # via a live ping instead of a second event arriving.
        second = client.get("/api/v1/health")
        assert second.status_code == 200
        ws.send_json({"action": "ping"})
        pong = ws.receive_json()
        assert pong["type"] == "pong"


# --------------------------------------------------------------------------
# Sprint 60 — representative end-to-end release-readiness workflows.
# --------------------------------------------------------------------------


def test_authenticated_request_lifecycle(client: TestClient, headers: dict[str, str]) -> None:
    """The full authenticated-request shape: no token -> 401, a valid
    token + the right permission -> 200, exercised against a real
    protected endpoint through the real middleware/policy chain."""
    unauthenticated = client.get("/api/v1/alerts")
    assert unauthenticated.status_code == 401

    authenticated = client.get("/api/v1/alerts", headers=headers)
    assert authenticated.status_code == 200
    assert "data" in authenticated.json()
    assert "meta" in authenticated.json()


async def test_full_platform_workflow_chains_every_domain_with_live_notifications(
    client: TestClient,
    headers: dict[str, str],
    ws_token: str,
    watchlist_service: WatchlistService,
    alert_service: AlertService,
) -> None:
    """One coherent "day in the life" workflow spanning every domain this
    platform exposes, with a single WebSocket connection subscribed to
    everything confirming each REST action's real-time notification
    arrives, correctly typed and correctly correlated, in the order the
    actions actually happened. This is the sprint's own "Portfolio
    recommendation, Backtest, Explainability, Alert evaluation, WebSocket
    notification" representative-workflow requirement, exercised as one
    continuous release-readiness scenario rather than five isolated ones.
    """
    from app.alerts.models import AlertCondition, AlertOperator

    watchlist = await watchlist_service.create_watchlist("RC1 Smoke Test Portfolio")
    await alert_service.create_rule(
        "RC1 Smoke Rule",
        conditions=(AlertCondition(id="c1", field="score", operator=AlertOperator.GREATER_THAN, value=50),),
    )

    with client.websocket_connect(f"/ws?token={ws_token}") as ws:
        connected = ws.receive_json()
        assert connected["type"] == "connected"

        ws.send_json({"action": "subscribe", "event_types": []})  # every event type
        subscribed = ws.receive_json()
        assert subscribed["type"] == "subscribed"

        # 1. Portfolio recommendation
        recommendation_response = client.post(
            "/api/v1/portfolio/recommendations",
            json={"portfolio_id": watchlist.id, "evidence": [{"ticker": "AAPL", "sector": "Technology"}]},
            headers=headers,
        )
        assert recommendation_response.status_code == 201
        recommendation_result_id = recommendation_response.json()["data"]["request_id"]

        recommendation_event = ws.receive_json()
        assert recommendation_event["event"]["event_type"] == "RECOMMENDATION_GENERATED"
        assert recommendation_event["event"]["correlation_id"] == recommendation_result_id

        # 2. Strategy evaluation, against that same recommendation
        strategy_response = client.post(
            "/api/v1/strategies/evaluate",
            json={"recommendation_result_id": recommendation_result_id},
            headers=headers,
        )
        assert strategy_response.status_code == 201

        strategy_event = ws.receive_json()
        assert strategy_event["event"]["event_type"] == "STRATEGY_EVALUATION_COMPLETED"

        # 3. Backtest, referencing the same recommendation result
        backtest_response = client.post(
            "/api/v1/backtests",
            json={
                "name": "RC1 Smoke Backtest", "start_date": "2026-01-01", "end_date": "2026-03-31",
                "initial_capital": 100000.0, "benchmark": "SPY",
                "snapshots": [
                    {"timestamp": "2026-01-15T00:00:00Z", "recommendation_result_id": recommendation_result_id}
                ],
            },
            headers=headers,
        )
        assert backtest_response.status_code == 201
        backtest_run_id = backtest_response.json()["data"]["request_id"]

        backtest_started_event = ws.receive_json()
        assert backtest_started_event["event"]["event_type"] == "BACKTEST_STARTED"
        backtest_completed_event = ws.receive_json()
        assert backtest_completed_event["event"]["event_type"] == "BACKTEST_COMPLETED"
        assert backtest_completed_event["event"]["correlation_id"] == backtest_run_id

        # 4. Explainability, tying the recommendation and backtest together
        explanation_response = client.post(
            "/api/v1/explainability",
            json={
                "name": "RC1 Smoke Explanation", "recommendation_result_id": recommendation_result_id,
                "backtest_run_id": backtest_run_id,
            },
            headers=headers,
        )
        assert explanation_response.status_code == 201

        explainability_event = ws.receive_json()
        assert explainability_event["event"]["event_type"] == "EXPLAINABILITY_COMPLETED"

        # 5. Alert evaluation
        alert_response = client.post(
            "/api/v1/alerts/evaluate",
            json={"signals": [{
                "ticker": "AAPL", "signal_name": "x", "category": "VALUATION", "triggered": True,
                "confidence": 90.0, "score": 80.0, "priority": "HIGH", "reason": "matched",
                "timestamp": "2026-01-15T00:00:00Z",
            }]},
            headers=headers,
        )
        assert alert_response.status_code == 201

        alert_event = ws.receive_json()
        assert alert_event["event"]["event_type"] == "ALERT_GENERATED"

        # Every notification arrived — nothing left buffered, nothing extra.
        ws.send_json({"action": "ping"})
        pong = ws.receive_json()
        assert pong["type"] == "pong"
