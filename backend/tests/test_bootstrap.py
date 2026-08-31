"""Unit tests for the bootstrap composition root's individual components."""

from __future__ import annotations

import logging

import pytest

from app.agents.company_research.agent import CompanyResearchAgent
from app.agents.portfolio_intelligence.agent import PortfolioIntelligenceAgent
from app.bootstrap import (
    AppSettings,
    EmptyKnowledgeHub,
    EmptyToolRegistry,
    InProcessMemory,
    NoOpEventBus,
    SettingsConfiguration,
    build_alert_repository,
    build_alert_rule_repository,
    build_alert_service,
    build_auth_repository,
    build_authentication_provider,
    build_authentication_service,
    build_authorization_service,
    build_backtesting_repository,
    build_backtesting_service,
    build_clock,
    build_company_research_agent,
    build_configuration_validation_service,
    build_embedding_provider,
    build_entity_resolution_service,
    build_explainability_repository,
    build_explainability_service,
    build_global_market_category_pipeline,
    build_global_market_intelligence_workflow,
    build_global_market_ranked_asset_repository,
    build_global_market_report_repository,
    build_global_market_run_repository,
    build_global_market_session_resolver,
    build_global_market_universe_registry,
    build_global_markets_research_agent,
    build_health_check_service,
    build_initial_analysis_service,
    build_jwt_signer,
    build_knowledge_hub,
    build_knowledge_repository,
    build_llm_service,
    build_market_data_provider,
    build_market_snapshot_service,
    build_metrics_recorder,
    build_news_collector_agent,
    build_normalization_service,
    build_password_hasher,
    build_penny_microcap_intelligence_agent,
    build_policy_evaluator,
    build_portfolio_intelligence_agent,
    build_portfolio_market_snapshot_service,
    build_profiler,
    build_prompt_registry,
    build_recommendation_repository,
    build_recommendation_service,
    build_risk_repository,
    build_risk_service,
    build_scheduler_infrastructure,
    build_screening_engine,
    build_screening_repository,
    build_signal_detection_service,
    build_signal_repository,
    build_startup_validation_service,
    build_strategy_repository,
    build_strategy_service,
    build_structured_logger,
    build_trading_calendar_registry,
    build_watchlist_repository,
    build_watchlist_service,
)
from app.core.runtime import AgentRuntime
from app.knowledge.hub import KnowledgeHub
from app.market_data.normalization import NormalizationService
from app.prompts.registry import PromptRegistry
from app.providers.embedding.local import LocalEmbeddingProvider
from app.providers.market_data.mock import MockMarketDataProvider
from app.providers.market_data.yahoo import YahooFinanceProvider
from app.scheduler.ap_scheduler import APSchedulerService
from app.scheduler.scheduler import Scheduler
from app.services.entity_resolution.service import EntityResolutionService
from app.services.llm.service import LLMService
from app.services.market_snapshot.service import MarketSnapshotService
from app.workflows.engine import WorkflowEngine

_LOGGER = logging.getLogger("test.bootstrap")


def _build_test_runtime() -> AgentRuntime:
    settings = AppSettings()
    return AgentRuntime(
        logger=_LOGGER,
        configuration=SettingsConfiguration(settings),
        knowledge_hub=EmptyKnowledgeHub(),
        memory=InProcessMemory(),
        tool_registry=EmptyToolRegistry(),
        event_bus=NoOpEventBus(),
    )


# --- InProcessMemory -----------------------------------------------------------


async def test_in_process_memory_read_write_round_trip() -> None:
    memory = InProcessMemory()
    await memory.write("key", "value")
    assert await memory.read("key") == "value"


async def test_in_process_memory_read_missing_key_returns_none() -> None:
    memory = InProcessMemory()
    assert await memory.read("does-not-exist") is None


# --- EmptyKnowledgeHub / EmptyToolRegistry / NoOpEventBus -----------------------------------------------------------


async def test_empty_knowledge_hub_query_returns_empty_list() -> None:
    hub = EmptyKnowledgeHub()
    assert await hub.query("anything") == []


def test_empty_tool_registry_has_no_tools() -> None:
    registry = EmptyToolRegistry()
    assert registry.list_tools() == ()


def test_empty_tool_registry_raises_for_unknown_tool() -> None:
    registry = EmptyToolRegistry()
    try:
        registry.get_tool("nonexistent")
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError")


async def test_no_op_event_bus_publish_does_not_raise() -> None:
    bus = NoOpEventBus()
    await bus.publish("event", {"data": 1})
    bus.subscribe("event", lambda payload: None)


# --- SettingsConfiguration -----------------------------------------------------------


def test_settings_configuration_returns_setting_value() -> None:
    settings = AppSettings(environment="production")
    config = SettingsConfiguration(settings)
    assert config.get("environment") == "production"


def test_settings_configuration_returns_default_for_unknown_key() -> None:
    settings = AppSettings()
    config = SettingsConfiguration(settings)
    assert config.get("does_not_exist", "fallback") == "fallback"


# --- build_embedding_provider (Milestone 11: LocalEmbeddingProvider) ------------------------------


def test_build_embedding_provider_returns_a_local_provider_by_default() -> None:
    """Milestone 11: `settings.embedding_provider` defaults to `"local"`,
    which constructs a real, concrete LocalEmbeddingProvider — no longer
    the documented gap it used to be."""
    settings = AppSettings()
    provider = build_embedding_provider(settings, _LOGGER)
    assert isinstance(provider, LocalEmbeddingProvider)
    assert provider.config.model == settings.embedding_model


