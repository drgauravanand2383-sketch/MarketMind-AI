"""HTTP-layer schemas for the Intelligence Query API.

Request bodies reuse the existing agent-level Pydantic models directly
(CompanyResearchRequest, PortfolioIntelligenceRequest) rather than duplicating
them — they are already pure data with no logic attached. Response models
here exist only to (a) carry traceability IDs alongside an agent's report
and (b) present MorningPipeline's result as clean, JSON-safe output,
omitting its internal `final_context` (a frozen dataclass not intended for
external exposure) since `execution_id` already provides top-level
traceability.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.agents.company_research.models import CompanyResearchReport
from app.agents.news_collector.models import NewsCollectionRequest
from app.agents.portfolio_intelligence.models import PortfolioIntelligenceReport
from app.services.evidence_engine.models import EvidenceGraph
from app.services.market_intelligence.models import MarketIntelligence
from app.services.relationship_engine.models import RelationshipGraph
from app.workflows.morning_pipeline.models import PipelineStatus, StageMetric

__all__ = [
    "CompanyResearchResponse",
    "PortfolioResearchResponse",
    "MorningRunRequest",
    "MorningRunResponse",
    "HealthResponse",
]


class CompanyResearchResponse(BaseModel):
    """Response for POST /company/research."""

    model_config = ConfigDict(extra="forbid")

    execution_id: str
    trace_id: str
    report: CompanyResearchReport


class PortfolioResearchResponse(BaseModel):
    """Response for POST /portfolio/research."""

    model_config = ConfigDict(extra="forbid")

    execution_id: str
    trace_id: str
    report: PortfolioIntelligenceReport


class MorningRunRequest(BaseModel):
    """Request body for POST /morning/run."""

    model_config = ConfigDict(extra="forbid")

    news_request: NewsCollectionRequest | None = None


class MorningRunResponse(BaseModel):
    """Response for POST /morning/run — PipelineResult's JSON-safe fields."""

    model_config = ConfigDict(extra="forbid")

    status: PipelineStatus
    execution_id: str
    started_at: datetime
    completed_at: datetime
    stage_metrics: list[StageMetric]
    evidence_graph: EvidenceGraph | None = None
    market_intelligence: MarketIntelligence | None = None
    relationship_graph: RelationshipGraph | None = None
    failed_stage: str | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    """Response for GET /health."""

    model_config = ConfigDict(extra="forbid")

    status: str
    version: str
