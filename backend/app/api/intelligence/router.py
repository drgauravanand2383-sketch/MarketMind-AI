"""FastAPI router for the Intelligence Query API.

Every endpoint here validates its request via FastAPI/Pydantic, creates an
ExecutionContext for the call (where the invoked agent requires one),
invokes the already-implemented agent or workflow, and returns structured
JSON that includes traceability IDs. This module contains no business
logic, never calls a repository directly, and never duplicates any agent's
internal behavior — each handler is a thin translation between HTTP and an
existing `agent.run(...)` / `pipeline.run(...)` call.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.agents.company_research.agent import CompanyResearchAgent
from app.agents.company_research.models import CompanyResearchRequest
from app.agents.portfolio_intelligence.agent import PortfolioIntelligenceAgent
from app.agents.portfolio_intelligence.models import PortfolioIntelligenceRequest
from app.api.intelligence.dependencies import (
    get_company_research_agent,
    get_morning_pipeline,
    get_portfolio_intelligence_agent,
)
from app.api.intelligence.schemas import (
    CompanyResearchResponse,
    HealthResponse,
    MorningRunRequest,
    MorningRunResponse,
    PortfolioResearchResponse,
)
from app.core.context import ExecutionContext, TriggerType, WorkflowStatus
from app.workflows.morning_pipeline.pipeline import MorningPipeline

__all__ = ["router"]

router = APIRouter()

API_VERSION = "0.1.0"


def _build_execution_context(
    workflow_id: str, workflow_type: str, participating_agents: tuple[str, ...]
) -> ExecutionContext:
    """Create a fresh ExecutionContext for one incoming API request."""
    execution_id = str(uuid.uuid4())
    return ExecutionContext(
        workflow_id=workflow_id,
        execution_id=execution_id,
        workflow_type=workflow_type,
        trigger=TriggerType.USER_REQUEST,
        initiated_by="api",
        started_at=datetime.now(timezone.utc),
        trace_id=execution_id,
        participating_agents=participating_agents,
        status=WorkflowStatus.RUNNING,
    )


@router.post("/company/research", response_model=CompanyResearchResponse)
async def research_company(
    request: CompanyResearchRequest,
    agent: CompanyResearchAgent = Depends(get_company_research_agent),
) -> CompanyResearchResponse:
    """Run CompanyResearchAgent (AGT-004) for the requested company."""
    context = _build_execution_context(
        workflow_id="WF-COMPANY-RESEARCH",
        workflow_type="company_research",
        participating_agents=(agent.agent_id,),
    )
    report = await agent.run(context, request)
    return CompanyResearchResponse(
        execution_id=context.execution_id, trace_id=context.trace_id, report=report
    )


@router.post("/portfolio/research", response_model=PortfolioResearchResponse)
async def research_portfolio(
    request: PortfolioIntelligenceRequest,
    agent: PortfolioIntelligenceAgent = Depends(get_portfolio_intelligence_agent),
) -> PortfolioResearchResponse:
    """Run PortfolioIntelligenceAgent (AGT-005) for the requested holdings."""
    context = _build_execution_context(
        workflow_id="WF-PORTFOLIO-INTELLIGENCE",
        workflow_type="portfolio_intelligence",
        participating_agents=(agent.agent_id,),
    )
    report = await agent.run(context, request)
    return PortfolioResearchResponse(
        execution_id=context.execution_id, trace_id=context.trace_id, report=report
    )


@router.post("/morning/run", response_model=MorningRunResponse)
async def run_morning_pipeline(
    request: MorningRunRequest,
    pipeline: MorningPipeline = Depends(get_morning_pipeline),
) -> MorningRunResponse:
    """Run the Morning Intelligence Pipeline end to end.

    Since Sprint 30's WorkflowProtocol standardization, MorningPipeline no
    longer builds its own ExecutionContext — this endpoint builds one, the
    same way it already does for the other two handlers above.
    """
    context = _build_execution_context(
        workflow_id="WF-MORNING-PIPELINE",
        workflow_type="morning_intelligence_pipeline",
        participating_agents=(),
    )
    result = await pipeline.run(context, news_request=request.news_request)
    return MorningRunResponse(
        status=result.status,
        execution_id=result.execution_id,
        started_at=result.started_at,
        completed_at=result.completed_at,
        stage_metrics=result.stage_metrics,
        evidence_graph=result.evidence_graph,
        market_intelligence=result.market_intelligence,
        relationship_graph=result.relationship_graph,
        failed_stage=result.failed_stage,
        error=result.error,
    )


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report basic API liveness. Does not probe downstream dependency health."""
    return HealthResponse(status="ok", version=API_VERSION)