def test_build_embedding_provider_returns_none_for_unrecognized_selector() -> None:
    """`embedding_provider` never crashes startup for a bad config value —
    the same None-when-unconfigured shape every other optional dependency
    in this module uses."""
    settings = AppSettings(embedding_provider="not-a-real-provider")
    assert build_embedding_provider(settings, _LOGGER) is None


# --- build_entity_resolution_service (Milestone 12) -----------------------------------------------------------


def test_build_entity_resolution_service_returns_a_service_by_default() -> None:
    """`entity_resolution_enabled` defaults to True — unlike ingestion,
    entity resolution is a safe, deterministic, in-process enrichment
    with no new scheduled job."""
    settings = AppSettings()
    service = build_entity_resolution_service(settings, _LOGGER)
    assert isinstance(service, EntityResolutionService)


def test_build_entity_resolution_service_returns_none_when_disabled() -> None:
    settings = AppSettings(entity_resolution_enabled=False)
    assert build_entity_resolution_service(settings, _LOGGER) is None


def test_build_entity_resolution_service_returns_none_for_invalid_thresholds() -> None:
    """A bad threshold configuration degrades to None (logged) rather
    than crashing startup — the same shape every other optional
    dependency in this module uses."""
    settings = AppSettings(entity_match_high_threshold=0.1, entity_match_medium_threshold=0.9)
    assert build_entity_resolution_service(settings, _LOGGER) is None


def test_build_entity_resolution_service_returns_none_for_invalid_max_candidates() -> None:
    settings = AppSettings(entity_max_candidates=0)
    assert build_entity_resolution_service(settings, _LOGGER) is None


def test_build_entity_resolution_service_uses_configured_thresholds() -> None:
    """Behavioral check (not reaching into private state): a
    medium_threshold set above what a real company match would score
    means even Apple's own canonical name no longer resolves at all."""
    settings = AppSettings(entity_match_high_threshold=0.999, entity_match_medium_threshold=0.999)
    service = build_entity_resolution_service(settings, _LOGGER)
    assert isinstance(service, EntityResolutionService)
    result = service.resolve("Apple Inc. reported strong earnings.", None)
    assert result.primary is None


# --- build_knowledge_repository (graceful degradation) -----------------------------------------------------------


def test_build_knowledge_repository_does_not_raise() -> None:
    """Whether chromadb is installed/reachable or not, this must never
    raise — it degrades to None instead of crashing startup."""
    settings = AppSettings()
    result = build_knowledge_repository(settings, _LOGGER)
    assert result is None or hasattr(result, "search")


# --- build_news_collector_agent -----------------------------------------------------------


def test_build_news_collector_agent_registers_rss_provider() -> None:
    settings = AppSettings(rss_feed_urls=["https://example.com/feed.xml"])
    runtime = AgentRuntime(
        logger=_LOGGER,
        configuration=SettingsConfiguration(settings),
        knowledge_hub=EmptyKnowledgeHub(),
        memory=InProcessMemory(),
        tool_registry=EmptyToolRegistry(),
        event_bus=NoOpEventBus(),
    )

    agent = build_news_collector_agent(runtime, settings)

    assert agent.agent_id == "AGT-003"


async def test_build_news_collector_agent_health_check_true_with_default_config() -> None:
    """NewsCollectorAgent.health_check() reflects whether any provider
    *config* is enabled (default True) — a coarser, agent-level signal
    that holds regardless of feed_urls being empty or populated. The
    feed_urls value itself is exercised directly against RSSProviderConfig
    in Sprint 10's own test suite."""
    settings = AppSettings(rss_feed_urls=[])
    runtime = AgentRuntime(
        logger=_LOGGER,
        configuration=SettingsConfiguration(settings),
        knowledge_hub=EmptyKnowledgeHub(),
        memory=InProcessMemory(),
        tool_registry=EmptyToolRegistry(),
        event_bus=NoOpEventBus(),
    )

    agent = build_news_collector_agent(runtime, settings)

    assert await agent.health_check() is True


# --- build_scheduler_infrastructure -----------------------------------------------------------


def test_build_scheduler_infrastructure_returns_the_full_chain_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SCHEDULER_ENABLED", raising=False)

    workflow_engine, scheduler, ap_scheduler_service = build_scheduler_infrastructure(_LOGGER)

    assert isinstance(workflow_engine, WorkflowEngine)
    assert isinstance(scheduler, Scheduler)
    assert isinstance(ap_scheduler_service, APSchedulerService)


def test_build_scheduler_infrastructure_respects_scheduler_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")

    _workflow_engine, scheduler, ap_scheduler_service = build_scheduler_infrastructure(_LOGGER)

    assert ap_scheduler_service is None
    assert isinstance(scheduler, Scheduler)  # Scheduler itself is still usable directly


def test_build_scheduler_infrastructure_does_not_require_anthropic_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SchedulerSettings is read standalone, not through the full
    ConfigurationService/AppConfig — which would otherwise fail here since
    AnthropicSettings.api_key is required and unset in this test env."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    _workflow_engine, _scheduler, ap_scheduler_service = build_scheduler_infrastructure(_LOGGER)

    assert ap_scheduler_service is not None


