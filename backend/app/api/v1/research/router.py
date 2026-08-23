"""FastAPI router for the Company Research API (`/api/v1/research`).

Every handler resolves `CompanyResearchAgent` via dependency injection
(reused from `app.api.intelligence.dependencies`, not duplicated), calls
its existing `run()` method, and caches the result in a thin,
HTTP-layer-only `InMemoryResultStore` purely so `GET /{request_id}` has
something to return — see `app.api.v1.research.schemas`'s module
docstring for why this cache exists and its known limitation
(in-process only). No business logic is duplicated or added.

`POST /batch` loops and calls `agent.run()` once per company, reusing one
shared `ExecutionContext` across the loop — the same pattern
`PortfolioIntelligenceAgent.run()` itself already uses internally to
research every company in a portfolio.

Literal-path `/company` and `/batch` are registered before `/{request_id}`
— see `app/api/v1/portfolio/router.py`'s own docstring for why
registration order matters to FastAPI's route matching.
"""

from __future__ import annotations

import uuid as uuid_module
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, status

from app.agents.company_research.agent import CompanyResearchAgent
from app.agents.company_research.models import CompanyResearchReport, CompanyResearchRequest
from app.api.intelligence.dependencies import get_company_research_agent
from app.api.v1.research.dependencies import get_research_report_store
from app.api.v1.research.schemas import BatchCompanyResearchRequest, CompanyResearchReportEnvelope
from app.api.v1.schemas.common import SuccessResponse, build_success_response
from app.api.v1.schemas.result_store import InMemoryResultStore
from app.auth.dependencies.policy_guard import require_policy
from app.auth.policies import RequirePermission
from app.core.context import ExecutionContext, TriggerType, WorkflowStatus

__all__ = ["router"]

router = APIRouter(prefix="/research", tags=["Company Research"])


def _build_execution_context(
    workflow_id: str, workflow_type: str, participating_agents: tuple[str, ...]
) -> ExecutionContext:
    """Create a fresh ExecutionContext for one incoming API request.

    A small, module-local equivalent of `app.api.intelligence.router`'s own
    private `_build_execution_context` — that helper is underscore-prefixed
    (module-private) and is not imported directly.
    """
    execution_id = str(uuid_module.uuid4())
    return ExecutionContext(
        workflow_id=workflow_id,
        execution_id=execution_id,
        workflow_type=workflow_type,
        trigger=TriggerType.USER_REQUEST,
        initiated_by="api",
        started_at=datetime.now(UTC),
        trace_id=execution_id,
        participating_agents=participating_agents,
        status=WorkflowStatus.RUNNING,
    )


@router.post(
    "/company",
    response_model=SuccessResponse[CompanyResearchReportEnvelope],
    status_code=status.HTTP_201_CREATED,
    summary="Run company research",
    description="Runs CompanyResearchAgent for one company and caches the report for later lookup.",
    dependencies=[Depends(require_policy(RequirePermission("research:run")))],
)
async def create_company_research(
    request: Request,
    body: CompanyResearchRequest,
    agent: CompanyResearchAgent = Depends(get_company_research_agent),
    store: InMemoryResultStore[CompanyResearchReport] = Depends(get_research_report_store),
) -> SuccessResponse[CompanyResearchReportEnvelope]:
    context = _build_execution_context(
        workflow_id="WF-COMPANY-RESEARCH", workflow_type="company_research", participating_agents=(agent.agent_id,)
    )
    report = await agent.run(context, body)
    request_id = store.put(report)
    return build_success_response(CompanyResearchReportEnvelope(request_id=request_id, report=report), request)


@router.post(
    "/batch",
    response_model=SuccessResponse[list[CompanyResearchReportEnvelope]],
    status_code=status.HTTP_201_CREATED,
    summary="Run company research for multiple companies",
    description="Runs CompanyResearchAgent once per company and caches each report for later lookup.",
    dependencies=[Depends(require_policy(RequirePermission("research:run")))],
)
async def create_batch_company_research(
    request: Request,
    body: BatchCompanyResearchRequest,
    agent: CompanyResearchAgent = Depends(get_company_research_agent),
    store: InMemoryResultStore[CompanyResearchReport] = Depends(get_research_report_store),
) -> SuccessResponse[list[CompanyResearchReportEnvelope]]:
    context = _build_execution_context(
        workflow_id="WF-COMPANY-RESEARCH-BATCH",
        workflow_type="company_research",
        participating_agents=(agent.agent_id,),
    )
    envelopes = []
    for company_request in body.companies:
        report = await agent.run(context, company_request)
        request_id = store.put(report)
        envelopes.append(CompanyResearchReportEnvelope(request_id=request_id, report=report))
    return build_success_response(envelopes, request)


@router.get(
    "/{request_id}",
    response_model=SuccessResponse[CompanyResearchReportEnvelope],
    summary="Get a cached company research report",
    description="Looks up a previously computed report by the id returned from POST /research/company or /research/batch.",
    dependencies=[Depends(require_policy(RequirePermission("research:read")))],
)
async def get_company_research(
    request: Request,
    request_id: uuid_module.UUID,
    store: InMemoryResultStore[CompanyResearchReport] = Depends(get_research_report_store),
) -> SuccessResponse[CompanyResearchReportEnvelope]:
    report = store.get(str(request_id))
    return build_success_response(CompanyResearchReportEnvelope(request_id=str(request_id), report=report), request)
