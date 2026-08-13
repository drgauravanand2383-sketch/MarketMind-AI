"""Application Bootstrap — the composition root for MarketMind AI.

This module constructs every injectable component and populates
`app.state` with them. No business logic, no agent logic, and no API
logic is implemented here — only composition:

- Where a concrete implementation already exists (RSSProvider, ChromaDB
  when reachable, and the Scheduler/APScheduler infrastructure), it is
  wired for real.
- Where no concrete implementation has been built yet (MemoryInterface,
  KnowledgeHubInterface, ToolRegistryInterface, EventBusInterface, and
  BaseEmbeddingProvider), a minimal, clearly-labeled, non-persistent
  default is used instead — never a stand-in for real business/AI logic.

Infrastructure that is genuinely unavailable (ChromaDB unreachable, no
embedding provider implementation) degrades to `None` rather than
crashing startup; the API's own dependency layer (Sprint 23) already
returns 503 for callers when a component is unset.

Sprint 35 note: no workflow is registered into the WorkflowEngine built
here. `MorningBriefWorkflow` needs a real `CompositeKnowledgeRepository`,
a real `KnowledgeHub`, and the reasoning engines wired together, and
`MorningPipeline` needs a real (non-None) `BaseEmbeddingProvider` — neither
dependency chain is built by this composition root yet (see
`build_embedding_provider`'s own docstring). The Scheduler/APScheduler
infrastructure is fully wired and started regardless, simply with zero
schedules registered, ready for a future sprint to register a workflow and
a Schedule for it once those dependency chains exist.
"""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from fastapi import FastAPI
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agents.company_research.agent import CompanyResearchAgent
from app.agents.company_research.prompts import register_company_research_prompts
from app.agents.news_collector.agent import NewsCollectorAgent
from app.agents.portfolio_intelligence.agent import PortfolioIntelligenceAgent
from app.agents.portfolio_intelligence.prompts import register_portfolio_intelligence_prompts
from app.auth.policies.evaluator import PolicyEvaluator
from app.auth.providers.jwt import JwtAuthenticationProvider
from app.auth.providers.provider import AuthenticationProvider
from app.auth.repositories.postgres.repository import PostgresAuthRepository
from app.auth.repositories.repository import BaseAuthRepository
from app.auth.security.clock import BaseClock, SystemClock
from app.auth.security.jwt_signer import BaseJWTSigner, HmacJWTSigner
from app.auth.security.password_hashing import BasePasswordHasher, Pbkdf2PasswordHasher
from app.auth.security.secrets_loader import load_jwt_secret
from app.auth.services.authentication import AuthenticationService
from app.auth.services.authorization import AuthorizationService
from app.backtesting.engine import BacktestingService
from app.config.models import (
    AnthropicSettings,
    APISettings,
    AppConfig,
    AuthSettings,
    LLMSettings,
    LoggingSettings,
    PostgreSQLSettings,
    RSSSettings,
    SchedulerSettings,
)
from app.config.service import ConfigurationService
from app.core.runtime import AgentRuntime
from app.knowledge.hub import KnowledgeHub
from app.market_data.normalization import NormalizationService
from app.prompts.registry import PromptRegistry
from app.providers.anthropic.models import AnthropicProviderConfig
from app.providers.anthropic.provider import AnthropicProvider
from app.providers.embedding.provider import BaseEmbeddingProvider
from app.providers.market_data.mock import MockMarketDataProvider
from app.providers.market_data.provider import MarketDataProvider
from app.providers.models import ProviderConfig
from app.providers.registry import ProviderRegistry
from app.providers.rss.models import RSSProviderConfig
from app.providers.rss.provider import RSSProvider
from app.services.llm.service import LLMService
from app.alerts.engine import AlertService
from app.repositories.alerts.postgres.repository import (
    PostgresAlertRepository,
    PostgresAlertRuleRepository,
)
from app.repositories.alerts.repository import BaseAlertRepository, BaseAlertRuleRepository
from app.repositories.backtesting.postgres.repository import PostgresBacktestingRepository
from app.repositories.backtesting.repository import BaseBacktestingRepository
from app.repositories.explainability.postgres.repository import PostgresExplainabilityRepository
from app.repositories.explainability.repository import BaseExplainabilityRepository
from app.explainability.engine import ExplainabilityService
from app.operations.health.service import HealthCheckService
from app.operations.logging.logger import StdlibStructuredLogger
from app.operations.logging.models import LogCategory
from app.operations.metrics.models import METRIC_STARTUP_DURATION_SECONDS
from app.operations.metrics.recorder import InMemoryMetricsRecorder
from app.operations.profiling.profiler import InMemoryProfiler
from app.operations.validation.configuration import ConfigurationValidationService
from app.operations.validation.models import ValidationReport
from app.operations.validation.startup import DEFAULT_REQUIRED_COMPONENTS, StartupValidationService
from app.recommendations.engine import PortfolioRecommendationService
from app.repositories.knowledge.repository import BaseKnowledgeRepository
from app.repositories.recommendations.postgres.repository import PostgresRecommendationRepository
from app.repositories.recommendations.repository import BaseRecommendationRepository
from app.repositories.screening.postgres.repository import PostgresScreeningRepository
from app.repositories.screening.repository import BaseScreeningRepository
from app.repositories.signals.postgres.repository import PostgresSignalDefinitionRepository
from app.repositories.signals.repository import BaseSignalDefinitionRepository
from app.repositories.risk.postgres.repository import PostgresRiskAnalyticsRepository
from app.repositories.risk.repository import BaseRiskAnalyticsRepository
from app.repositories.strategy.postgres.repository import PostgresStrategyRepository
from app.repositories.strategy.repository import BaseStrategyRepository
from app.repositories.watchlist.postgres.repository import PostgresWatchlistRepository
from app.repositories.watchlist.repository import BaseWatchlistRepository
from app.risk.engine import RiskAnalyticsService
from app.scheduler.ap_scheduler import APSchedulerService
from app.scheduler.scheduler import Scheduler
from app.screening.engine import ScreeningEngine
from app.signals.engine import SignalDetectionService
from app.strategy.engine import StrategyEvaluationService
from app.watchlist.service import WatchlistService
from app.workflows.engine import WorkflowEngine