# --- build_watchlist_repository / build_watchlist_service -----------------------------------------------------------


def test_build_watchlist_repository_does_not_raise() -> None:
    """`create_async_engine` never opens a connection eagerly, so this
    always succeeds for a syntactically valid URL, regardless of whether a
    PostgreSQL server is actually reachable."""
    result = build_watchlist_repository(_LOGGER)
    assert result is None or hasattr(result, "create_watchlist")


def test_build_watchlist_repository_does_not_require_anthropic_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PostgreSQLSettings is read standalone, not through the full
    ConfigurationService/AppConfig — same reasoning as the scheduler
    infrastructure builder above."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = build_watchlist_repository(_LOGGER)

    assert result is not None


def test_build_watchlist_service_returns_none_without_a_repository() -> None:
    settings = AppSettings()
    assert build_watchlist_service(None, settings) is None


def test_build_watchlist_service_wires_the_configured_max_size() -> None:
    settings = AppSettings(watchlist_max_size=42)
    repository = build_watchlist_repository(_LOGGER)

    service = build_watchlist_service(repository, settings)

    assert service is not None
    assert service._max_watchlist_size == 42


# --- build_screening_repository / build_screening_engine -----------------------------------------------------------


def test_build_screening_repository_does_not_raise() -> None:
    """`create_async_engine` never opens a connection eagerly, so this
    always succeeds for a syntactically valid URL, regardless of whether a
    PostgreSQL server is actually reachable."""
    result = build_screening_repository(_LOGGER)
    assert result is None or hasattr(result, "create_profile")


def test_build_screening_repository_does_not_require_anthropic_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = build_screening_repository(_LOGGER)

    assert result is not None


def test_build_screening_engine_returns_none_without_a_repository() -> None:
    settings = AppSettings()
    assert build_screening_engine(None, settings) is None


def test_build_screening_engine_wires_the_configured_max_filters() -> None:
    settings = AppSettings(screening_max_filters=7)
    repository = build_screening_repository(_LOGGER)

    engine = build_screening_engine(repository, settings)

    assert engine is not None
    assert engine._max_filters == 7


# --- build_market_data_provider / build_normalization_service -------------------------------------


def test_build_market_data_provider_returns_a_mock_provider_by_default() -> None:
    """Never None: MockMarketDataProvider has no external dependency that
    can fail, unlike the database-backed repositories above. Default
    MARKET_DATA_PROVIDER="mock" preserves pre-Milestone-13 behavior."""
    provider, is_live = build_market_data_provider(AppSettings(), _LOGGER)
    assert isinstance(provider, MockMarketDataProvider)
    assert is_live is False


def test_build_market_data_provider_returns_a_fresh_instance_each_call() -> None:
    first, _ = build_market_data_provider(AppSettings(), _LOGGER)
    second, _ = build_market_data_provider(AppSettings(), _LOGGER)
    assert first is not second


def test_build_market_data_provider_returns_yahoo_finance_when_selected() -> None:
    """Milestone 13: a real, non-mock provider is now selectable."""
    settings = AppSettings(market_data_provider="yahoo_finance")
    provider, is_live = build_market_data_provider(settings, _LOGGER)
    assert isinstance(provider, YahooFinanceProvider)
    assert is_live is True


def test_build_market_data_provider_falls_back_to_mock_for_unrecognized_selector() -> None:
    settings = AppSettings(market_data_provider="not-a-real-provider")
    provider, is_live = build_market_data_provider(settings, _LOGGER)
    assert isinstance(provider, MockMarketDataProvider)
    assert is_live is False


def test_build_market_snapshot_service_always_succeeds() -> None:
    settings = AppSettings()
    provider, _ = build_market_data_provider(settings, _LOGGER)
    service = build_market_snapshot_service(provider, None, settings)
    assert isinstance(service, MarketSnapshotService)


def test_build_normalization_service_returns_a_service() -> None:
    service = build_normalization_service()
    assert isinstance(service, NormalizationService)


# --- build_signal_repository / build_signal_detection_service -------------------------------------


def test_build_signal_repository_does_not_raise() -> None:
    """`create_async_engine` never opens a connection eagerly, so this
    always succeeds for a syntactically valid URL, regardless of whether a
    PostgreSQL server is actually reachable."""
    result = build_signal_repository(_LOGGER)
    assert result is None or hasattr(result, "create_signal_definition")


def test_build_signal_repository_does_not_require_anthropic_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = build_signal_repository(_LOGGER)

    assert result is not None


def test_build_signal_detection_service_returns_none_without_a_repository() -> None:
    settings = AppSettings()
    assert build_signal_detection_service(None, settings) is None


def test_build_signal_detection_service_wires_the_configured_max_conditions() -> None:
    settings = AppSettings(signal_max_conditions=9)
    repository = build_signal_repository(_LOGGER)

    service = build_signal_detection_service(repository, settings)

    assert service is not None
    assert service._max_conditions == 9


# --- build_alert_rule_repository / build_alert_repository / build_alert_service -------------------


def test_build_alert_rule_repository_does_not_raise() -> None:
    result = build_alert_rule_repository(_LOGGER)
    assert result is None or hasattr(result, "create_rule")


def test_build_alert_rule_repository_does_not_require_anthropic_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = build_alert_rule_repository(_LOGGER)

    assert result is not None


