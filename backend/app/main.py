"""Application entrypoint for MarketMind AI.

This module only assembles the ASGI application object — router
registration, middleware, exception handlers, OpenAPI metadata, and
lifespan wiring — and contains no business, agent, or API logic itself.
Run with: `uvicorn app.main:app`.

`/api/v1` (Sprint 55) is additive: the pre-existing, unversioned
Intelligence Query API (`app.api.intelligence`, mounted at the
application root) is untouched — both routers coexist on the same
application instance.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.api.intelligence.router import router as intelligence_router
from app.api.v1.exception_handlers import register_exception_handlers
from app.api.v1.middleware import register_middleware
from app.api.v1.router import router as v1_router
from app.api.v1.schemas.result_store import InMemoryResultStore
from app.api.ws import router as ws_router
from app.api.ws.connection_manager.manager import ConnectionManager
from app.api.ws.publishers.event_publisher import EventPublisher
from app.config.models import APISettings
from app.lifespan import lifespan

__all__ = ["create_app", "app"]

OPENAPI_TAGS_METADATA = [
    {
        "name": "Auth",
        "description": (
            "Login, token refresh, and logout — reuses "
            "`app.auth.services.authentication.AuthenticationService` "
            "(Frontend Milestone 1; the framework itself is Sprint 56)."
        ),
    },
    {
        "name": "Health",
        "description": (
            "Application health and readiness — reuses "
            "`app.operations.health.HealthCheckService` (Sprint 54)."
        ),
    },
    {
        "name": "System",
        "description": (
            "Read-only introspection of version, non-secret configuration, "
            "capabilities, and the service inventory."
        ),
    },
    {
        "name": "Watchlists",
        "description": (
            "Authenticated CRUD over watchlists and their tracked companies — "
            "reuses `app.watchlist.service.WatchlistService` (Sprint 57)."
        ),
    },
    {
        "name": "Portfolio",
        "description": (
            "Authenticated portfolio views computed on demand from a watchlist's "
            "companies — a `portfolio_id` is a `watchlist_id`. Reuses "
            "`WatchlistService`, `PortfolioIntelligenceAgent`, `RiskAnalyticsService`, "
            "and `PortfolioRecommendationService` (Sprint 57)."
        ),
    },
    {
        "name": "Company Research",
        "description": (
            "Authenticated company research reports — reuses "
            "`CompanyResearchAgent` (Sprint 58)."
        ),
    },
    {
        "name": "Screening",
        "description": (
            "Authenticated company screening profiles and runs — reuses "
            "`app.screening.engine.ScreeningEngine` (Sprint 58)."
        ),
    },
    {
        "name": "Signal Detection",
        "description": (
            "Authenticated signal definitions and evaluation — reuses "
            "`app.signals.engine.SignalDetectionService` (Sprint 58)."
        ),
    },
    {
        "name": "Alerts",
        "description": (
            "Authenticated alert lookup and rule evaluation — reuses "
            "`app.alerts.engine.AlertService` (Sprint 58)."
        ),
    },
    {
        "name": "Strategy Evaluation",
        "description": (
            "Authenticated investment strategy management and evaluation — reuses "
            "`app.strategy.engine.StrategyEvaluationService` (Sprint 58)."
        ),
    },
    {
        "name": "Backtesting",
        "description": (
            "Authenticated backtest execution and results — reuses "
            "`app.backtesting.engine.BacktestingService` (Sprint 58)."
        ),
    },
    {
        "name": "Explainability",
        "description": (
            "Authenticated explanation generation and lookup — reuses "
            "`app.explainability.engine.ExplainabilityService` (Sprint 58)."
        ),
    },
    {
        "name": "Real-Time Events",
        "description": (
            "WebSocket delivery of already-completed backend events (`/ws`) — "
            "reuses the existing authentication/authorization framework; "
            "publishes no new business logic (Sprint 59)."
        ),
    },
]


def create_app() -> FastAPI:
    """Construct the MarketMind AI FastAPI application."""
    api_settings = APISettings()
    application = FastAPI(
        title="MarketMind AI",
        description=(
            "MarketMind AI — a modular, multi-agent market intelligence platform. "
            "`/api/v1` exposes the completed backend (screening, signal detection, alerts, "
            "recommendations, strategy evaluation, risk analytics, backtesting, and "
            "explainability), plus authenticated watchlist and portfolio management, "
            "as a versioned REST API. `/ws` delivers the same completed activity in "
            "real time over an authenticated WebSocket connection."
        ),
        version="1.0.0",
        openapi_tags=OPENAPI_TAGS_METADATA,
        lifespan=lifespan,
    )
    application.include_router(intelligence_router)
    application.include_router(v1_router, prefix=api_settings.v1_prefix)
    application.include_router(ws_router, tags=["Real-Time Events"])
    register_middleware(application, api_settings=api_settings)
    register_exception_handlers(application)

    # Thin, HTTP-layer-only result caches (Sprint 58) — not business logic,
    # so constructed here rather than in app.bootstrap.py's composition
    # root. See app.api.v1.schemas.result_store's module docstring.
    application.state.research_report_store = InMemoryResultStore("research report")
    application.state.screening_result_store = InMemoryResultStore("screening result")
    application.state.signal_result_store = InMemoryResultStore("signal result")

    # Real-Time Event & WebSocket Framework (Sprint 59) — connection state
    # and the event publisher are pure API-layer infrastructure (no
    # business logic, no external messaging system), so constructed here
    # rather than in app.bootstrap.py, exactly like the result caches above.
    connection_manager = ConnectionManager()
    application.state.connection_manager = connection_manager
    application.state.event_publisher = EventPublisher(connection_manager)

    return application


app = create_app()