__all__ = [
    "AppSettings",
    "InProcessMemory",
    "EmptyKnowledgeHub",
    "EmptyToolRegistry",
    "NoOpEventBus",
    "SettingsConfiguration",
    "configure_logging",
    "build_knowledge_repository",
    "build_embedding_provider",
    "build_news_collector_agent",
    "build_scheduler_infrastructure",
    "build_watchlist_repository",
    "build_watchlist_service",
    "build_screening_repository",
    "build_screening_engine",
    "build_market_data_provider",
    "build_normalization_service",
    "build_signal_repository",
    "build_signal_detection_service",
    "build_alert_rule_repository",
    "build_alert_repository",
    "build_alert_service",
    "build_recommendation_repository",
    "build_recommendation_service",
    "build_strategy_repository",
    "build_strategy_service",
    "build_risk_repository",
    "build_risk_service",
    "build_backtesting_repository",
    "build_backtesting_service",
    "build_explainability_repository",
    "build_explainability_service",
    "build_structured_logger",
    "build_metrics_recorder",
    "build_profiler",
    "build_health_check_service",
    "build_configuration_validation_service",
    "build_startup_validation_service",
    "build_auth_repository",
    "build_clock",
    "build_password_hasher",
    "build_jwt_signer",
    "build_authorization_service",
    "build_authentication_provider",
    "build_authentication_service",
    "build_policy_evaluator",
    "bootstrap_application_state",
    "shutdown_application_state",
]


class AppSettings(BaseSettings):
    """Application configuration, loaded from environment variables / `.env`."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    log_level: str = "INFO"
    chroma_persist_directory: str = "./data/cache/chroma"
    chroma_collection_name: str = "marketmind_knowledge"
    rss_feed_urls: list[str] = []
    rss_user_agent: str = "MarketMind-AI/1.0"
    watchlist_max_size: int = 500
    screening_max_filters: int = 100
    signal_max_conditions: int = 100
    alert_max_rules: int = 100


class InProcessMemory:
    """Minimal, non-persistent MemoryInterface default.

    State lives only in this process's memory and is lost on restart —
    a development-only placeholder. A Redis-backed implementation is a
    distinct, not-yet-built deliverable (the `memory/` package is still
    empty).
    """

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    async def read(self, key: str) -> Any:
        return self._store.get(key)

    async def write(self, key: str, value: Any) -> None:
        self._store[key] = value


class EmptyKnowledgeHub:
    """A KnowledgeHubInterface default with no backing store.

    Always returns no results. Real domain knowledge retrieval currently
    goes through BaseKnowledgeRepository (search/get), not this
    interface; no concrete KnowledgeHubInterface implementation has been
    built yet.
    """

    async def query(self, query: str, top_k: int = 5) -> list[Any]:
        return []


class EmptyToolRegistry:
    """A ToolRegistryInterface default with no registered tools.

    No agent-callable tools have been built yet (the `tools/` package is
    still empty).
    """

    def get_tool(self, name: str) -> Any:
        raise KeyError(f"No tool registered under {name!r}")

    def list_tools(self) -> tuple[str, ...]:
        return ()


class NoOpEventBus:
    """An EventBusInterface default that delivers nothing.

    No event distribution mechanism (e.g. Redis pub/sub) has been built
    yet.
    """

    async def publish(self, event_name: str, payload: Any) -> None:
        return None

    def subscribe(self, event_name: str, handler: Any) -> None:
        return None


class SettingsConfiguration:
    """A ConfigurationInterface adapter over AppSettings."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self._settings, key, default)


def configure_logging(settings: AppSettings) -> None:
    """Configure root logging level/format from settings. Safe to call more than once."""
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )


def build_knowledge_repository(
    settings: AppSettings, logger: logging.Logger
) -> BaseKnowledgeRepository | None:
    """Attempt to construct a real ChromaDB-backed Knowledge Repository.

    Returns None if chromadb is not installed or fails to initialize —
    the application still starts successfully without a reachable
    ChromaDB; callers hit the API's existing 503 "not configured" path
    instead of a startup crash.
    """
    try:
        import chromadb
    except ImportError:
        logger.warning("chromadb is not installed; knowledge_repository will be unavailable.")
        return None

    try:
        from app.repositories.knowledge.chroma.repository import ChromaKnowledgeRepository

        client = chromadb.PersistentClient(path=settings.chroma_persist_directory)
        collection = client.get_or_create_collection(name=settings.chroma_collection_name)
        return ChromaKnowledgeRepository(collection)
    except Exception as exc:  # noqa: BLE001 - an infrastructure failure must not crash startup
        logger.warning("Failed to initialize ChromaDB knowledge repository: %s", exc)
        return None


def build_embedding_provider(
    settings: AppSettings, logger: logging.Logger
) -> BaseEmbeddingProvider | None:
    """No concrete BaseEmbeddingProvider implementation exists yet.

    Implementing one (a real embedding API call) was explicitly deferred
    when BaseEmbeddingProvider was designed and is out of scope for this
    composition root. Always returns None; callers hit the API's existing
    503 "not configured" path.
    """
    logger.info("No embedding provider implementation is available; embedding_provider is unset.")
    return None