def test_build_alert_repository_does_not_raise() -> None:
    result = build_alert_repository(_LOGGER)
    assert result is None or hasattr(result, "create_alert")


def test_build_alert_repository_does_not_require_anthropic_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = build_alert_repository(_LOGGER)

    assert result is not None


def test_build_alert_service_returns_none_without_either_repository() -> None:
    settings = AppSettings()
    rule_repository = build_alert_rule_repository(_LOGGER)
    alert_repository = build_alert_repository(_LOGGER)

    assert build_alert_service(None, alert_repository, settings) is None
    assert build_alert_service(rule_repository, None, settings) is None
    assert build_alert_service(None, None, settings) is None


def test_build_alert_service_wires_the_configured_max_rules() -> None:
    settings = AppSettings(alert_max_rules=13)
    rule_repository = build_alert_rule_repository(_LOGGER)
    alert_repository = build_alert_repository(_LOGGER)

    service = build_alert_service(rule_repository, alert_repository, settings)

    assert service is not None
    assert service._max_rules == 13


# --- build_recommendation_repository / build_recommendation_service -------------------------------


def test_build_recommendation_repository_does_not_raise() -> None:
    """`create_async_engine` never opens a connection eagerly, so this
    always succeeds for a syntactically valid URL, regardless of whether a
    PostgreSQL server is actually reachable."""
    result = build_recommendation_repository(_LOGGER)
    assert result is None or hasattr(result, "create_request")


def test_build_recommendation_repository_does_not_require_anthropic_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = build_recommendation_repository(_LOGGER)

    assert result is not None


def test_build_recommendation_service_returns_none_without_a_repository() -> None:
    assert build_recommendation_service(None) is None


def test_build_recommendation_service_returns_a_service_when_repository_is_available() -> None:
    repository = build_recommendation_repository(_LOGGER)

    service = build_recommendation_service(repository)

    assert service is not None


# --- build_strategy_repository / build_strategy_service -----------------------------------------------------------


def test_build_strategy_repository_does_not_raise() -> None:
    """`create_async_engine` never opens a connection eagerly, so this
    always succeeds for a syntactically valid URL, regardless of whether a
    PostgreSQL server is actually reachable."""
    result = build_strategy_repository(_LOGGER)
    assert result is None or hasattr(result, "create_strategy")


def test_build_strategy_repository_does_not_require_anthropic_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = build_strategy_repository(_LOGGER)

    assert result is not None


def test_build_strategy_service_returns_none_without_a_repository() -> None:
    assert build_strategy_service(None) is None


def test_build_strategy_service_returns_a_service_when_repository_is_available() -> None:
    repository = build_strategy_repository(_LOGGER)

    service = build_strategy_service(repository)

    assert service is not None


# --- build_risk_repository / build_risk_service -----------------------------------------------------------


def test_build_risk_repository_does_not_raise() -> None:
    """`create_async_engine` never opens a connection eagerly, so this
    always succeeds for a syntactically valid URL, regardless of whether a
    PostgreSQL server is actually reachable."""
    result = build_risk_repository(_LOGGER)
    assert result is None or hasattr(result, "create_request")


def test_build_risk_repository_does_not_require_anthropic_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = build_risk_repository(_LOGGER)

    assert result is not None


def test_build_risk_service_returns_none_without_a_repository() -> None:
    assert build_risk_service(None) is None


def test_build_risk_service_returns_a_service_when_repository_is_available() -> None:
    repository = build_risk_repository(_LOGGER)

    service = build_risk_service(repository)

    assert service is not None


# --- build_initial_analysis_service -----------------------------------------------------------


def _build_full_initial_analysis_dependencies():
    settings = AppSettings()
    watchlist_service = build_watchlist_service(build_watchlist_repository(_LOGGER), settings)
    signal_detection_service = build_signal_detection_service(build_signal_repository(_LOGGER), settings)
    alert_service = build_alert_service(build_alert_rule_repository(_LOGGER), build_alert_repository(_LOGGER), settings)
    recommendation_service = build_recommendation_service(build_recommendation_repository(_LOGGER))
    risk_service = build_risk_service(build_risk_repository(_LOGGER))
    market_data_provider, _ = build_market_data_provider(settings, _LOGGER)
    entity_resolution_service = build_entity_resolution_service(settings, _LOGGER)
    market_snapshot_service = build_market_snapshot_service(market_data_provider, entity_resolution_service, settings)
    portfolio_market_snapshot_service = build_portfolio_market_snapshot_service(
        market_snapshot_service, entity_resolution_service
    )
    return (
        watchlist_service,
        portfolio_market_snapshot_service,
        signal_detection_service,
        alert_service,
        recommendation_service,
        risk_service,
    )


def test_build_initial_analysis_service_returns_none_without_watchlist_service() -> None:
    (
        _watchlist_service,
        portfolio_market_snapshot_service,
        signal_detection_service,
        alert_service,
        recommendation_service,
        risk_service,
    ) = _build_full_initial_analysis_dependencies()

    result = build_initial_analysis_service(
        watchlist_service=None,
        portfolio_market_snapshot_service=portfolio_market_snapshot_service,
        signal_detection_service=signal_detection_service,
        alert_service=alert_service,
        recommendation_service=recommendation_service,
        risk_service=risk_service,
    )

    assert result is None


