"""Tests for the FastAPI application's startup/shutdown lifecycle,
dependency registration, and health endpoint — using the real lifespan
(via `with TestClient(app) as client:`), not a mocked one."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

# --- Startup tests -----------------------------------------------------------


def test_startup_populates_agent_runtime_in_state() -> None:
    app = create_app()
    with TestClient(app) as client:
        assert client.app.state.agent_runtime is not None


def test_startup_populates_news_collector_agent_in_state() -> None:
    app = create_app()
    with TestClient(app) as client:
        assert client.app.state.news_collector_agent is not None
        assert client.app.state.news_collector_agent.agent_id == "AGT-003"


def test_startup_knowledge_repository_is_repository_or_none() -> None:
    """Degrades gracefully to None rather than crashing startup when
    ChromaDB isn't installed/reachable in this environment."""
    app = create_app()
    with TestClient(app) as client:
        repository = client.app.state.knowledge_repository
        assert repository is None or hasattr(repository, "search")


def test_startup_embedding_provider_is_none() -> None:
    """Documents the intentional gap: no concrete BaseEmbeddingProvider exists yet."""
    app = create_app()
    with TestClient(app) as client:
        assert client.app.state.embedding_provider is None


def test_startup_populates_settings_in_state() -> None:
    app = create_app()
    with TestClient(app) as client:
        assert client.app.state.settings is not None


# --- Shutdown tests -----------------------------------------------------------


def test_shutdown_does_not_raise() -> None:
    app = create_app()
    with TestClient(app):
        pass  # startup and shutdown both ran without raising


def test_app_can_start_and_stop_multiple_times_independently() -> None:
    for _ in range(2):
        app = create_app()
        with TestClient(app) as client:
            assert client.app.state.agent_runtime is not None


# --- Dependency registration tests -----------------------------------------------------------


def test_agent_runtime_is_a_shared_instance_across_requests() -> None:
    app = create_app()
    with TestClient(app) as client:
        runtime_before = client.app.state.agent_runtime
        client.get("/health")
        runtime_after = client.app.state.agent_runtime
        assert runtime_before is runtime_after


def test_company_research_never_returns_500_after_startup() -> None:
    """AgentRuntime is always populated by bootstrap, so this must resolve
    to either a real report (200) or a graceful "not configured" (503) —
    never an unhandled server error."""
    app = create_app()
    with TestClient(app) as client:
        response = client.post("/company/research", json={"company_name": "Apple"})
        assert response.status_code in (200, 503)


def test_morning_run_never_returns_500_after_startup() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.post("/morning/run", json={})
        assert response.status_code in (200, 503)


# --- Health endpoint tests -----------------------------------------------------------


def test_health_endpoint_after_startup() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_health_endpoint_does_not_depend_on_knowledge_repository() -> None:
    """Health must succeed regardless of whether ChromaDB happened to be
    reachable during this test run."""
    app = create_app()
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200


# --- Scheduler / APScheduler lifecycle tests -----------------------------------------------------------


def test_startup_populates_workflow_engine_and_scheduler_in_state() -> None:
    app = create_app()
    with TestClient(app) as client:
        assert client.app.state.workflow_engine is not None
        assert client.app.state.scheduler is not None


def test_startup_populates_ap_scheduler_service_in_state() -> None:
    app = create_app()
    with TestClient(app) as client:
        assert client.app.state.ap_scheduler_service is not None


def test_scheduler_is_running_during_the_apps_lifetime() -> None:
    app = create_app()
    with TestClient(app) as client:
        service = client.app.state.ap_scheduler_service
        assert service._ap_scheduler.running is True


def test_scheduler_is_stopped_after_shutdown() -> None:
    app = create_app()
    with TestClient(app) as client:
        service = client.app.state.ap_scheduler_service

    # The `with` block has exited: lifespan shutdown has fully completed.
    assert service._ap_scheduler.running is False