def build_news_collector_agent(
    runtime: AgentRuntime, settings: AppSettings
) -> NewsCollectorAgent:
    """Construct the News Collector agent with RSSProvider registered.

    If `settings.rss_feed_urls` is empty (the default), the agent is
    still constructed correctly but has no feeds configured to collect
    from — a configuration matter for the deployer, not a startup error.
    """
    registry = ProviderRegistry()
    registry.register("rss", RSSProvider)
    provider_configs: list[ProviderConfig] = [
        RSSProviderConfig(
            provider_id="rss",
            feed_urls=list(settings.rss_feed_urls),
            user_agent=settings.rss_user_agent,
        )
    ]
    return NewsCollectorAgent(
        memory=runtime.memory, registry=registry, provider_configs=provider_configs
    )


def build_prompt_registry() -> PromptRegistry:
    """Build the shared PromptRegistry with every agent's templates registered.

    `PromptRegistry` never scans the filesystem — registration is always an
    explicit function call, so this always succeeds.
    """
    registry = PromptRegistry()
    register_company_research_prompts(registry)
    register_portfolio_intelligence_prompts(registry)
    return registry


def build_knowledge_hub(knowledge_repository: BaseKnowledgeRepository | None) -> KnowledgeHub | None:
    """Wrap the already-built Knowledge Repository for agent consumption.

    `KnowledgeHub` only ever calls `.search()`/`.get()` on its injected
    repository, so it works against any `BaseKnowledgeRepository`
    implementation without building a second repository. Returns None when
    `build_knowledge_repository` itself returned None (e.g. chromadb
    unavailable), mirroring every other agent's None-when-unconfigured guard.
    """
    if knowledge_repository is None:
        return None
    return KnowledgeHub(knowledge_repository)  # type: ignore[arg-type]


def build_llm_service(logger: logging.Logger) -> LLMService | None:
    """Attempt to construct a real Claude-backed LLMService.

    `AnthropicSettings.api_key` has no default, so constructing it fails
    without `ANTHROPIC_API_KEY` set — for the same reason
    `build_scheduler_infrastructure`/`build_watchlist_repository` avoid a
    full `AppConfig` at startup, that failure is caught here rather than
    propagated, so a missing key degrades to no LLM service instead of
    crashing the application. Callers hit the API's existing 503 "not
    configured" path.
    """
    try:
        anthropic_settings = AnthropicSettings()
        llm_settings = LLMSettings()
    except Exception as exc:  # noqa: BLE001 - missing/invalid config must not crash startup
        logger.warning("Anthropic/LLM settings unavailable; llm_service will be unavailable: %s", exc)
        return None

    try:
        configuration = ConfigurationService(AppConfig(anthropic=anthropic_settings, llm=llm_settings))
        provider_config = AnthropicProviderConfig.from_settings(anthropic_settings)
        provider = AnthropicProvider(provider_config)
        return LLMService({"anthropic": provider}, configuration)
    except Exception as exc:  # noqa: BLE001 - an infrastructure failure must not crash startup
        logger.warning("Failed to initialize LLMService: %s", exc)
        return None


def build_company_research_agent(
    runtime: AgentRuntime,
    knowledge_hub: KnowledgeHub | None,
    llm_service: LLMService | None,
    prompt_registry: PromptRegistry,
) -> CompanyResearchAgent | None:
    """Construct the Company Research agent, or None if a dependency is unavailable."""
    if knowledge_hub is None or llm_service is None:
        return None
    return CompanyResearchAgent(
        runtime=runtime,
        knowledge_hub=knowledge_hub,
        llm_service=llm_service,
        prompt_registry=prompt_registry,
    )


def build_portfolio_intelligence_agent(
    runtime: AgentRuntime,
    knowledge_hub: KnowledgeHub | None,
    llm_service: LLMService | None,
    prompt_registry: PromptRegistry,
    company_research_agent: CompanyResearchAgent | None,
) -> PortfolioIntelligenceAgent | None:
    """Construct the Portfolio Intelligence agent, or None if a dependency is unavailable."""
    if knowledge_hub is None or llm_service is None or company_research_agent is None:
        return None
    return PortfolioIntelligenceAgent(
        runtime=runtime,
        knowledge_hub=knowledge_hub,
        llm_service=llm_service,
        prompt_registry=prompt_registry,
        company_research_agent=company_research_agent,
    )


def build_scheduler_infrastructure(
    logger: logging.Logger,
) -> tuple[WorkflowEngine, Scheduler, APSchedulerService | None]:
    """Construct the WorkflowEngine/Scheduler/APSchedulerService chain.

    `SchedulerSettings` (app.config, Sprint 32) is read directly here
    rather than through a full `ConfigurationService`/`AppConfig`, since
    `AppConfig` bundles in `AnthropicSettings.api_key` (required, no
    default) — constructing it just to read the Scheduler section would
    make every startup (including this test suite's) fail without an
    unrelated Anthropic API key configured. `SchedulerSettings` has no
    required fields of its own, so it's safe to construct standalone.

    `APSchedulerService` is only built and started when
    `SchedulerSettings.enabled` is True (the default); a deployer can set
    `SCHEDULER_ENABLED=false` to disable the whole scheduling subsystem,
    in which case this returns `None` for it and no timer is created at
    all — `Scheduler` itself (and `WorkflowEngine`) are still returned and
    usable for direct, on-demand `run_schedule()` calls.
    """
    scheduler_settings = SchedulerSettings()
    workflow_engine = WorkflowEngine()
    scheduler = Scheduler(workflow_engine)

    if not scheduler_settings.enabled:
        logger.info("Scheduler subsystem disabled (SCHEDULER_ENABLED=false); APScheduler not started.")
        return workflow_engine, scheduler, None

    return workflow_engine, scheduler, APSchedulerService(scheduler)


