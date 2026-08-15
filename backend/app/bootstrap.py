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

Milestone 11 update: `MorningPipeline` (Market Intelligence Ingestion) is
now registered into the WorkflowEngine and scheduled via `Scheduler`,
using `build_morning_pipeline()` below — the real `ChromaDB`-backed
`knowledge_repository` and the newly-implemented `LocalEmbeddingProvider`
(`build_embedding_provider()`) it needed are both built here. Registration
is gated by `INGESTION_ENABLED` (default `False` — an explicit opt-in for
this new post-v1.0 capability, so upgrading an existing deployment never
silently starts a new background job) and only happens at all when both
`knowledge_repository` and `embedding_provider` were actually constructed
(chromadb reachable, embedding provider healthy) — see
`docs/architecture/MARKET_INTELLIGENCE_INGESTION.md` for the full design.

`MorningBriefWorkflow` (a separate, still-unbuilt workflow — not to be
confused with `MorningPipeline` above) remains unregistered: it needs the
reasoning engines wired together for report *generation*, a distinct,
larger dependency chain this milestone does not build.
"""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agents.company_research.agent import CompanyResearchAgent
from app.agents.company_research.prompts import register_company_research_prompts
from app.agents.news_collector.agent import NewsCollectorAgent
from app.agents.portfolio_intelligence.agent import PortfolioIntelligenceAgent
from app.agents.portfolio_intelligence.prompts import register_portfolio_intelligence_prompts
from app.alerts.engine import AlertService
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
from app.explainability.engine import ExplainabilityService
from app.knowledge.hub import KnowledgeHub
from app.market_data.normalization import NormalizationService
from app.operations.health.service import HealthCheckService
from app.operations.logging.logger import StdlibStructuredLogger
from app.operations.logging.models import LogCategory
from app.operations.metrics.models import METRIC_STARTUP_DURATION_SECONDS
from app.operations.metrics.recorder import InMemoryMetricsRecorder
from app.operations.profiling.profiler import InMemoryProfiler
from app.operations.validation.configuration import ConfigurationValidationService
from app.operations.validation.models import ValidationReport
from app.operations.validation.startup import DEFAULT_REQUIRED_COMPONENTS, StartupValidationService
from app.prompts.registry import PromptRegistry
from app.providers.anthropic.models import AnthropicProviderConfig
from app.providers.anthropic.provider import AnthropicProvider
from app.providers.embedding.local import LocalEmbeddingProvider
from app.providers.embedding.models import EmbeddingProviderConfig
from app.providers.embedding.provider import BaseEmbeddingProvider
from app.providers.market_data.mock import MockMarketDataProvider
from app.providers.market_data.provider import MarketDataProvider
from app.providers.market_data.yahoo import YahooFinanceProvider, YahooFinanceProviderConfig
from app.providers.models import ProviderConfig
from app.providers.registry import ProviderRegistry
from app.providers.rss.models import RSSProviderConfig
from app.providers.rss.provider import RSSProvider
from app.recommendations.engine import PortfolioRecommendationService
from app.repositories.alerts.postgres.repository import (
    PostgresAlertRepository,
    PostgresAlertRuleRepository,
)
from app.repositories.alerts.repository import BaseAlertRepository, BaseAlertRuleRepository
from app.repositories.backtesting.postgres.repository import PostgresBacktestingRepository
from app.repositories.backtesting.repository import BaseBacktestingRepository
from app.repositories.continuous_intelligence.postgres.repository import (
    PostgresContinuousIntelligenceStateRepository,
)
from app.repositories.continuous_intelligence.repository import (
    BaseContinuousIntelligenceStateRepository,
)
from app.repositories.explainability.postgres.repository import PostgresExplainabilityRepository
from app.repositories.explainability.repository import BaseExplainabilityRepository
from app.repositories.knowledge.repository import BaseKnowledgeRepository
from app.repositories.recommendations.postgres.repository import PostgresRecommendationRepository
from app.repositories.recommendations.repository import BaseRecommendationRepository
from app.repositories.risk.postgres.repository import PostgresRiskAnalyticsRepository
from app.repositories.risk.repository import BaseRiskAnalyticsRepository
from app.repositories.screening.postgres.repository import PostgresScreeningRepository
from app.repositories.screening.repository import BaseScreeningRepository
from app.repositories.signals.postgres.repository import PostgresSignalDefinitionRepository
from app.repositories.signals.repository import BaseSignalDefinitionRepository
from app.repositories.strategy.postgres.repository import PostgresStrategyRepository
from app.repositories.strategy.repository import BaseStrategyRepository
from app.repositories.watchlist.postgres.repository import PostgresWatchlistRepository
from app.repositories.watchlist.repository import BaseWatchlistRepository
from app.risk.engine import RiskAnalyticsService
from app.scheduler.ap_scheduler import APSchedulerService
from app.scheduler.models import Schedule, ScheduleTriggerType
from app.scheduler.scheduler import Scheduler
from app.screening.engine import ScreeningEngine
from app.services.embedding.service import EmbeddingService
from app.services.entity_resolution.service import (
    DEFAULT_HIGH_THRESHOLD,
    DEFAULT_MAX_CANDIDATES,
    DEFAULT_MEDIUM_THRESHOLD,
    EntityResolutionService,
)
from app.services.evidence_engine.engine import EvidenceEngine
from app.services.knowledge_ingestion.service import KnowledgeIngestionService
from app.services.llm.service import LLMService
from app.services.market_intelligence.engine import MarketIntelligenceEngine
from app.services.market_snapshot.cache import InMemoryMarketSnapshotCache
from app.services.market_snapshot.service import MarketSnapshotService
from app.services.continuous_intelligence.config import ContinuousIntelligenceThresholds
from app.services.continuous_intelligence.locking import (
    CycleLock,
    InMemoryCycleLock,
    PostgresCycleLock,
)
from app.services.continuous_intelligence.service import ContinuousIntelligenceService
from app.services.continuous_intelligence.state import (
    ContinuousIntelligenceStateStore,
    InMemoryContinuousIntelligenceStateStore,
    PostgresContinuousIntelligenceStateStore,
)
from app.services.continuous_intelligence.suppression import (
    PostgresSuppressionService,
    Suppression,
    SuppressionService,
)
from app.services.entity_resolution.reference_overlay import (
    apply_canonical_entity_overlay_from_path,
)
from app.services.portfolio_market_snapshot.service import PortfolioMarketSnapshotService
from app.services.relationship_engine.engine import RelationshipEngine
from app.signals.engine import SignalDetectionService
from app.strategy.engine import StrategyEvaluationService
from app.watchlist.service import WatchlistService
from app.workflows.engine import WorkflowEngine
from app.workflows.continuous_intelligence.workflow import ContinuousIntelligenceWorkflow
from app.workflows.market_data_refresh.workflow import MarketDataRefreshWorkflow
from app.workflows.morning_pipeline.pipeline import MorningPipeline

if TYPE_CHECKING:
    # Type-checking only: `app.api.ws` is pure API-layer infrastructure
    # (see `app.main.create_app`'s own docstring — `EventPublisher` is
    # deliberately constructed there, not in this composition root), so
    # this module never imports it at runtime; `event_publisher` is read
    # off `app.state` (already set by `main.py` before this function
    # runs) via `getattr`, never constructed here.
    from app.api.ws.publishers.event_publisher import EventPublisher

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
    "build_entity_resolution_service",
    "build_news_collector_agent",
    "build_morning_pipeline",
    "register_ingestion_schedule",
    "build_scheduler_infrastructure",
    "build_watchlist_repository",
    "build_watchlist_service",
    "build_screening_repository",
    "build_screening_engine",
    "build_market_data_provider",
    "build_market_snapshot_service",
    "build_portfolio_market_snapshot_service",
    "build_market_data_refresh_workflow",
    "register_market_data_schedule",
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
    "build_continuous_intelligence_thresholds",
    "build_continuous_intelligence_repository",
    "build_continuous_intelligence_state_store",
    "build_continuous_intelligence_suppression",
    "build_continuous_intelligence_lock",
    "build_continuous_intelligence_service",
    "build_continuous_intelligence_workflow",
    "register_continuous_intelligence_schedule",
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
    rss_feed_timeout_seconds: float = 10.0
    rss_retry_attempts: int = 1
    rss_retry_backoff_seconds: float = 1.0
    # --- Market Intelligence Ingestion (Milestone 11) ---
    # Default False: an explicit opt-in for this new post-v1.0 capability
    # — upgrading an existing deployment must never silently start a new
    # periodic background job. Harmless either way when enabled with no
    # RSS_FEED_URLS configured (same "nothing to collect" behavior
    # `build_news_collector_agent` already documents).
    ingestion_enabled: bool = False
    ingestion_interval_seconds: float = 3600.0
    # The only currently-implemented option is "local" (LocalEmbeddingProvider,
    # `app.providers.embedding.local`) — a real embedding call, but not
    # hardcoded into MorningPipeline: this setting is the one place that
    # decides which concrete BaseEmbeddingProvider gets built.
    embedding_provider: str = "local"
    embedding_model: str = "all-MiniLM-L6-v2"
    # --- Entity Resolution & Company Intelligence (Milestone 12) ---
    # Default True, unlike INGESTION_ENABLED above: resolution is a pure,
    # deterministic, in-process metadata enrichment — it starts no new
    # scheduled job and calls no external service, so (unlike a new
    # periodic background job) there is no "upgrading silently changes
    # runtime behavior" concern to guard against with an opt-in default.
    # An operator who wants the pre-Milestone-12 behavior (every record
    # `entity_resolved: False`) can still set this to false.
    entity_resolution_enabled: bool = True
    entity_match_high_threshold: float = DEFAULT_HIGH_THRESHOLD
    entity_match_medium_threshold: float = DEFAULT_MEDIUM_THRESHOLD
    entity_max_candidates: int = DEFAULT_MAX_CANDIDATES
    # --- Live Market Data & Price Intelligence (Milestone 13) ---
    # Default "mock" (MockMarketDataProvider, unchanged pre-Milestone-13
    # behavior) — like INGESTION_ENABLED (not like ENTITY_RESOLUTION_ENABLED):
    # a real provider is a new outbound network call surface, so upgrading
    # an existing deployment must never silently start making live
    # requests to an external vendor. MARKET_DATA_ENABLED (below) gates
    # only the *scheduled refresh job*, separately from which provider
    # MARKET_DATA_PROVIDER itself selects — an operator can use the real
    # provider for on-demand/Research lookups without opting into the
    # periodic background refresh, or vice versa.
    market_data_provider: str = "mock"
    market_data_timeout_seconds: float = 10.0
    market_data_retry_attempts: int = 1
    market_data_retry_backoff_seconds: float = 1.0
    market_data_cache_ttl_seconds: float = 60.0
    market_data_enabled: bool = False
    market_data_refresh_interval_seconds: float = 3600.0
    watchlist_max_size: int = 500
    screening_max_filters: int = 100
    signal_max_conditions: int = 100
    alert_max_rules: int = 100
    # --- Continuous Intelligence & Decision Automation (Milestone 15) ---
    # Default disabled, like INGESTION_ENABLED/MARKET_DATA_ENABLED: this
    # cycle calls the real market provider (via MarketSnapshotService) and
    # publishes real-time notifications on every run, so upgrading an
    # existing deployment must never silently start doing either.
    continuous_intelligence_enabled: bool = False
    continuous_intelligence_interval_seconds: float = 900.0
    market_change_threshold: float = 3.0
    news_significance_threshold: int = 2
    news_high_confidence_threshold: float = 0.75
    recommendation_score_delta_threshold: float = 10.0
    strategy_alignment_delta_threshold: float = 10.0
    continuous_intelligence_suppression_cooldown_minutes: float = 60.0
    # Milestone 16 §5/§6: how long a PostgresCycleLock claim is honored
    # before being treated as abandoned and automatically reclaimed.
    continuous_intelligence_lock_ttl_seconds: float = 300.0
    # Milestone 16 §8: optional path to a JSON file of additional
    # canonical entities to merge into COMPANY_KEYWORDS at startup. Unset
    # by default — no overlay, zero behavior change from Milestone 15.
    canonical_entities_overlay_path: str | None = None


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
    """Construct the configured concrete BaseEmbeddingProvider.

    `settings.embedding_provider` selects the implementation — never
    hardcoded into `MorningPipeline` itself, which only ever depends on
    the `BaseEmbeddingProvider` abstraction. Only `"local"`
    (`LocalEmbeddingProvider`, a local CPU-only model — no external API
    key, no new external service) is implemented today; an unrecognized
    value degrades to None (logged), the same "not configured" shape
    every other optional dependency in this module already uses, rather
    than crashing startup.
    """
    if settings.embedding_provider != "local":
        logger.warning(
            "Unrecognized EMBEDDING_PROVIDER %r; embedding_provider will be unavailable.",
            settings.embedding_provider,
        )
        return None
    config = EmbeddingProviderConfig(provider_id="local", model=settings.embedding_model)
    return LocalEmbeddingProvider(config)


def build_entity_resolution_service(
    settings: AppSettings, logger: logging.Logger
) -> EntityResolutionService | None:
    """Construct the Entity Resolution Service (Milestone 12), or None if
    disabled/misconfigured.

    Returns None — the same "not configured" shape every other optional
    dependency in this module uses — when `ENTITY_RESOLUTION_ENABLED` is
    false, or when the configured thresholds are invalid
    (`EntityResolutionService.__init__` validates
    `0 <= medium_threshold <= high_threshold <= 1` and
    `max_candidates >= 1`); a bad threshold value degrades to "entity
    resolution unavailable" rather than crashing startup, exactly like a
    missing embedding provider or unreachable database.
    """
    if not settings.entity_resolution_enabled:
        logger.info("Entity Resolution disabled (ENTITY_RESOLUTION_ENABLED=false).")
        return None
    try:
        return EntityResolutionService(
            high_threshold=settings.entity_match_high_threshold,
            medium_threshold=settings.entity_match_medium_threshold,
            max_candidates=settings.entity_max_candidates,
        )
    except ValueError as exc:
        logger.warning("Invalid entity resolution configuration; entity_resolution_service will be unavailable: %s", exc)
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
            timeout=settings.rss_feed_timeout_seconds,
            retry_attempts=settings.rss_retry_attempts,
            retry_backoff_seconds=settings.rss_retry_backoff_seconds,
        )
    ]
    return NewsCollectorAgent(
        memory=runtime.memory, registry=registry, provider_configs=provider_configs
    )


def build_morning_pipeline(
    news_collector: NewsCollectorAgent,
    embedding_provider: BaseEmbeddingProvider | None,
    knowledge_repository: BaseKnowledgeRepository | None,
    entity_resolution_service: EntityResolutionService | None,
) -> MorningPipeline | None:
    """Construct the Market Intelligence Ingestion pipeline (Milestone 11).

    Returns None — the same "not configured" shape every other optional
    dependency in this module uses — when either hard dependency isn't
    available (chromadb unreachable, or the configured embedding provider
    failed to build): a real run needs both a place to persist knowledge
    and a real embedding provider, so a partially-built pipeline would
    only ever fail at Stage 4 or 5. `news_collector` has no such failure
    mode (`build_news_collector_agent` always succeeds, even with zero
    feeds configured), so it's a required, non-Optional argument here.
    `entity_resolution_service` (Milestone 12) is genuinely optional even
    when the pipeline itself builds successfully — `KnowledgeIngestionService`
    degrades to its pre-Milestone-12 behavior (`entity_resolved: False`
    on every record) when it's None, exactly as documented on that
    service's own constructor.

    `KnowledgeIngestionService`/`EmbeddingService`/`EvidenceEngine`/
    `MarketIntelligenceEngine`/`RelationshipEngine` all construct without
    any external dependency of their own (see each one's own module) —
    built fresh here, not shared with any other part of this composition
    root, since none of them hold state.
    """
    if embedding_provider is None or knowledge_repository is None:
        return None
    return MorningPipeline(
        news_collector=news_collector,
        ingestion_service=KnowledgeIngestionService(entity_resolver=entity_resolution_service),
        embedding_service=EmbeddingService(),
        embedding_provider=embedding_provider,
        knowledge_repository=knowledge_repository,
        evidence_engine=EvidenceEngine(),
        market_intelligence_engine=MarketIntelligenceEngine(),
        relationship_engine=RelationshipEngine(),
    )


INGESTION_WORKFLOW_ID = "market_intelligence_ingestion"


def register_ingestion_schedule(
    workflow_engine: WorkflowEngine,
    scheduler: Scheduler,
    morning_pipeline: MorningPipeline | None,
    settings: AppSettings,
    logger: logging.Logger,
) -> None:
    """Register MorningPipeline with WorkflowEngine and schedule it.

    A no-op (logged) if `morning_pipeline` is None — nothing to run.
    Otherwise always registers the workflow (so
    `Scheduler.run_schedule(INGESTION_WORKFLOW_ID)` — the operational
    "run now" trigger, `backend/scripts/run_ingestion.py` — works
    regardless of whether the automatic timer is on) and always
    registers a Schedule, but with `enabled=settings.ingestion_enabled` —
    `Scheduler`'s own contract ("enabled gates all execution of a
    schedule, not only automatic triggering") means a disabled schedule
    can't be fired through either path, deliberately: `INGESTION_ENABLED`
    is one on/off switch for this whole capability, not two independent
    ones for "automatic" vs. "manual."

    Must be called before `APSchedulerService.start()` — that method's
    own `register_all()` only picks up schedules already registered on
    `scheduler` at the moment it runs.
    """
    if morning_pipeline is None:
        logger.info(
            "Market Intelligence Ingestion not registered: embedding_provider or "
            "knowledge_repository unavailable."
        )
        return

    workflow_engine.register_workflow(INGESTION_WORKFLOW_ID, morning_pipeline)
    scheduler.register_schedule(
        Schedule(
            workflow_id=INGESTION_WORKFLOW_ID,
            enabled=settings.ingestion_enabled,
            trigger_type=ScheduleTriggerType.INTERVAL,
            interval_seconds=settings.ingestion_interval_seconds,
            initiated_by="scheduler",
        )
    )
    logger.info(
        "Market Intelligence Ingestion registered (enabled=%s, interval_seconds=%s).",
        settings.ingestion_enabled,
        settings.ingestion_interval_seconds,
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
    entity_resolution_service: EntityResolutionService | None,
    market_snapshot_service: MarketSnapshotService | None = None,
) -> CompanyResearchAgent | None:
    """Construct the Company Research agent, or None if a hard dependency
    is unavailable. `entity_resolution_service` (Milestone 12) and
    `market_snapshot_service` (Milestone 13) are both passed through even
    when None — the agent's own constructor documents that it degrades
    gracefully in both cases (pure semantic retrieval; no market snapshot
    attached), never a reason to withhold the whole agent."""
    if knowledge_hub is None or llm_service is None:
        return None
    return CompanyResearchAgent(
        runtime=runtime,
        knowledge_hub=knowledge_hub,
        llm_service=llm_service,
        prompt_registry=prompt_registry,
        entity_resolver=entity_resolution_service,
        market_snapshot_service=market_snapshot_service,
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


def build_market_data_provider(
    settings: AppSettings, logger: logging.Logger
) -> tuple[MarketDataProvider, bool]:
    """Construct the configured `MarketDataProvider`.

    `settings.market_data_provider` selects the implementation — never
    hardcoded into any caller, which only ever depends on the
    `MarketDataProvider` abstraction (same pattern
    `build_embedding_provider` established in Milestone 11). `"mock"`
    (the default) constructs `MockMarketDataProvider`, preserving every
    pre-Milestone-13 behavior exactly. `"yahoo_finance"` constructs the
    real `YahooFinanceProvider` (Milestone 13) — no API key required (see
    `docs/architecture/MARKET_DATA_ARCHITECTURE.md`). An unrecognized
    value degrades to Mock (logged), not a crash.

    Unlike every other `build_*` function in this module, this one always
    returns a usable, non-None instance — `MockMarketDataProvider` has no
    external dependency that can fail, so there is always a safe
    fallback, even when the real provider is selected but somehow fails
    to construct (this provider takes no credential, so that path is not
    expected to occur in practice, but is still handled rather than
    assumed impossible).

    Returns:
        A `(provider, is_live)` tuple — `is_live` is `True` only when a
        real (non-mock) provider was actually constructed, the signal
        `GET /api/v1/capabilities` uses for its `live_market_data` flag
        (see `app.api.v1.routers.capabilities`).
    """
    if settings.market_data_provider == "yahoo_finance":
        try:
            config = YahooFinanceProviderConfig(
                timeout=settings.market_data_timeout_seconds,
                retry_attempts=settings.market_data_retry_attempts,
                retry_backoff_seconds=settings.market_data_retry_backoff_seconds,
            )
            return YahooFinanceProvider(config), True
        except Exception as exc:  # noqa: BLE001 - an infrastructure/config failure must not crash startup
            logger.warning("Failed to initialize YahooFinanceProvider; falling back to mock: %s", exc)
            return MockMarketDataProvider(), False

    if settings.market_data_provider != "mock":
        logger.warning(
            "Unrecognized MARKET_DATA_PROVIDER %r; falling back to mock.", settings.market_data_provider
        )
    return MockMarketDataProvider(), False


def build_market_snapshot_service(
    market_data_provider: MarketDataProvider,
    entity_resolution_service: EntityResolutionService | None,
    settings: AppSettings,
) -> MarketSnapshotService:
    """Construct the MarketSnapshotService (Milestone 13).

    Always succeeds: `market_data_provider` is never None (see
    `build_market_data_provider` above), and `entity_resolution_service`
    being `None` is handled gracefully by `MarketSnapshotService` itself
    (every lookup reports `ENTITY_NOT_MAPPED` rather than failing).
    """
    cache = InMemoryMarketSnapshotCache(ttl_seconds=settings.market_data_cache_ttl_seconds)
    return MarketSnapshotService(market_data_provider, entity_resolution_service, cache)


def build_portfolio_market_snapshot_service(
    market_snapshot_service: MarketSnapshotService,
    entity_resolution_service: EntityResolutionService | None,
) -> PortfolioMarketSnapshotService:
    """Construct the PortfolioMarketSnapshotService (Milestone 14) — pure
    composition of the already-built `market_snapshot_service` (Milestone
    13) and `entity_resolution_service` (Milestone 12), no new provider or
    cache. Always succeeds: `entity_resolution_service` being `None` is
    handled gracefully (every item reports `ENTITY_NOT_MAPPED`), exactly
    like `build_market_snapshot_service` above."""
    return PortfolioMarketSnapshotService(market_snapshot_service, entity_resolution_service)


def build_market_data_refresh_workflow(
    market_snapshot_service: MarketSnapshotService,
    entity_resolution_service: EntityResolutionService | None,
    event_publisher: EventPublisher | None = None,
) -> MarketDataRefreshWorkflow | None:
    """Construct the Market Data Refresh workflow (Milestone 13), or None
    if `entity_resolution_service` is unavailable — with no canonical
    entities to enumerate, this workflow would always refresh zero
    entities, so it is not registered at all rather than registered as a
    permanent no-op (the same "don't register something with nothing to
    do" judgment `build_morning_pipeline` already applies to its own hard
    dependencies).

    `event_publisher` (Milestone 14, optional) is threaded through so
    every scheduled refresh publishes `MARKET_SNAPSHOT_REFRESHED` — see
    `MarketDataRefreshWorkflow`'s own docstring for why this is a valid
    real-time-event trigger point and an operational script is not.
    """
    if entity_resolution_service is None:
        return None
    return MarketDataRefreshWorkflow(market_snapshot_service, entity_resolution_service, event_publisher)


MARKET_DATA_WORKFLOW_ID = "market_data_refresh"


def register_market_data_schedule(
    workflow_engine: WorkflowEngine,
    scheduler: Scheduler,
    market_data_refresh_workflow: MarketDataRefreshWorkflow | None,
    settings: AppSettings,
    logger: logging.Logger,
) -> None:
    """Register MarketDataRefreshWorkflow with WorkflowEngine and schedule
    it — the same pattern `register_ingestion_schedule` (Milestone 11)
    already established.

    A no-op (logged) if `market_data_refresh_workflow` is None. Otherwise
    always registers the workflow (so
    `Scheduler.run_schedule(MARKET_DATA_WORKFLOW_ID)` — the operational
    "run now" trigger, `backend/scripts/run_market_data_refresh.py` —
    works regardless of whether the automatic timer is on) and always
    registers a Schedule, but with `enabled=settings.market_data_enabled`
    — one on/off switch for the whole capability, not two independent
    ones for "automatic" vs. "manual," matching `Scheduler`'s own
    documented contract.

    Must be called before `APSchedulerService.start()` — see
    `register_ingestion_schedule`'s own docstring for why.
    """
    if market_data_refresh_workflow is None:
        logger.info("Market Data Refresh not registered: entity_resolution_service unavailable.")
        return

    workflow_engine.register_workflow(MARKET_DATA_WORKFLOW_ID, market_data_refresh_workflow)
    scheduler.register_schedule(
        Schedule(
            workflow_id=MARKET_DATA_WORKFLOW_ID,
            enabled=settings.market_data_enabled,
            trigger_type=ScheduleTriggerType.INTERVAL,
            interval_seconds=settings.market_data_refresh_interval_seconds,
            initiated_by="scheduler",
        )
    )
    logger.info(
        "Market Data Refresh registered (enabled=%s, interval_seconds=%s).",
        settings.market_data_enabled,
        settings.market_data_refresh_interval_seconds,
    )


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


def build_continuous_intelligence_thresholds(settings: AppSettings) -> ContinuousIntelligenceThresholds:
    """Build the typed, documented significance thresholds (§3) from
    `AppSettings` — every field here is a named config value, never an
    unexplained literal inside a detector."""
    return ContinuousIntelligenceThresholds(
        market_change_percent_threshold=settings.market_change_threshold,
        news_significance_threshold=settings.news_significance_threshold,
        news_high_confidence_threshold=settings.news_high_confidence_threshold,
        recommendation_score_delta_threshold=settings.recommendation_score_delta_threshold,
        strategy_alignment_delta_threshold=settings.strategy_alignment_delta_threshold,
        suppression_cooldown_minutes=settings.continuous_intelligence_suppression_cooldown_minutes,
        cycle_lock_ttl_seconds=settings.continuous_intelligence_lock_ttl_seconds,
    )


def build_continuous_intelligence_repository(
    logger: logging.Logger,
) -> BaseContinuousIntelligenceStateRepository | None:
    """Construct a PostgreSQL-backed Continuous Intelligence state
    repository (Milestone 16 §2-§5), or `None` on any infrastructure
    failure.

    Same reasoning and same graceful-degradation shape as every other
    `build_*_repository` function in this module. Unlike the hard
    dependencies `build_continuous_intelligence_service` requires, this
    one degrades gracefully at the call site: comparison state,
    suppression, and cycle locking all fall back to their Milestone 15
    in-memory equivalents when this returns `None` — persistence is a
    reliability *enhancement*, not a requirement for the feature to
    function at all (the system already worked, with weaker
    restart-survival guarantees, before this milestone).
    """
    settings = PostgreSQLSettings()
    database_url = settings.database_url or (
        f"postgresql+asyncpg://{settings.user}:{settings.password.get_secret_value()}"
        f"@{settings.host}:{settings.port}/{settings.db}"
    )
    try:
        engine = create_async_engine(database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        return PostgresContinuousIntelligenceStateRepository(session_factory)
    except Exception as exc:  # noqa: BLE001 - an infrastructure failure must not crash startup
        logger.warning("Failed to initialize PostgreSQL continuous intelligence repository: %s", exc)
        return None


def build_continuous_intelligence_state_store(
    repository: BaseContinuousIntelligenceStateRepository | None,
) -> ContinuousIntelligenceStateStore:
    """Postgres-backed when a repository is available (§2, restart-safe),
    in-memory otherwise (Milestone 15 behavior, unchanged)."""
    if repository is None:
        return InMemoryContinuousIntelligenceStateStore()
    return PostgresContinuousIntelligenceStateStore(repository)


def build_continuous_intelligence_suppression(
    repository: BaseContinuousIntelligenceStateRepository | None,
    thresholds: ContinuousIntelligenceThresholds,
) -> Suppression:
    """Postgres-backed when a repository is available (§3, restart-safe),
    in-memory otherwise (Milestone 15 behavior, unchanged)."""
    if repository is None:
        return SuppressionService(thresholds.suppression_cooldown_minutes)
    return PostgresSuppressionService(thresholds.suppression_cooldown_minutes, repository)


def build_continuous_intelligence_lock(
    repository: BaseContinuousIntelligenceStateRepository | None,
    thresholds: ContinuousIntelligenceThresholds,
) -> CycleLock:
    """Postgres-backed (cross-process safe, §5) when a repository is
    available, an in-process `asyncio.Lock` (same-process only) otherwise —
    still real protection for the one case that can occur without a
    durable store (manual trigger racing the scheduler on one process)."""
    if repository is None:
        return InMemoryCycleLock()
    return PostgresCycleLock(repository, lock_ttl_seconds=thresholds.cycle_lock_ttl_seconds)


def build_continuous_intelligence_service(
    *,
    entity_resolution_service: EntityResolutionService | None,
    market_snapshot_service: MarketSnapshotService,
    knowledge_hub: KnowledgeHub | None,
    signal_detection_service: SignalDetectionService | None,
    alert_service: AlertService | None,
    risk_service: RiskAnalyticsService | None,
    recommendation_service: PortfolioRecommendationService | None,
    watchlist_service: WatchlistService,
    settings: AppSettings,
    strategy_service: StrategyEvaluationService | None = None,
    continuous_intelligence_repository: BaseContinuousIntelligenceStateRepository | None = None,
    event_publisher: EventPublisher | None = None,
) -> ContinuousIntelligenceService | None:
    """Construct the ContinuousIntelligenceService, or None if any hard
    dependency is unavailable — the same "don't register something with
    nothing to do" judgment `build_market_data_refresh_workflow` already
    applies: with no canonical entities to enumerate
    (`entity_resolution_service`), or no Signal/Alert/Risk/Recommendation
    service to detect decision-context changes through, this cycle would
    do nothing meaningful every run. `strategy_service` is a soft
    dependency (§12): when `None`, Strategy detection is simply skipped,
    same as when `knowledge_hub` is `None` for News detection.
    """
    if (
        entity_resolution_service is None
        or signal_detection_service is None
        or alert_service is None
        or risk_service is None
        or recommendation_service is None
    ):
        return None
    thresholds = build_continuous_intelligence_thresholds(settings)
    return ContinuousIntelligenceService(
        entity_resolver=entity_resolution_service,
        market_snapshot_service=market_snapshot_service,
        knowledge_hub=knowledge_hub,
        signal_service=signal_detection_service,
        alert_service=alert_service,
        risk_service=risk_service,
        recommendation_service=recommendation_service,
        watchlist_service=watchlist_service,
        strategy_service=strategy_service,
        thresholds=thresholds,
        state=build_continuous_intelligence_state_store(continuous_intelligence_repository),
        suppression=build_continuous_intelligence_suppression(continuous_intelligence_repository, thresholds),
        lock=build_continuous_intelligence_lock(continuous_intelligence_repository, thresholds),
        event_publisher=event_publisher,
    )


def build_continuous_intelligence_workflow(
    service: ContinuousIntelligenceService | None,
) -> ContinuousIntelligenceWorkflow | None:
    if service is None:
        return None
    return ContinuousIntelligenceWorkflow(service)


CONTINUOUS_INTELLIGENCE_WORKFLOW_ID = "continuous_intelligence"


def register_continuous_intelligence_schedule(
    workflow_engine: WorkflowEngine,
    scheduler: Scheduler,
    continuous_intelligence_workflow: ContinuousIntelligenceWorkflow | None,
    settings: AppSettings,
    logger: logging.Logger,
) -> None:
    """Register ContinuousIntelligenceWorkflow with WorkflowEngine and
    schedule it — the same pattern `register_market_data_schedule`
    (Milestone 13) already established, including always registering both
    the workflow (so the operational "run now" trigger,
    `scripts/run_continuous_intelligence.py`, works regardless of the
    automatic timer) and the Schedule itself, gated by one
    `enabled=settings.continuous_intelligence_enabled` switch.

    Must be called before `APSchedulerService.start()` — like every other
    `register_*_schedule` function, and unlike them, this one also depends
    on `watchlist_service`/`signal_detection_service`/`alert_service`/
    `risk_service`/`recommendation_service`/`knowledge_hub` — see
    `bootstrap_application_state`'s own comment at its `ap_scheduler_
    service.start()` call site for why that call was moved later to
    accommodate this.
    """
    if continuous_intelligence_workflow is None:
        logger.info(
            "Continuous Intelligence not registered: entity_resolution_service or a required "
            "decision-context service (signal/alert/risk/recommendation) is unavailable."
        )
        return

    workflow_engine.register_workflow(CONTINUOUS_INTELLIGENCE_WORKFLOW_ID, continuous_intelligence_workflow)
    scheduler.register_schedule(
        Schedule(
            workflow_id=CONTINUOUS_INTELLIGENCE_WORKFLOW_ID,
            enabled=settings.continuous_intelligence_enabled,
            trigger_type=ScheduleTriggerType.INTERVAL,
            interval_seconds=settings.continuous_intelligence_interval_seconds,
            initiated_by="scheduler",
        )
    )
    logger.info(
        "Continuous Intelligence registered (enabled=%s, interval_seconds=%s).",
        settings.continuous_intelligence_enabled,
        settings.continuous_intelligence_interval_seconds,
    )


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

    # `ap_scheduler_service.start()` is deferred until every schedule this
    # application ever registers is present on `scheduler` —
    # `APSchedulerService.start()` -> `register_all()` only picks up
    # schedules already present at the moment it runs. Originally deferred
    # only past `register_ingestion_schedule`/`register_market_data_schedule`;
    # Milestone 15's `register_continuous_intelligence_schedule` additionally
    # depends on `watchlist_service`/`signal_detection_service`/
    # `alert_service`/`risk_service`/`recommendation_service`/`knowledge_hub`,
    # all built later — so the actual `.start()` call site has moved to the
    # end of this function's own service construction, right after
    # `register_continuous_intelligence_schedule` itself.
    workflow_engine, scheduler, ap_scheduler_service = build_scheduler_infrastructure(logger)

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

    # Milestone 16 §8: must run before the first `get_company_reference_data()`
    # call in the process — that function memoizes its result on first call,
    # so applying the overlay any later (including after
    # `build_entity_resolution_service` below) would silently never take
    # effect. A no-op when `canonical_entities_overlay_path` is unset.
    if settings.canonical_entities_overlay_path:
        apply_canonical_entity_overlay_from_path(settings.canonical_entities_overlay_path, logger)

    app.state.settings = settings
    app.state.agent_runtime = runtime
    app.state.knowledge_repository = build_knowledge_repository(settings, logger)
    app.state.embedding_provider = build_embedding_provider(settings, logger)
    app.state.entity_resolution_service = build_entity_resolution_service(settings, logger)
    app.state.news_collector_agent = build_news_collector_agent(runtime, settings)
    app.state.morning_pipeline = build_morning_pipeline(
        app.state.news_collector_agent,
        app.state.embedding_provider,
        app.state.knowledge_repository,
        app.state.entity_resolution_service,
    )
    register_ingestion_schedule(
        workflow_engine, scheduler, app.state.morning_pipeline, settings, logger
    )
    market_data_provider, provider_is_live = build_market_data_provider(settings, logger)
    app.state.market_data_provider = market_data_provider
    app.state.market_data_provider_is_live = provider_is_live
    app.state.market_snapshot_service = build_market_snapshot_service(
        app.state.market_data_provider, app.state.entity_resolution_service, settings
    )
    app.state.portfolio_market_snapshot_service = build_portfolio_market_snapshot_service(
        app.state.market_snapshot_service, app.state.entity_resolution_service
    )
    app.state.market_data_refresh_workflow = build_market_data_refresh_workflow(
        app.state.market_snapshot_service,
        app.state.entity_resolution_service,
        getattr(app.state, "event_publisher", None),
    )
    register_market_data_schedule(
        workflow_engine, scheduler, app.state.market_data_refresh_workflow, settings, logger
    )
    app.state.prompt_registry = build_prompt_registry()
    app.state.knowledge_hub = build_knowledge_hub(app.state.knowledge_repository)
    app.state.llm_service = build_llm_service(logger)
    app.state.company_research_agent = build_company_research_agent(
        runtime,
        app.state.knowledge_hub,
        app.state.llm_service,
        app.state.prompt_registry,
        app.state.entity_resolution_service,
        app.state.market_snapshot_service,
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
    app.state.continuous_intelligence_repository = build_continuous_intelligence_repository(logger)
    app.state.continuous_intelligence_service = build_continuous_intelligence_service(
        entity_resolution_service=app.state.entity_resolution_service,
        market_snapshot_service=app.state.market_snapshot_service,
        knowledge_hub=app.state.knowledge_hub,
        signal_detection_service=app.state.signal_detection_service,
        alert_service=app.state.alert_service,
        risk_service=app.state.risk_service,
        recommendation_service=app.state.recommendation_service,
        watchlist_service=app.state.watchlist_service,
        settings=settings,
        strategy_service=app.state.strategy_service,
        continuous_intelligence_repository=app.state.continuous_intelligence_repository,
        event_publisher=getattr(app.state, "event_publisher", None),
    )
    app.state.continuous_intelligence_workflow = build_continuous_intelligence_workflow(
        app.state.continuous_intelligence_service
    )
    register_continuous_intelligence_schedule(
        workflow_engine, scheduler, app.state.continuous_intelligence_workflow, settings, logger
    )
    if ap_scheduler_service is not None:
        await ap_scheduler_service.start()
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