def test_build_initial_analysis_service_returns_a_service_when_every_dependency_is_available() -> None:
    (
        watchlist_service,
        portfolio_market_snapshot_service,
        signal_detection_service,
        alert_service,
        recommendation_service,
        risk_service,
    ) = _build_full_initial_analysis_dependencies()

    service = build_initial_analysis_service(
        watchlist_service=watchlist_service,
        portfolio_market_snapshot_service=portfolio_market_snapshot_service,
        signal_detection_service=signal_detection_service,
        alert_service=alert_service,
        recommendation_service=recommendation_service,
        risk_service=risk_service,
    )

    assert service is not None


# --- build_backtesting_repository / build_backtesting_service -------------------------------------


def test_build_backtesting_repository_does_not_raise() -> None:
    """`create_async_engine` never opens a connection eagerly, so this
    always succeeds for a syntactically valid URL, regardless of whether a
    PostgreSQL server is actually reachable."""
    result = build_backtesting_repository(_LOGGER)
    assert result is None or hasattr(result, "create_request")


def test_build_backtesting_repository_does_not_require_anthropic_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = build_backtesting_repository(_LOGGER)

    assert result is not None


def _build_dependent_services():
    recommendation_service = build_recommendation_service(build_recommendation_repository(_LOGGER))
    strategy_service = build_strategy_service(build_strategy_repository(_LOGGER))
    risk_service = build_risk_service(build_risk_repository(_LOGGER))
    return recommendation_service, strategy_service, risk_service


def test_build_backtesting_service_returns_none_without_a_repository() -> None:
    recommendation_service, strategy_service, risk_service = _build_dependent_services()

    result = build_backtesting_service(None, recommendation_service, strategy_service, risk_service)

    assert result is None


def test_build_backtesting_service_returns_none_without_a_recommendation_service() -> None:
    repository = build_backtesting_repository(_LOGGER)
    _, strategy_service, risk_service = _build_dependent_services()

    result = build_backtesting_service(repository, None, strategy_service, risk_service)

    assert result is None


def test_build_backtesting_service_returns_none_without_a_strategy_service() -> None:
    repository = build_backtesting_repository(_LOGGER)
    recommendation_service, _, risk_service = _build_dependent_services()

    result = build_backtesting_service(repository, recommendation_service, None, risk_service)

    assert result is None


def test_build_backtesting_service_returns_none_without_a_risk_service() -> None:
    repository = build_backtesting_repository(_LOGGER)
    recommendation_service, strategy_service, _ = _build_dependent_services()

    result = build_backtesting_service(repository, recommendation_service, strategy_service, None)

    assert result is None


def test_build_backtesting_service_returns_a_service_when_every_dependency_is_available() -> None:
    repository = build_backtesting_repository(_LOGGER)
    recommendation_service, strategy_service, risk_service = _build_dependent_services()

    service = build_backtesting_service(repository, recommendation_service, strategy_service, risk_service)

    assert service is not None


# --- build_explainability_repository / build_explainability_service -------------------------------


def test_build_explainability_repository_does_not_raise() -> None:
    """`create_async_engine` never opens a connection eagerly, so this
    always succeeds for a syntactically valid URL, regardless of whether a
    PostgreSQL server is actually reachable."""
    result = build_explainability_repository(_LOGGER)
    assert result is None or hasattr(result, "create_request")


def test_build_explainability_repository_does_not_require_anthropic_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = build_explainability_repository(_LOGGER)

    assert result is not None


def _build_explainability_dependent_services():
    recommendation_service, strategy_service, risk_service = _build_dependent_services()
    backtesting_repository = build_backtesting_repository(_LOGGER)
    backtesting_service = build_backtesting_service(
        backtesting_repository, recommendation_service, strategy_service, risk_service
    )
    return recommendation_service, strategy_service, risk_service, backtesting_service


def test_build_explainability_service_returns_none_without_a_repository() -> None:
    recommendation_service, strategy_service, risk_service, backtesting_service = (
        _build_explainability_dependent_services()
    )

    result = build_explainability_service(
        None, recommendation_service, strategy_service, risk_service, backtesting_service
    )

    assert result is None


def test_build_explainability_service_returns_none_without_a_recommendation_service() -> None:
    repository = build_explainability_repository(_LOGGER)
    _, strategy_service, risk_service, backtesting_service = _build_explainability_dependent_services()

    result = build_explainability_service(repository, None, strategy_service, risk_service, backtesting_service)

    assert result is None


def test_build_explainability_service_returns_none_without_a_strategy_service() -> None:
    repository = build_explainability_repository(_LOGGER)
    recommendation_service, _, risk_service, backtesting_service = _build_explainability_dependent_services()

    result = build_explainability_service(repository, recommendation_service, None, risk_service, backtesting_service)

    assert result is None


def test_build_explainability_service_returns_none_without_a_risk_service() -> None:
    repository = build_explainability_repository(_LOGGER)
    recommendation_service, strategy_service, _, backtesting_service = _build_explainability_dependent_services()

    result = build_explainability_service(
        repository, recommendation_service, strategy_service, None, backtesting_service
    )

    assert result is None


def test_build_explainability_service_returns_none_without_a_backtesting_service() -> None:
    repository = build_explainability_repository(_LOGGER)
    recommendation_service, strategy_service, risk_service, _ = _build_explainability_dependent_services()

    result = build_explainability_service(repository, recommendation_service, strategy_service, risk_service, None)

    assert result is None