def build_watchlist_repository(logger: logging.Logger) -> BaseWatchlistRepository | None:
    """Construct a PostgreSQL-backed Watchlist Repository.

    `PostgreSQLSettings` (app.config, Sprint 32) is read directly here
    rather than through a full `ConfigurationService`/`AppConfig`, for the
    same reason `build_scheduler_infrastructure` reads `SchedulerSettings`
    directly: `AppConfig` requires `AnthropicSettings.api_key`, which would
    make every startup (including this test suite's) fail without an
    unrelated Anthropic API key configured. `PostgreSQLSettings` has no
    required fields of its own, so it's safe to construct standalone.

    `create_async_engine` does not open a connection eagerly, so this
    always succeeds for a syntactically valid URL — an unreachable database
    only surfaces later, at first real use, via the repository's own
    `health_check()` (mirrors `PostgresKnowledgeRepository`'s own
    lazily-connecting behavior). Table creation (DDL) is intentionally not
    performed here — `alembic` is a declared dependency but no migration
    environment has been initialized in this codebase yet; see the
    Sprint 44 completion report for this flagged as a known gap.
    """
    settings = PostgreSQLSettings()
    database_url = settings.database_url or (
        f"postgresql+asyncpg://{settings.user}:{settings.password.get_secret_value()}"
        f"@{settings.host}:{settings.port}/{settings.db}"
    )
    try:
        engine = create_async_engine(database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        return PostgresWatchlistRepository(session_factory)
    except Exception as exc:  # noqa: BLE001 - an infrastructure failure must not crash startup
        logger.warning("Failed to initialize PostgreSQL watchlist repository: %s", exc)
        return None


def build_watchlist_service(
    repository: BaseWatchlistRepository | None, settings: AppSettings
) -> WatchlistService | None:
    """Construct the WatchlistService, or None if no repository is available."""
    if repository is None:
        return None
    return WatchlistService(repository, max_watchlist_size=settings.watchlist_max_size)


def build_screening_repository(logger: logging.Logger) -> BaseScreeningRepository | None:
    """Construct a PostgreSQL-backed Screening Repository.

    Same reasoning and same graceful-degradation shape as
    `build_watchlist_repository` above: `PostgreSQLSettings` is read
    standalone, `create_async_engine` never opens a connection eagerly, and
    table creation (DDL) is intentionally not performed here.
    """
    settings = PostgreSQLSettings()
    database_url = settings.database_url or (
        f"postgresql+asyncpg://{settings.user}:{settings.password.get_secret_value()}"
        f"@{settings.host}:{settings.port}/{settings.db}"
    )
    try:
        engine = create_async_engine(database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        return PostgresScreeningRepository(session_factory)
    except Exception as exc:  # noqa: BLE001 - an infrastructure failure must not crash startup
        logger.warning("Failed to initialize PostgreSQL screening repository: %s", exc)
        return None


def build_screening_engine(
    repository: BaseScreeningRepository | None, settings: AppSettings
) -> ScreeningEngine | None:
    """Construct the ScreeningEngine, or None if no repository is available."""
    if repository is None:
        return None
    return ScreeningEngine(repository, max_filters=settings.screening_max_filters)


def build_market_data_provider() -> MarketDataProvider:
    """Construct the registered `MarketDataProvider`.

    `MockMarketDataProvider` is the only implementation this sprint
    provides — deterministic and in-memory, never a real market-data API
    call. Unlike every other `build_*` function in this module, this one
    cannot fail (no connection, no credentials, no external dependency),
    so it always returns a usable instance rather than `None`. Swapping in
    a real provider in a future sprint means changing only this function's
    body — every caller depends on the `MarketDataProvider` interface, not
    on `MockMarketDataProvider` directly.
    """
    return MockMarketDataProvider()


def build_normalization_service() -> NormalizationService:
    """Construct the NormalizationService. Stateless and dependency-free —
    always succeeds."""
    return NormalizationService()


def build_signal_repository(logger: logging.Logger) -> BaseSignalDefinitionRepository | None:
    """Construct a PostgreSQL-backed Signal Definition Repository.

    Same reasoning and same graceful-degradation shape as
    `build_screening_repository`/`build_watchlist_repository`:
    `PostgreSQLSettings` is read standalone, `create_async_engine` never
    opens a connection eagerly, and table creation (DDL) is intentionally
    not performed here.
    """
    settings = PostgreSQLSettings()
    database_url = settings.database_url or (
        f"postgresql+asyncpg://{settings.user}:{settings.password.get_secret_value()}"
        f"@{settings.host}:{settings.port}/{settings.db}"
    )
    try:
        engine = create_async_engine(database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        return PostgresSignalDefinitionRepository(session_factory)
    except Exception as exc:  # noqa: BLE001 - an infrastructure failure must not crash startup
        logger.warning("Failed to initialize PostgreSQL signal definition repository: %s", exc)
        return None


def build_signal_detection_service(
    repository: BaseSignalDefinitionRepository | None, settings: AppSettings
) -> SignalDetectionService | None:
    """Construct the SignalDetectionService, or None if no repository is available."""
    if repository is None:
        return None
    return SignalDetectionService(repository, max_conditions=settings.signal_max_conditions)


def build_alert_rule_repository(logger: logging.Logger) -> BaseAlertRuleRepository | None:
    """Construct a PostgreSQL-backed Alert Rule Repository.

    Same reasoning and same graceful-degradation shape as
    `build_signal_repository`/`build_screening_repository`:
    `PostgreSQLSettings` is read standalone, `create_async_engine` never
    opens a connection eagerly, and table creation (DDL) is intentionally
    not performed here.
    """
    settings = PostgreSQLSettings()
    database_url = settings.database_url or (
        f"postgresql+asyncpg://{settings.user}:{settings.password.get_secret_value()}"
        f"@{settings.host}:{settings.port}/{settings.db}"
    )
    try:
        engine = create_async_engine(database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        return PostgresAlertRuleRepository(session_factory)
    except Exception as exc:  # noqa: BLE001 - an infrastructure failure must not crash startup
        logger.warning("Failed to initialize PostgreSQL alert rule repository: %s", exc)
        return None


def build_alert_repository(logger: logging.Logger) -> BaseAlertRepository | None:
    """Construct a PostgreSQL-backed Alert Repository. Same reasoning as
    `build_alert_rule_repository` above — a genuinely separate repository
    (and, in production, a separate table), per this sprint's own
    Dependency Injection section registering it independently."""
    settings = PostgreSQLSettings()
    database_url = settings.database_url or (
        f"postgresql+asyncpg://{settings.user}:{settings.password.get_secret_value()}"
        f"@{settings.host}:{settings.port}/{settings.db}"
    )
    try:
        engine = create_async_engine(database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        return PostgresAlertRepository(session_factory)
    except Exception as exc:  # noqa: BLE001 - an infrastructure failure must not crash startup
        logger.warning("Failed to initialize PostgreSQL alert repository: %s", exc)
        return None


def build_alert_service(
    rule_repository: BaseAlertRuleRepository | None,
    alert_repository: BaseAlertRepository | None,
    settings: AppSettings,
) -> AlertService | None:
    """Construct the AlertService, or None if either repository is unavailable."""
    if rule_repository is None or alert_repository is None:
        return None
    return AlertService(rule_repository, alert_repository, max_rules=settings.alert_max_rules)


def build_recommendation_repository(logger: logging.Logger) -> BaseRecommendationRepository | None:
    """Construct a PostgreSQL-backed Recommendation Repository.

    Same reasoning and same graceful-degradation shape as every other
    `build_*_repository` function in this module: `PostgreSQLSettings` is
    read standalone, `create_async_engine` never opens a connection
    eagerly, and table creation (DDL) is intentionally not performed here.
    """
    settings = PostgreSQLSettings()
    database_url = settings.database_url or (
        f"postgresql+asyncpg://{settings.user}:{settings.password.get_secret_value()}"
        f"@{settings.host}:{settings.port}/{settings.db}"
    )
    try:
        engine = create_async_engine(database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        return PostgresRecommendationRepository(session_factory)
    except Exception as exc:  # noqa: BLE001 - an infrastructure failure must not crash startup
        logger.warning("Failed to initialize PostgreSQL recommendation repository: %s", exc)
        return None


def build_recommendation_service(
    repository: BaseRecommendationRepository | None,
) -> PortfolioRecommendationService | None:
    """Construct the PortfolioRecommendationService, or None if no
    repository is available. Unlike every other `build_*_service`
    function in this module, no `AppSettings` field is threaded through:
    the sprint's own configurable knobs (`ScoringWeights`,
    `RecommendationThresholds`) are per-request scoring policy, not
    process-wide configuration, and are left at their documented defaults
    here — a caller wanting different weights/thresholds constructs its
    own `PortfolioRecommendationService` directly, exactly as any other
    consumer of this class would.
    """
    if repository is None:
        return None
    return PortfolioRecommendationService(repository)


def build_strategy_repository(logger: logging.Logger) -> BaseStrategyRepository | None:
    """Construct a PostgreSQL-backed Strategy Repository.

    Same reasoning and same graceful-degradation shape as every other
    `build_*_repository` function in this module: `PostgreSQLSettings` is
    read standalone, `create_async_engine` never opens a connection
    eagerly, and table creation (DDL) is intentionally not performed here.
    """
    settings = PostgreSQLSettings()
    database_url = settings.database_url or (
        f"postgresql+asyncpg://{settings.user}:{settings.password.get_secret_value()}"
        f"@{settings.host}:{settings.port}/{settings.db}"
    )
    try:
        engine = create_async_engine(database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        return PostgresStrategyRepository(session_factory)
    except Exception as exc:  # noqa: BLE001 - an infrastructure failure must not crash startup
        logger.warning("Failed to initialize PostgreSQL strategy repository: %s", exc)
        return None


def build_strategy_service(
    repository: BaseStrategyRepository | None,
) -> StrategyEvaluationService | None:
    """Construct the StrategyEvaluationService, or None if no repository
    is available. Same reasoning as `build_recommendation_service` above:
    no `AppSettings` field is threaded through — `max_strategies`/
    `max_rules` are left at their documented defaults."""
    if repository is None:
        return None
    return StrategyEvaluationService(repository)


def build_risk_repository(logger: logging.Logger) -> BaseRiskAnalyticsRepository | None:
    """Construct a PostgreSQL-backed Risk Analytics Repository.

    Same reasoning and same graceful-degradation shape as every other
    `build_*_repository` function in this module: `PostgreSQLSettings` is
    read standalone, `create_async_engine` never opens a connection
    eagerly, and table creation (DDL) is intentionally not performed here.
    """
    settings = PostgreSQLSettings()
    database_url = settings.database_url or (
        f"postgresql+asyncpg://{settings.user}:{settings.password.get_secret_value()}"
        f"@{settings.host}:{settings.port}/{settings.db}"
    )
    try:
        engine = create_async_engine(database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        return PostgresRiskAnalyticsRepository(session_factory)
    except Exception as exc:  # noqa: BLE001 - an infrastructure failure must not crash startup
        logger.warning("Failed to initialize PostgreSQL risk analytics repository: %s", exc)
        return None


def build_risk_service(repository: BaseRiskAnalyticsRepository | None) -> RiskAnalyticsService | None:
    """Construct the RiskAnalyticsService, or None if no repository is
    available. Same reasoning as `build_strategy_service` above: no
    `AppSettings` field is threaded through — `RiskWeighting`/
    `RiskThresholds`/`max_exposures` are left at their documented
    defaults."""
    if repository is None:
        return None
    return RiskAnalyticsService(repository)


def build_backtesting_repository(logger: logging.Logger) -> BaseBacktestingRepository | None:
    """Construct a PostgreSQL-backed Backtesting Repository.

    Same reasoning and same graceful-degradation shape as every other
    `build_*_repository` function in this module: `PostgreSQLSettings` is
    read standalone, `create_async_engine` never opens a connection
    eagerly, and table creation (DDL) is intentionally not performed here.
    """
    settings = PostgreSQLSettings()
    database_url = settings.database_url or (
        f"postgresql+asyncpg://{settings.user}:{settings.password.get_secret_value()}"
        f"@{settings.host}:{settings.port}/{settings.db}"
    )
    try:
        engine = create_async_engine(database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        return PostgresBacktestingRepository(session_factory)
    except Exception as exc:  # noqa: BLE001 - an infrastructure failure must not crash startup
        logger.warning("Failed to initialize PostgreSQL backtesting repository: %s", exc)
        return None


def build_backtesting_service(
    repository: BaseBacktestingRepository | None,
    recommendation_service: PortfolioRecommendationService | None,
    strategy_service: StrategyEvaluationService | None,
    risk_service: RiskAnalyticsService | None,
) -> BacktestingService | None:
    """Construct the BacktestingService, or None if the repository or any
    of the three injected services it replays through is unavailable.
    Unlike `build_recommendation_service`/`build_strategy_service`/
    `build_risk_service`, this one has three service dependencies (not
    just a repository) — see `app.backtesting.engine`'s own docstring for
    why: replay resolves each historical snapshot by calling into the
    already-built Recommendation/Strategy/Risk services directly, so all
    three must exist for backtesting to be usable at all. Same reasoning
    as those three otherwise: `max_periods` is left at its documented
    default here.
    """
    if repository is None or recommendation_service is None or strategy_service is None or risk_service is None:
        return None
    return BacktestingService(repository, recommendation_service, strategy_service, risk_service)


def build_explainability_repository(logger: logging.Logger) -> BaseExplainabilityRepository | None:
    """Construct a PostgreSQL-backed Explainability Repository.

    Same reasoning and same graceful-degradation shape as every other
    `build_*_repository` function in this module: `PostgreSQLSettings` is
    read standalone, `create_async_engine` never opens a connection
    eagerly, and table creation (DDL) is intentionally not performed here.
    """
    settings = PostgreSQLSettings()
    database_url = settings.database_url or (
        f"postgresql+asyncpg://{settings.user}:{settings.password.get_secret_value()}"
        f"@{settings.host}:{settings.port}/{settings.db}"
    )
    try:
        engine = create_async_engine(database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        return PostgresExplainabilityRepository(session_factory)
    except Exception as exc:  # noqa: BLE001 - an infrastructure failure must not crash startup
        logger.warning("Failed to initialize PostgreSQL explainability repository: %s", exc)
        return None


def build_explainability_service(
    repository: BaseExplainabilityRepository | None,
    recommendation_service: PortfolioRecommendationService | None,
    strategy_service: StrategyEvaluationService | None,
    risk_service: RiskAnalyticsService | None,
    backtesting_service: BacktestingService | None,
) -> ExplainabilityService | None:
    """Construct the ExplainabilityService, or None if the repository or
    any of the four injected services it explains through is unavailable.
    Same reasoning as `build_backtesting_service` above: this engine
    resolves every referenced id by calling into the already-built
    Recommendation/Strategy/Risk/Backtesting services directly, so all
    four must exist for explanation to be usable at all. `max_categories`/
    `contribution_total`/`weighting` are left at their documented
    defaults here.
    """
    if (
        repository is None
        or recommendation_service is None
        or strategy_service is None
        or risk_service is None
        or backtesting_service is None
    ):
        return None
    return ExplainabilityService(repository, recommendation_service, strategy_service, risk_service, backtesting_service)


def build_structured_logger(logger: logging.Logger) -> StdlibStructuredLogger:
    """Wrap an already-configured stdlib `Logger` in the structured
    logging abstraction (Sprint 54) — never a vendor SDK. Cannot fail:
    unlike a repository, this has no external connection to establish."""
    return StdlibStructuredLogger(logger)


def build_metrics_recorder() -> InMemoryMetricsRecorder:
    """Construct the metrics recorder (Sprint 54). In-memory only — no
    Prometheus/StatsD/vendor integration; a future sprint can add one
    without changing any caller of `BaseMetricsRecorder`."""
    return InMemoryMetricsRecorder()


def build_profiler() -> InMemoryProfiler:
    """Construct the performance profiler (Sprint 54). Plain wall-clock
    timing only — no sampling profiler, no external tooling."""
    return InMemoryProfiler()


def build_health_check_service() -> HealthCheckService:
    """Construct the health check service (Sprint 54). Cannot fail:
    holds no external connection itself — every check it performs calls
    into an already-constructed repository's own `health_check()`."""
    return HealthCheckService()


def build_configuration_validation_service() -> ConfigurationValidationService:
    """Construct the configuration validation service (Sprint 54)."""
    return ConfigurationValidationService()


def build_startup_validation_service(
    configuration_service: ConfigurationValidationService,
) -> StartupValidationService:
    """Construct the startup validation service (Sprint 54), composing
    `configuration_service` via injection rather than re-implementing its
    checks."""
    return StartupValidationService(configuration_service)


def build_auth_repository(logger: logging.Logger) -> BaseAuthRepository | None:
    """Construct a PostgreSQL-backed Auth Repository (Sprint 56).

    Same reasoning and same graceful-degradation shape as every other
    `build_*_repository` function in this module: `PostgreSQLSettings` is
    read standalone, `create_async_engine` never opens a connection
    eagerly, and table creation (DDL) is intentionally not performed here.
    """
    settings = PostgreSQLSettings()
    database_url = settings.database_url or (
        f"postgresql+asyncpg://{settings.user}:{settings.password.get_secret_value()}"
        f"@{settings.host}:{settings.port}/{settings.db}"
    )
    try:
        engine = create_async_engine(database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        return PostgresAuthRepository(session_factory)
    except Exception as exc:  # noqa: BLE001 - an infrastructure failure must not crash startup
        logger.warning("Failed to initialize PostgreSQL auth repository: %s", exc)
        return None


def build_clock() -> BaseClock:
    """Construct the clock (Sprint 56). Real wall-clock time in
    production; tests inject their own `BaseClock` directly."""
    return SystemClock()


def build_password_hasher() -> BasePasswordHasher:
    """Construct the password hasher (Sprint 56). PBKDF2-HMAC-SHA256,
    standard library only — see `app.auth.security.password_hashing`'s
    own docstring for why no third-party hashing library is introduced."""
    return Pbkdf2PasswordHasher()


def build_jwt_signer(settings: AuthSettings) -> BaseJWTSigner:
    """Construct the JWT signer (Sprint 56) from `AuthSettings`. The one
    place outside `app.auth.security.secrets_loader` itself that touches
    `load_jwt_secret` — the raw secret is never threaded any further than
    this constructor call."""
    return HmacJWTSigner(load_jwt_secret(settings), algorithm=settings.algorithm)


def build_authorization_service(repository: BaseAuthRepository | None) -> AuthorizationService | None:
    """Construct the authorization service (Sprint 56), or None if no
    repository is available."""
    if repository is None:
        return None
    return AuthorizationService(repository)


def build_authentication_provider(
    repository: BaseAuthRepository | None,
    authorization_service: AuthorizationService | None,
    jwt_signer: BaseJWTSigner,
    password_hasher: BasePasswordHasher,
    clock: BaseClock,
    settings: AuthSettings,
) -> AuthenticationProvider | None:
    """Construct the JWT authentication provider (Sprint 56), or None if
    its repository/authorization-service dependencies are unavailable.
    This is the one function in this module that names a concrete
    provider (`JwtAuthenticationProvider`) — swapping in a future
    provider means changing only this function's body; every caller of
    `build_authentication_service` below depends on the
    `AuthenticationProvider` abstraction it returns, never this concrete
    type.
    """
    if repository is None or authorization_service is None:
        return None
    return JwtAuthenticationProvider(
        repository,
        jwt_signer,
        password_hasher,
        authorization_service,
        clock=clock,
        access_token_ttl=timedelta(minutes=settings.access_token_expire_minutes),
        refresh_token_ttl=timedelta(minutes=settings.refresh_token_expire_minutes),
        clock_skew_tolerance=timedelta(seconds=settings.clock_skew_tolerance_seconds),
    )


def build_authentication_service(
    provider: AuthenticationProvider | None,
    repository: BaseAuthRepository | None,
    password_hasher: BasePasswordHasher,
) -> AuthenticationService | None:
    """Construct the authentication service (Sprint 56), or None if its
    provider/repository dependencies are unavailable."""
    if provider is None or repository is None:
        return None
    return AuthenticationService(provider, repository, password_hasher)


def build_policy_evaluator() -> PolicyEvaluator:
    """Construct the policy evaluator (Sprint 56). Cannot fail: holds no
    external dependency of its own."""
    return PolicyEvaluator()


async def bootstrap_application_state(app: FastAPI) -> None:
    """Construct every injectable component and populate `app.state`.

    This is the application's composition root, invoked once at startup
    (see `app/lifespan.py`).
    """
    started_at = time.perf_counter()

    settings = AppSettings()
    configure_logging(settings)
    logger = logging.getLogger("marketmind.bootstrap")
    structured_logger = build_structured_logger(logger)
    metrics_recorder = build_metrics_recorder()
    profiler = build_profiler()
    health_check_service = build_health_check_service()
    configuration_validation_service = build_configuration_validation_service()
    startup_validation_service = build_startup_validation_service(configuration_validation_service)

    runtime = AgentRuntime(
        logger=logging.getLogger("marketmind.agents"),
        configuration=SettingsConfiguration(settings),
        knowledge_hub=EmptyKnowledgeHub(),
        memory=InProcessMemory(),
        tool_registry=EmptyToolRegistry(),
        event_bus=NoOpEventBus(),
    )

    workflow_engine, scheduler, ap_scheduler_service = build_scheduler_infrastructure(logger)
    if ap_scheduler_service is not None:
        await ap_scheduler_service.start()

    watchlist_repository = build_watchlist_repository(logger)
    screening_repository = build_screening_repository(logger)
    signal_repository = build_signal_repository(logger)
    alert_rule_repository = build_alert_rule_repository(logger)
    alert_repository = build_alert_repository(logger)
    recommendation_repository = build_recommendation_repository(logger)
    strategy_repository = build_strategy_repository(logger)
    risk_repository = build_risk_repository(logger)
    backtesting_repository = build_backtesting_repository(logger)
    explainability_repository = build_explainability_repository(logger)
    auth_repository = build_auth_repository(logger)

    app.state.settings = settings
    app.state.agent_runtime = runtime
    app.state.knowledge_repository = build_knowledge_repository(settings, logger)
    app.state.embedding_provider = build_embedding_provider(settings, logger)
    app.state.news_collector_agent = build_news_collector_agent(runtime, settings)
    app.state.prompt_registry = build_prompt_registry()
    app.state.knowledge_hub = build_knowledge_hub(app.state.knowledge_repository)
    app.state.llm_service = build_llm_service(logger)
    app.state.company_research_agent = build_company_research_agent(
        runtime, app.state.knowledge_hub, app.state.llm_service, app.state.prompt_registry
    )
    app.state.portfolio_intelligence_agent = build_portfolio_intelligence_agent(
        runtime,
        app.state.knowledge_hub,
        app.state.llm_service,
        app.state.prompt_registry,
        app.state.company_research_agent,
    )
    app.state.workflow_engine = workflow_engine
    app.state.scheduler = scheduler
    app.state.ap_scheduler_service = ap_scheduler_service
    app.state.watchlist_repository = watchlist_repository
    app.state.watchlist_service = build_watchlist_service(watchlist_repository, settings)
    app.state.screening_repository = screening_repository
    app.state.screening_engine = build_screening_engine(screening_repository, settings)
    app.state.market_data_provider = build_market_data_provider()
    app.state.normalization_service = build_normalization_service()
    app.state.signal_repository = signal_repository
    app.state.signal_detection_service = build_signal_detection_service(signal_repository, settings)
    app.state.alert_rule_repository = alert_rule_repository
    app.state.alert_repository = alert_repository
    app.state.alert_service = build_alert_service(alert_rule_repository, alert_repository, settings)
    app.state.recommendation_repository = recommendation_repository
    app.state.recommendation_service = build_recommendation_service(recommendation_repository)
    app.state.strategy_repository = strategy_repository
    app.state.strategy_service = build_strategy_service(strategy_repository)
    app.state.risk_repository = risk_repository
    app.state.risk_service = build_risk_service(risk_repository)
    app.state.backtesting_repository = backtesting_repository
    app.state.backtesting_service = build_backtesting_service(
        backtesting_repository,
        app.state.recommendation_service,
        app.state.strategy_service,
        app.state.risk_service,
    )
    app.state.explainability_repository = explainability_repository
    app.state.explainability_service = build_explainability_service(
        explainability_repository,
        app.state.recommendation_service,
        app.state.strategy_service,
        app.state.risk_service,
        app.state.backtesting_service,
    )

    auth_settings = AuthSettings()
    clock = build_clock()
    password_hasher = build_password_hasher()
    jwt_signer = build_jwt_signer(auth_settings)
    app.state.auth_repository = auth_repository
    app.state.authorization_service = build_authorization_service(auth_repository)
    authentication_provider = build_authentication_provider(
        auth_repository, app.state.authorization_service, jwt_signer, password_hasher, clock, auth_settings
    )
    app.state.authentication_service = build_authentication_service(
        authentication_provider, auth_repository, password_hasher
    )
    app.state.policy_evaluator = build_policy_evaluator()

    app.state.structured_logger = structured_logger
    app.state.metrics_recorder = metrics_recorder
    app.state.profiler = profiler
    app.state.health_check_service = health_check_service
    app.state.configuration_validation_service = configuration_validation_service
    app.state.startup_validation_service = startup_validation_service
    app.state.startup_validation_report = _run_startup_validation(app, startup_validation_service, settings, auth_settings)

    duration_seconds = time.perf_counter() - started_at
    metrics_recorder.record_duration(METRIC_STARTUP_DURATION_SECONDS, duration_seconds)
    structured_logger.info(
        LogCategory.STARTUP,
        "bootstrap_completed",
        duration_seconds=round(duration_seconds, 4),
        startup_validation_passed=app.state.startup_validation_report.passed,
    )
    logger.info("MarketMind AI application state bootstrapped.")


def _run_startup_validation(
    app: FastAPI,
    startup_validation_service: StartupValidationService,
    settings: AppSettings,
    auth_settings: AuthSettings,
) -> ValidationReport:
    """Run `StartupValidationService.validate_full()` against every
    component just wired into `app.state`. Never crashes bootstrap on a
    failed check (matches this module's own established "an
    infrastructure/configuration issue degrades, it never crashes
    startup" philosophy) — the report is stored on `app.state
    .startup_validation_report` for the caller (or a future health
    endpoint) to inspect and act on.
    """
    components = tuple((name, getattr(app.state, name, None)) for name in DEFAULT_REQUIRED_COMPONENTS)
    try:
        anthropic_settings: AnthropicSettings | None = AnthropicSettings()
    except Exception:  # noqa: BLE001 - a missing required secret must not crash startup
        anthropic_settings = None
    return startup_validation_service.validate_full(
        components,
        environment=settings.environment,
        postgres=PostgreSQLSettings(),
        anthropic=anthropic_settings,
        logging_settings=LoggingSettings(),
        llm=LLMSettings(),
        api=APISettings(),
        rss=RSSSettings(),
        auth=auth_settings,
    )


async def shutdown_application_state(app: FastAPI) -> None:
    """Release any resources acquired during bootstrap.

    Every other constructed component holds no resource requiring explicit
    teardown (ChromaDB's PersistentClient needs none; the in-process
    memory/event-bus/tool-registry defaults hold nothing external) — only
    `ap_scheduler_service`, when built, owns a real background timer that
    must be stopped gracefully.
    """
    logger = logging.getLogger("marketmind.bootstrap")

    ap_scheduler_service = getattr(app.state, "ap_scheduler_service", None)
    if ap_scheduler_service is not None:
        await ap_scheduler_service.shutdown()

    logger.info("MarketMind AI application state shut down.")
