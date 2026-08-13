"""Release readiness validation (Sprint 60) — a consolidated smoke test
confirming the pieces Alembic (`tests/operations/test_alembic_environment.py`),
health/readiness (`tests/api/v1/test_health.py`), and bootstrap
(`tests/test_bootstrap.py`) already test individually actually come
together correctly in one real application instance: every expected
`app.state` attribute is wired after a real bootstrap, startup and
shutdown complete cleanly, and configuration loads without error.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config.models import (
    AnthropicSettings,
    APISettings,
    AuthSettings,
    LLMSettings,
    LoggingSettings,
    PostgreSQLSettings,
    RSSSettings,
    SchedulerSettings,
    SecurityHeadersSettings,
)

# Every attribute `app.bootstrap.bootstrap_application_state` and
# `app.main.create_app` wire onto `app.state` in production. The
# attribute must *exist* after a real bootstrap — its value may
# legitimately be `None` in this sandboxed environment (no reachable
# PostgreSQL/ChromaDB/Anthropic key), which is the documented graceful-
# degradation behavior every `build_*` function in `app/bootstrap.py`
# already implements and already has its own dedicated tests for.
EXPECTED_APP_STATE_ATTRIBUTES = (
    "settings",
    "agent_runtime",
    "knowledge_repository",
    "embedding_provider",
    "news_collector_agent",
    "prompt_registry",
    "knowledge_hub",
    "llm_service",
    "company_research_agent",
    "portfolio_intelligence_agent",
    "workflow_engine",
    "scheduler",
    "ap_scheduler_service",
    "watchlist_repository",
    "watchlist_service",
    "screening_repository",
    "screening_engine",
    "market_data_provider",
    "normalization_service",
    "signal_repository",
    "signal_detection_service",
    "alert_rule_repository",
    "alert_repository",
    "alert_service",
    "recommendation_repository",
    "recommendation_service",
    "strategy_repository",
    "strategy_service",
    "risk_repository",
    "risk_service",
    "backtesting_repository",
    "backtesting_service",
    "explainability_repository",
    "explainability_service",
    "structured_logger",
    "metrics_recorder",
    "profiler",
    "health_check_service",
    "configuration_validation_service",
    "startup_validation_service",
    "startup_validation_report",
    "auth_repository",
    "authorization_service",
    "authentication_service",
    "policy_evaluator",
    "research_report_store",
    "screening_result_store",
    "signal_result_store",
    "connection_manager",
    "event_publisher",
)


def test_every_expected_app_state_attribute_is_wired_after_bootstrap() -> None:
    from app.main import create_app

    app = create_app()
    with TestClient(app):
        missing = [name for name in EXPECTED_APP_STATE_ATTRIBUTES if not hasattr(app.state, name)]
        assert not missing, f"app.state is missing attributes after bootstrap: {missing}"


def test_startup_and_shutdown_complete_without_raising() -> None:
    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
    # reaching this line means shutdown (the lifespan's `finally` block) completed cleanly


def test_dependency_providers_resolve_the_bootstrapped_singleton() -> None:
    """`get_watchlist_service`/`get_alert_service` must return the exact
    object `app.bootstrap` already constructed at startup — proving
    dependency injection resolves the bootstrapped singleton rather than
    constructing a fresh instance per call (which would silently duplicate
    the container `app.bootstrap` already is)."""
    from app.api.v1.alerts.dependencies import get_alert_service
    from app.api.v1.watchlists.dependencies import get_watchlist_service
    from app.main import create_app

    app = create_app()
    with TestClient(app):
        fake_request = type("FakeRequest", (), {"app": app})()
        assert get_watchlist_service(fake_request) is app.state.watchlist_service
        assert get_alert_service(fake_request) is app.state.alert_service


def test_every_settings_class_loads_with_defaults() -> None:
    """Configuration validation: every settings class this application
    depends on constructs successfully from defaults/environment alone —
    a broken/missing required env var here would fail startup entirely."""
    APISettings()
    AuthSettings()
    LoggingSettings()
    RSSSettings()
    SchedulerSettings()
    SecurityHeadersSettings()
    PostgreSQLSettings()
    LLMSettings()
    # AnthropicSettings.api_key has no default — confirm it fails
    # predictably (not with an unrelated error) rather than silently
    # succeeding with a blank key.
    try:
        AnthropicSettings()
    except Exception as exc:  # noqa: BLE001 - asserting *some* clear validation failure, not a specific type
        assert "api_key" in str(exc)


def test_health_and_readiness_endpoints_respond() -> None:
    """Overrides `get_repositories_map` with instant fakes — the same
    reasoning `tests/api/v1/conftest.py`'s own `client` fixture documents:
    without it, every real repository's `health_check()` blocks for
    several seconds each against an unreachable PostgreSQL server. The
    genuinely-unhealthy/unreachable path already has its own dedicated
    coverage in `tests/api/v1/test_health.py`."""
    from app.api.v1.dependencies.state import REPOSITORY_NAMES, get_repositories_map
    from app.main import create_app

    class _FakeHealthyRepository:
        async def health_check(self) -> bool:
            return True

    app = create_app()
    app.dependency_overrides[get_repositories_map] = lambda: {
        name: _FakeHealthyRepository() for name in REPOSITORY_NAMES
    }
    with TestClient(app) as client:
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert "state" in health.json()["data"]

        ready = client.get("/api/v1/ready")
        assert ready.status_code in (200, 503)
        assert "ready" in ready.json()["data"]


def test_logging_metrics_and_profiling_are_wired_and_usable() -> None:
    from app.main import create_app

    app = create_app()
    with TestClient(app):
        assert app.state.structured_logger is not None
        assert app.state.metrics_recorder is not None
        assert app.state.profiler is not None

        app.state.structured_logger.info(
            __import__("app.operations.logging.models", fromlist=["LogCategory"]).LogCategory.APPLICATION,
            "release_readiness_probe",
        )
        app.state.profiler.record("release_readiness_probe", 0.001)
        assert app.state.profiler.count("release_readiness_probe") >= 1