def test_build_explainability_service_returns_a_service_when_every_dependency_is_available() -> None:
    repository = build_explainability_repository(_LOGGER)
    recommendation_service, strategy_service, risk_service, backtesting_service = (
        _build_explainability_dependent_services()
    )

    service = build_explainability_service(
        repository, recommendation_service, strategy_service, risk_service, backtesting_service
    )

    assert service is not None


# --- build_structured_logger / build_metrics_recorder / build_profiler ----------------------------


def test_build_structured_logger_wraps_the_given_logger() -> None:
    from app.operations.logging.logger import StdlibStructuredLogger

    result = build_structured_logger(_LOGGER)

    assert isinstance(result, StdlibStructuredLogger)


def test_build_metrics_recorder_returns_an_in_memory_recorder() -> None:
    from app.operations.metrics.recorder import InMemoryMetricsRecorder

    result = build_metrics_recorder()

    assert isinstance(result, InMemoryMetricsRecorder)


def test_build_profiler_returns_an_in_memory_profiler() -> None:
    from app.operations.profiling.profiler import InMemoryProfiler

    result = build_profiler()

    assert isinstance(result, InMemoryProfiler)


# --- build_health_check_service / build_configuration_validation_service / build_startup_validation_service ---


def test_build_health_check_service_returns_a_service() -> None:
    result = build_health_check_service()

    assert result is not None


def test_build_configuration_validation_service_returns_a_service() -> None:
    result = build_configuration_validation_service()

    assert result is not None


def test_build_startup_validation_service_composes_the_configuration_service() -> None:
    configuration_service = build_configuration_validation_service()

    result = build_startup_validation_service(configuration_service)

    assert result is not None


# --- build_auth_repository / build_clock / build_password_hasher / build_jwt_signer ---------------


def test_build_auth_repository_does_not_raise() -> None:
    """`create_async_engine` never opens a connection eagerly, so this
    always succeeds for a syntactically valid URL, regardless of whether a
    PostgreSQL server is actually reachable."""
    result = build_auth_repository(_LOGGER)
    assert result is None or hasattr(result, "create_user")


def test_build_auth_repository_does_not_require_anthropic_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = build_auth_repository(_LOGGER)

    assert result is not None


def test_build_clock_returns_a_clock() -> None:
    from app.auth.security.clock import SystemClock

    assert isinstance(build_clock(), SystemClock)


def test_build_password_hasher_returns_a_hasher() -> None:
    from app.auth.security.password_hashing import Pbkdf2PasswordHasher

    assert isinstance(build_password_hasher(), Pbkdf2PasswordHasher)


def test_build_jwt_signer_does_not_require_a_real_secret() -> None:
    from app.config.models import AuthSettings

    signer = build_jwt_signer(AuthSettings())

    token = signer.encode({"sub": "x"})
    assert signer.decode(token) == {"sub": "x"}


# --- build_authorization_service / build_authentication_provider /
# build_authentication_service / build_policy_evaluator ---


def test_build_authorization_service_returns_none_without_a_repository() -> None:
    assert build_authorization_service(None) is None


def test_build_authorization_service_returns_a_service_when_repository_is_available() -> None:
    repository = build_auth_repository(_LOGGER)

    service = build_authorization_service(repository)

    assert service is not None


def _build_auth_provider_dependencies():
    from app.config.models import AuthSettings

    repository = build_auth_repository(_LOGGER)
    authorization_service = build_authorization_service(repository)
    jwt_signer = build_jwt_signer(AuthSettings())
    password_hasher = build_password_hasher()
    clock = build_clock()
    return repository, authorization_service, jwt_signer, password_hasher, clock, AuthSettings()


def test_build_authentication_provider_returns_none_without_a_repository() -> None:
    _, authorization_service, jwt_signer, password_hasher, clock, settings = _build_auth_provider_dependencies()

    result = build_authentication_provider(None, authorization_service, jwt_signer, password_hasher, clock, settings)

    assert result is None


def test_build_authentication_provider_returns_none_without_an_authorization_service() -> None:
    repository, _, jwt_signer, password_hasher, clock, settings = _build_auth_provider_dependencies()

    result = build_authentication_provider(repository, None, jwt_signer, password_hasher, clock, settings)

    assert result is None


def test_build_authentication_provider_returns_a_provider_when_available() -> None:
    repository, authorization_service, jwt_signer, password_hasher, clock, settings = (
        _build_auth_provider_dependencies()
    )

    provider = build_authentication_provider(
        repository, authorization_service, jwt_signer, password_hasher, clock, settings
    )

    assert provider is not None
    assert provider.provider_name() == "jwt"


def test_build_authentication_service_returns_none_without_a_provider() -> None:
    repository, _, _, password_hasher, _, _ = _build_auth_provider_dependencies()

    result = build_authentication_service(None, repository, password_hasher)

    assert result is None


def test_build_authentication_service_returns_none_without_a_repository() -> None:
    repository, authorization_service, jwt_signer, password_hasher, clock, settings = (
        _build_auth_provider_dependencies()
    )
    provider = build_authentication_provider(
        repository, authorization_service, jwt_signer, password_hasher, clock, settings
    )

    result = build_authentication_service(provider, None, password_hasher)

    assert result is None


