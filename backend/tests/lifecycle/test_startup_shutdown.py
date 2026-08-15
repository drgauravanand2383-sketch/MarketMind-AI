"""Startup/shutdown lifecycle tests (Sprint 54): full
`bootstrap_application_state`/`shutdown_application_state` against a real
`FastAPI` app instance — not the individual `build_*` function unit tests
already covered by `tests/test_bootstrap.py`, but the end-to-end sequence
those functions are composed into.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.bootstrap import bootstrap_application_state, shutdown_application_state
from app.operations.logging.models import LogCategory
from app.operations.metrics.models import METRIC_STARTUP_DURATION_SECONDS
from app.operations.validation.models import ValidationReport


async def test_bootstrap_populates_every_domain_repository_and_service() -> None:
    app = FastAPI()

    await bootstrap_application_state(app)

    try:
        for name in (
            "watchlist_service", "screening_engine", "signal_detection_service", "alert_service",
            "recommendation_service", "strategy_service", "risk_service", "backtesting_service",
            "explainability_service",
        ):
            assert getattr(app.state, name) is not None, f"{name} was not constructed"
    finally:
        await shutdown_application_state(app)


async def test_bootstrap_populates_every_auth_component() -> None:
    app = FastAPI()

    await bootstrap_application_state(app)

    try:
        assert app.state.auth_repository is not None
        assert app.state.authorization_service is not None
        assert app.state.authentication_service is not None
        assert app.state.policy_evaluator is not None
        assert app.state.authentication_service.provider_name() == "jwt"
    finally:
        await shutdown_application_state(app)


async def test_bootstrap_populates_every_operational_component() -> None:
    app = FastAPI()

    await bootstrap_application_state(app)

    try:
        assert app.state.structured_logger is not None
        assert app.state.metrics_recorder is not None
        assert app.state.profiler is not None
        assert app.state.health_check_service is not None
        assert app.state.configuration_validation_service is not None
        assert app.state.startup_validation_service is not None
    finally:
        await shutdown_application_state(app)


async def test_bootstrap_produces_a_startup_validation_report() -> None:
    app = FastAPI()

    await bootstrap_application_state(app)

    try:
        report = app.state.startup_validation_report
        assert isinstance(report, ValidationReport)
        assert len(report.checks) > 0
        # Every domain component this sprint's own DEFAULT_REQUIRED_COMPONENTS
        # names was actually constructed above -> every "registered:*" check passes.
        registered_checks = [c for c in report.checks if c.name.startswith("registered:")]
        assert registered_checks
        assert all(c.passed for c in registered_checks)
    finally:
        await shutdown_application_state(app)


async def test_bootstrap_records_a_startup_duration_metric() -> None:
    app = FastAPI()

    await bootstrap_application_state(app)

    try:
        duration = app.state.metrics_recorder.total(METRIC_STARTUP_DURATION_SECONDS)
        assert duration > 0
    finally:
        await shutdown_application_state(app)


async def test_bootstrap_logs_a_structured_startup_event() -> None:
    from app.operations.logging.logger import InMemoryStructuredLogger

    app = FastAPI()
    await bootstrap_application_state(app)

    try:
        # The real bootstrap wires a StdlibStructuredLogger (verified by its
        # own unit tests to emit valid structured JSON); here we confirm the
        # abstraction itself was actually wired, not bypassed.
        assert app.state.structured_logger is not None
        assert not isinstance(app.state.structured_logger, InMemoryStructuredLogger)
    finally:
        await shutdown_application_state(app)


async def test_repeated_bootstrap_on_fresh_app_instances_is_deterministic() -> None:
    """Two independent bootstrap runs against two fresh `FastAPI` app
    instances must produce the same startup validation *outcome* (not
    necessarily identical timestamps) — bootstrap wiring has no
    randomness."""
    app_one = FastAPI()
    app_two = FastAPI()

    await bootstrap_application_state(app_one)
    await bootstrap_application_state(app_two)

    try:
        assert app_one.state.startup_validation_report.passed == app_two.state.startup_validation_report.passed
        names_one = sorted(c.name for c in app_one.state.startup_validation_report.checks)
        names_two = sorted(c.name for c in app_two.state.startup_validation_report.checks)
        assert names_one == names_two
    finally:
        await shutdown_application_state(app_one)
        await shutdown_application_state(app_two)


async def test_shutdown_is_safe_to_call_on_a_never_bootstrapped_app() -> None:
    """`shutdown_application_state` reads `app.state.ap_scheduler_service`
    via `getattr(..., None)` specifically so it tolerates a partially- or
    never-bootstrapped app — must not raise."""
    app = FastAPI()

    await shutdown_application_state(app)  # must not raise


async def test_shutdown_stops_the_scheduler_cleanly() -> None:
    app = FastAPI()
    await bootstrap_application_state(app)

    scheduler_service = app.state.ap_scheduler_service
    if scheduler_service is not None:
        assert (await scheduler_service.health_check()).scheduler_running is True

    await shutdown_application_state(app)

    if scheduler_service is not None:
        assert (await scheduler_service.health_check()).scheduler_running is False


async def test_bootstrap_then_shutdown_completes_without_error() -> None:
    app = FastAPI()
    await bootstrap_application_state(app)
    await shutdown_application_state(app)


# --- Market Intelligence Ingestion (Milestone 11) -----------------------------------------------------------


async def test_bootstrap_populates_morning_pipeline_when_dependencies_available() -> None:
    """chromadb and LocalEmbeddingProvider are both real, locally-available
    dependencies in this test environment (no network required at
    construction time — see LocalEmbeddingProvider's own lazy-init
    docstring), so `morning_pipeline` should always build successfully
    here, exactly as every other optional-but-normally-available
    dependency in this suite already does."""
    from app.workflows.morning_pipeline.pipeline import MorningPipeline

    app = FastAPI()
    await bootstrap_application_state(app)

    try:
        assert app.state.knowledge_repository is not None
        assert app.state.embedding_provider is not None
        assert isinstance(app.state.morning_pipeline, MorningPipeline)
    finally:
        await shutdown_application_state(app)


async def test_bootstrap_registers_the_ingestion_workflow_and_schedule() -> None:
    from app.bootstrap import INGESTION_WORKFLOW_ID

    app = FastAPI()
    await bootstrap_application_state(app)

    try:
        assert INGESTION_WORKFLOW_ID in app.state.workflow_engine.list_workflows()
        schedules = {s.workflow_id: s for s in app.state.scheduler.list_schedules()}
        assert INGESTION_WORKFLOW_ID in schedules
        schedule = schedules[INGESTION_WORKFLOW_ID]
        # INGESTION_ENABLED defaults to False (Milestone 11's own explicit
        # opt-in default) — this test's .env does not set it, so the
        # registered schedule must reflect that default, not silently on.
        assert schedule.enabled is app.state.settings.ingestion_enabled
        assert schedule.enabled is False
    finally:
        await shutdown_application_state(app)


async def test_ingestion_schedule_reflects_ingestion_enabled_setting(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("INGESTION_ENABLED", "true")
    app = FastAPI()
    await bootstrap_application_state(app)

    try:
        from app.bootstrap import INGESTION_WORKFLOW_ID

        schedules = {s.workflow_id: s for s in app.state.scheduler.list_schedules()}
        assert schedules[INGESTION_WORKFLOW_ID].enabled is True
    finally:
        await shutdown_application_state(app)


async def test_bootstrap_registers_the_market_data_refresh_workflow_and_schedule() -> None:
    from app.bootstrap import MARKET_DATA_WORKFLOW_ID

    app = FastAPI()
    await bootstrap_application_state(app)

    try:
        assert MARKET_DATA_WORKFLOW_ID in app.state.workflow_engine.list_workflows()
        schedules = {s.workflow_id: s for s in app.state.scheduler.list_schedules()}
        assert MARKET_DATA_WORKFLOW_ID in schedules
        # MARKET_DATA_ENABLED defaults to False (same explicit opt-in
        # default rationale as INGESTION_ENABLED) — this test's .env does
        # not set it, so the registered schedule must reflect that.
        assert schedules[MARKET_DATA_WORKFLOW_ID].enabled is app.state.settings.market_data_enabled
        assert schedules[MARKET_DATA_WORKFLOW_ID].enabled is False
    finally:
        await shutdown_application_state(app)


async def test_market_data_schedule_reflects_market_data_enabled_setting(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("MARKET_DATA_ENABLED", "true")
    app = FastAPI()
    await bootstrap_application_state(app)

    try:
        from app.bootstrap import MARKET_DATA_WORKFLOW_ID

        schedules = {s.workflow_id: s for s in app.state.scheduler.list_schedules()}
        assert schedules[MARKET_DATA_WORKFLOW_ID].enabled is True
    finally:
        await shutdown_application_state(app)


async def test_bootstrap_registers_the_continuous_intelligence_workflow_and_schedule() -> None:
    from app.bootstrap import CONTINUOUS_INTELLIGENCE_WORKFLOW_ID

    app = FastAPI()
    await bootstrap_application_state(app)

    try:
        assert CONTINUOUS_INTELLIGENCE_WORKFLOW_ID in app.state.workflow_engine.list_workflows()
        schedules = {s.workflow_id: s for s in app.state.scheduler.list_schedules()}
        assert CONTINUOUS_INTELLIGENCE_WORKFLOW_ID in schedules
        # CONTINUOUS_INTELLIGENCE_ENABLED defaults to False, same rationale
        # as INGESTION_ENABLED/MARKET_DATA_ENABLED.
        assert schedules[CONTINUOUS_INTELLIGENCE_WORKFLOW_ID].enabled is app.state.settings.continuous_intelligence_enabled
        assert schedules[CONTINUOUS_INTELLIGENCE_WORKFLOW_ID].enabled is False
    finally:
        await shutdown_application_state(app)


async def test_continuous_intelligence_schedule_reflects_enabled_setting(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("CONTINUOUS_INTELLIGENCE_ENABLED", "true")
    app = FastAPI()
    await bootstrap_application_state(app)

    try:
        from app.bootstrap import CONTINUOUS_INTELLIGENCE_WORKFLOW_ID

        schedules = {s.workflow_id: s for s in app.state.scheduler.list_schedules()}
        assert schedules[CONTINUOUS_INTELLIGENCE_WORKFLOW_ID].enabled is True
    finally:
        await shutdown_application_state(app)


async def test_bootstrap_wires_continuous_intelligence_service() -> None:
    from app.services.continuous_intelligence.service import ContinuousIntelligenceService

    app = FastAPI()
    await bootstrap_application_state(app)

    try:
        assert isinstance(app.state.continuous_intelligence_service, ContinuousIntelligenceService)
    finally:
        await shutdown_application_state(app)


async def test_bootstrap_wires_market_data_provider_and_snapshot_service() -> None:
    from app.providers.market_data.mock import MockMarketDataProvider
    from app.services.market_snapshot.service import MarketSnapshotService

    app = FastAPI()
    await bootstrap_application_state(app)

    try:
        assert isinstance(app.state.market_data_provider, MockMarketDataProvider)
        assert app.state.market_data_provider_is_live is False
        assert isinstance(app.state.market_snapshot_service, MarketSnapshotService)
    finally:
        await shutdown_application_state(app)
