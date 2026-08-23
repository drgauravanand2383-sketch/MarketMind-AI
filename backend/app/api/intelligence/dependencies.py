"""FastAPI dependency providers for the Intelligence Query API.

Every provider function here resolves an already-configured component —
from the FastAPI application's `state` for infrastructure singletons
(AgentRuntime, the Knowledge Repository, the Embedding Provider, the News
Collector agent), or by composing already-implemented agents/services for
the rest. This module never contains business logic, never talks to a
repository directly, and never duplicates any agent's internal behavior —
it only wires already-built components together for HTTP handlers to use.

No production-ready concrete BaseKnowledgeRepository or
BaseEmbeddingProvider exists yet (both remain intentionally abstract per
their own sprints), so the base-level providers below return a clear 503
if the application hasn't been configured with real instances at startup.
Tests use FastAPI's `app.dependency_overrides` to substitute test doubles.
"""

from __future__ import annotations

from fastapi import Depends, Request

from app.agents.company_research.agent import CompanyResearchAgent
from app.agents.news_collector.agent import NewsCollectorAgent
from app.agents.portfolio_intelligence.agent import PortfolioIntelligenceAgent
from app.api.dependencies.state import resolve_app_state
from app.core.runtime import AgentRuntime
from app.providers.embedding.provider import BaseEmbeddingProvider
from app.repositories.knowledge.repository import BaseKnowledgeRepository
from app.services.embedding.service import EmbeddingService
from app.services.evidence_engine.engine import EvidenceEngine
from app.services.knowledge_ingestion.service import KnowledgeIngestionService
from app.services.market_intelligence.engine import MarketIntelligenceEngine
from app.services.relationship_engine.engine import RelationshipEngine
from app.workflows.morning_pipeline.pipeline import MorningPipeline

__all__ = [
    "get_agent_runtime",
    "get_knowledge_repository",
    "get_embedding_provider",
    "get_news_collector_agent",
    "get_company_research_agent",
    "get_portfolio_intelligence_agent",
    "get_morning_pipeline",
]


def get_agent_runtime(request: Request) -> AgentRuntime:
    """Resolve the shared AgentRuntime configured at application startup."""
    return resolve_app_state(request, "agent_runtime", AgentRuntime, label="AgentRuntime")


def get_knowledge_repository(request: Request) -> BaseKnowledgeRepository:
    """Resolve the shared Knowledge Repository configured at application startup."""
    # BaseKnowledgeRepository is an ABC — resolve_app_state's `expected_type:
    # type[T]` requires a concrete/instantiable class even though the value
    # is never actually instantiated inside it, only used to infer `T`.
    return resolve_app_state(request, "knowledge_repository", BaseKnowledgeRepository, label="Knowledge Repository")  # type: ignore[type-abstract]


def get_embedding_provider(request: Request) -> BaseEmbeddingProvider:
    """Resolve the shared Embedding Provider configured at application startup."""
    return resolve_app_state(request, "embedding_provider", BaseEmbeddingProvider, label="Embedding Provider")  # type: ignore[type-abstract]


def get_news_collector_agent(request: Request) -> NewsCollectorAgent:
    """Resolve the shared News Collector agent configured at application startup."""
    return resolve_app_state(request, "news_collector_agent", NewsCollectorAgent, label="News Collector agent")


def get_company_research_agent(request: Request) -> CompanyResearchAgent:
    """Resolve the shared CompanyResearchAgent configured at application startup."""
    return resolve_app_state(request, "company_research_agent", CompanyResearchAgent, label="CompanyResearchAgent")


def get_portfolio_intelligence_agent(request: Request) -> PortfolioIntelligenceAgent:
    """Resolve the shared PortfolioIntelligenceAgent configured at application startup."""
    return resolve_app_state(
        request, "portfolio_intelligence_agent", PortfolioIntelligenceAgent, label="PortfolioIntelligenceAgent"
    )


def get_morning_pipeline(
    news_collector: NewsCollectorAgent = Depends(get_news_collector_agent),
    knowledge_repository: BaseKnowledgeRepository = Depends(get_knowledge_repository),
    embedding_provider: BaseEmbeddingProvider = Depends(get_embedding_provider),
) -> MorningPipeline:
    """Construct a MorningPipeline for this request from injected dependencies."""
    return MorningPipeline(
        news_collector=news_collector,
        ingestion_service=KnowledgeIngestionService(),
        embedding_service=EmbeddingService(),
        embedding_provider=embedding_provider,
        knowledge_repository=knowledge_repository,
        evidence_engine=EvidenceEngine(),
        market_intelligence_engine=MarketIntelligenceEngine(),
        relationship_engine=RelationshipEngine(),
    )