def test_build_authentication_service_returns_a_service_when_available() -> None:
    repository, authorization_service, jwt_signer, password_hasher, clock, settings = (
        _build_auth_provider_dependencies()
    )
    provider = build_authentication_provider(
        repository, authorization_service, jwt_signer, password_hasher, clock, settings
    )

    service = build_authentication_service(provider, repository, password_hasher)

    assert service is not None


def test_build_policy_evaluator_returns_an_evaluator() -> None:
    from app.auth.policies import PolicyEvaluator

    assert isinstance(build_policy_evaluator(), PolicyEvaluator)


# --- build_prompt_registry / build_knowledge_hub / build_llm_service / agent builders (Sprint 57) --


def test_build_prompt_registry_registers_every_agent_template() -> None:
    registry = build_prompt_registry()

    assert isinstance(registry, PromptRegistry)
    assert registry.get("company_research").template_id == "company_research"
    assert registry.get("portfolio_intelligence").template_id == "portfolio_intelligence"


class _FakeKnowledgeRepository:
    """A minimal duck-typed stand-in for `BaseKnowledgeRepository` — avoids
    depending on chromadb actually being installed in the test environment."""

    async def search(self, query: object) -> list:
        return []

    async def get(self, record_id: str) -> None:
        return None


def test_build_knowledge_hub_returns_none_without_a_repository() -> None:
    assert build_knowledge_hub(None) is None


def test_build_knowledge_hub_wraps_a_repository() -> None:
    hub = build_knowledge_hub(_FakeKnowledgeRepository())

    assert isinstance(hub, KnowledgeHub)


def test_build_llm_service_returns_none_without_anthropic_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """`AnthropicSettings.api_key` is required with no default, so
    constructing it fails without `ANTHROPIC_API_KEY` set — that failure
    must degrade to None, not crash startup."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    assert build_llm_service(_LOGGER) is None


def test_build_llm_service_returns_a_service_with_anthropic_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")

    service = build_llm_service(_LOGGER)

    assert isinstance(service, LLMService)


def test_build_company_research_agent_returns_none_without_knowledge_hub() -> None:
    runtime = _build_test_runtime()
    registry = build_prompt_registry()

    result = build_company_research_agent(runtime, None, None, registry, None)

    assert result is None


def test_build_company_research_agent_returns_none_without_llm_service() -> None:
    runtime = _build_test_runtime()
    registry = build_prompt_registry()
    hub = build_knowledge_hub(_FakeKnowledgeRepository())

    result = build_company_research_agent(runtime, hub, None, registry, None)

    assert result is None


def test_build_company_research_agent_returns_an_agent_when_dependencies_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    runtime = _build_test_runtime()
    registry = build_prompt_registry()
    hub = build_knowledge_hub(_FakeKnowledgeRepository())
    llm_service = build_llm_service(_LOGGER)

    agent = build_company_research_agent(runtime, hub, llm_service, registry, None)

    assert isinstance(agent, CompanyResearchAgent)


def test_build_portfolio_intelligence_agent_returns_none_without_company_research_agent() -> None:
    runtime = _build_test_runtime()
    registry = build_prompt_registry()
    hub = build_knowledge_hub(_FakeKnowledgeRepository())

    result = build_portfolio_intelligence_agent(runtime, hub, None, registry, None)

    assert result is None


def test_build_portfolio_intelligence_agent_returns_an_agent_when_dependencies_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    runtime = _build_test_runtime()
    registry = build_prompt_registry()
    hub = build_knowledge_hub(_FakeKnowledgeRepository())
    llm_service = build_llm_service(_LOGGER)
    company_research_agent = build_company_research_agent(runtime, hub, llm_service, registry, None)

    agent = build_portfolio_intelligence_agent(runtime, hub, llm_service, registry, company_research_agent)

    assert isinstance(agent, PortfolioIntelligenceAgent)


# --- Global Market Intelligence (Phase 1) -----------------------------------------------------------


def test_build_trading_calendar_registry_covers_every_market_region() -> None:
    from app.global_markets.models import MarketRegion

    registry = build_trading_calendar_registry()

    assert set(registry.supported_regions()) == set(MarketRegion)


def test_build_global_market_session_resolver_returns_a_resolver() -> None:
    from app.global_markets.session.resolver import MarketSessionResolutionService

    registry = build_trading_calendar_registry()

    resolver = build_global_market_session_resolver(registry)

    assert isinstance(resolver, MarketSessionResolutionService)


def test_build_global_market_run_repository_does_not_raise() -> None:
    """`create_async_engine` never opens a connection eagerly, so this
    always succeeds for a syntactically valid URL, regardless of whether a
    PostgreSQL server is actually reachable."""
    result = build_global_market_run_repository(_LOGGER)
    assert result is None or hasattr(result, "create_run")


def test_build_global_market_intelligence_workflow_always_returns_a_workflow() -> None:
    from app.workflows.global_markets.pipeline import GlobalMarketIntelligenceWorkflow

    registry = build_trading_calendar_registry()
    resolver = build_global_market_session_resolver(registry)

    workflow = build_global_market_intelligence_workflow(resolver, None)

    assert isinstance(workflow, GlobalMarketIntelligenceWorkflow)


# --- Global Market Intelligence (Phase 2) -----------------------------------------------------------


def test_build_global_market_universe_registry_covers_every_report_category() -> None:
    from app.global_markets.models import ReportCategory
    from app.global_markets.universe.registry import UniverseRegistry

    registry = build_global_market_universe_registry()

    assert isinstance(registry, UniverseRegistry)
    assert registry.get(ReportCategory.US_EQUITY) != ()


def test_build_global_market_category_pipeline_returns_a_pipeline() -> None:
    from app.global_markets.pipeline.category_pipeline import CategoryDataPipeline
    from app.providers.market_data.mock import MockMarketDataProvider

    pipeline = build_global_market_category_pipeline(MockMarketDataProvider())

    assert isinstance(pipeline, CategoryDataPipeline)


def test_build_global_market_ranked_asset_repository_does_not_raise() -> None:
    """`create_async_engine` never opens a connection eagerly, so this
    always succeeds for a syntactically valid URL, regardless of whether a
    PostgreSQL server is actually reachable."""
    result = build_global_market_ranked_asset_repository(_LOGGER)
    assert result is None or hasattr(result, "replace_ranked_assets")


def test_build_global_market_intelligence_workflow_accepts_phase_2_and_3_dependencies() -> None:
    from app.global_markets.pipeline.category_pipeline import CategoryDataPipeline
    from app.providers.market_data.mock import MockMarketDataProvider
    from app.workflows.global_markets.pipeline import GlobalMarketIntelligenceWorkflow

    registry = build_trading_calendar_registry()
    resolver = build_global_market_session_resolver(registry)
    pipeline = CategoryDataPipeline(MockMarketDataProvider())
    universe_registry = build_global_market_universe_registry()

    workflow = build_global_market_intelligence_workflow(
        resolver,
        None,
        category_pipeline=pipeline,
        universe_registry=universe_registry,
        ranked_asset_repository=None,
    )

    assert isinstance(workflow, GlobalMarketIntelligenceWorkflow)


# --- Global Market Intelligence (Phase 3) -----------------------------------------------------------


def test_build_global_markets_research_agent_returns_none_without_llm_service() -> None:
    runtime = _build_test_runtime()
    registry = build_prompt_registry()

    result = build_global_markets_research_agent(runtime, None, registry)

    assert result is None


def test_build_global_markets_research_agent_returns_an_agent_when_dependencies_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.agents.global_markets_research.agent import GlobalMarketsResearchAgent

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    runtime = _build_test_runtime()
    registry = build_prompt_registry()
    llm_service = build_llm_service(_LOGGER)

    agent = build_global_markets_research_agent(runtime, llm_service, registry)

    assert isinstance(agent, GlobalMarketsResearchAgent)


def test_build_penny_microcap_intelligence_agent_returns_none_without_llm_service() -> None:
    runtime = _build_test_runtime()
    registry = build_prompt_registry()

    result = build_penny_microcap_intelligence_agent(runtime, None, registry)

    assert result is None


def test_build_penny_microcap_intelligence_agent_returns_an_agent_when_dependencies_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.agents.penny_microcap_intelligence.agent import PennyMicrocapIntelligenceAgent

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    runtime = _build_test_runtime()
    registry = build_prompt_registry()
    llm_service = build_llm_service(_LOGGER)

    agent = build_penny_microcap_intelligence_agent(runtime, llm_service, registry)

    assert isinstance(agent, PennyMicrocapIntelligenceAgent)


def test_build_global_market_report_repository_does_not_raise() -> None:
    """`create_async_engine` never opens a connection eagerly, so this
    always succeeds for a syntactically valid URL, regardless of whether a
    PostgreSQL server is actually reachable."""
    result = build_global_market_report_repository(_LOGGER)
    assert result is None or hasattr(result, "save_report")


def test_build_global_market_intelligence_workflow_accepts_phase_3_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.global_markets.pipeline.category_pipeline import CategoryDataPipeline
    from app.providers.market_data.mock import MockMarketDataProvider
    from app.workflows.global_markets.pipeline import GlobalMarketIntelligenceWorkflow

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    registry = build_trading_calendar_registry()
    resolver = build_global_market_session_resolver(registry)
    pipeline = CategoryDataPipeline(MockMarketDataProvider())
    universe_registry = build_global_market_universe_registry()
    runtime = _build_test_runtime()
    prompt_registry = build_prompt_registry()
    llm_service = build_llm_service(_LOGGER)
    research_agent = build_global_markets_research_agent(runtime, llm_service, prompt_registry)
    penny_agent = build_penny_microcap_intelligence_agent(runtime, llm_service, prompt_registry)

    workflow = build_global_market_intelligence_workflow(
        resolver,
        None,
        category_pipeline=pipeline,
        universe_registry=universe_registry,
        ranked_asset_repository=None,
        research_agent=research_agent,
        penny_microcap_agent=penny_agent,
        report_repository=None,
    )

    assert isinstance(workflow, GlobalMarketIntelligenceWorkflow)


# --- Global Market Intelligence (Phase 5) -----------------------------------------------------------


def test_build_global_market_intelligence_workflow_accepts_an_event_publisher() -> None:
    from app.api.ws.connection_manager.manager import ConnectionManager
    from app.api.ws.publishers.event_publisher import EventPublisher
    from app.workflows.global_markets.pipeline import GlobalMarketIntelligenceWorkflow

    registry = build_trading_calendar_registry()
    resolver = build_global_market_session_resolver(registry)
    event_publisher = EventPublisher(ConnectionManager())

    workflow = build_global_market_intelligence_workflow(resolver, None, event_publisher=event_publisher)

    assert isinstance(workflow, GlobalMarketIntelligenceWorkflow)
