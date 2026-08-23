"""FastAPI router for the Portfolio API (`/api/v1/portfolio`).

By explicit product decision, "portfolio" has no domain entity of its
own — a `portfolio_id` *is* a `watchlist_id`. Every handler either
delegates directly to `WatchlistService` (list/get/summary), builds a
request from a watchlist's items and calls the existing
`PortfolioIntelligenceAgent` (intelligence), or performs a read-only
lookup of the most-recently-stored `RiskAssessment`/`RecommendationResult`
linked to the watchlist_id (risk, recommendations). No new scoring,
research, or recommendation logic is introduced here.

Domain exceptions (`WatchlistServiceError`, `RiskAnalyticsError`,
`RecommendationEngineError` subclasses) are never caught here; they
propagate to the centralized domain-exception handler already registered
in Sprint 55/56 (`app.api.v1.exception_handlers.handlers`).

Every endpoint requires authentication and a specific permission — see
each route's own `dependencies=[Depends(require_policy(...))]`. No inline
role/permission check exists anywhere in this module.

Literal-path routes (`/summary`, `/intelligence`, `/risk`,
`/recommendations`) are declared before `/{portfolio_id}` — FastAPI
matches routes in registration order, so `/{portfolio_id}` would otherwise
shadow them (e.g. a request to `/portfolio/summary` would match
`/{portfolio_id}` first with `portfolio_id="summary"` and fail UUID
coercion, instead of ever reaching the summary handler).

`create_portfolio_recommendations` (Sprint 59) additionally publishes a
`RECOMMENDATION_GENERATED` real-time event via `EventPublisher`.

v1.2 Priority 8 closed the long-standing gap this docstring used to
document here: no endpoint ever called `RiskAnalyticsService
.assess_portfolio()` for a brand new portfolio, and `POST /portfolio
/recommendations` required client-supplied evidence, so a newly created
watchlist's Risk/Recommendation state stayed empty forever unless a
caller happened to supply its own evidence by hand. `GET /portfolio
/{portfolio_id}/analysis-status` and `POST /portfolio/{portfolio_id}
/analysis` below are the new, minimal surface for that — both delegate
entirely to `InitialPortfolioAnalysisService`
(`app.services.initial_analysis.service`), which composes already-existing
services (Signal Detection, Alerts, Market Snapshot) into the evidence
`generate_recommendations()`/`assess_portfolio()` need; no new scoring or
evaluation logic lives here or in that service. `GET /portfolio/risk`
and `GET /portfolio/recommendations` above remain read-only lookups,
unchanged.
"""

from __future__ import annotations

import uuid as uuid_module
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status

from app.agents.portfolio_intelligence.agent import PortfolioIntelligenceAgent
from app.agents.portfolio_intelligence.models import (
    PortfolioCompanyRequest,
    PortfolioIntelligenceReport,
    PortfolioIntelligenceRequest,
)
from app.api.intelligence.dependencies import get_portfolio_intelligence_agent
from app.api.v1.portfolio.dependencies import (
    get_initial_analysis_service,
    get_portfolio_market_snapshot_service,
    get_recommendation_service,
    get_risk_service,
)
from app.api.v1.portfolio.schemas import GenerateRecommendationsRequest
from app.api.v1.schemas.common import PaginatedResponse, SuccessResponse, build_success_response
from app.api.v1.schemas.filters import WatchlistFilterParams, matches_watchlist_filters, watchlist_filter_params
from app.api.v1.schemas.pagination import PaginationParams, build_paginated_response, paginate_items, pagination_params
from app.api.v1.watchlists.dependencies import get_watchlist_service
from app.api.ws.dependencies.services import get_event_publisher
from app.api.ws.publishers.event_publisher import EventPublisher
from app.auth.dependencies.policy_guard import require_policy
from app.auth.policies import RequirePermission
from app.core.context import ExecutionContext, TriggerType, WorkflowStatus
from app.recommendations.engine import PortfolioRecommendationService
from app.recommendations.exceptions import RecommendationRequestNotFoundError
from app.recommendations.models import RecommendationResult
from app.risk.engine import RiskAnalyticsService
from app.risk.exceptions import RiskAssessmentRequestNotFoundError
from app.risk.models import RiskAssessment
from app.services.initial_analysis.models import InitialAnalysisState
from app.services.initial_analysis.service import InitialPortfolioAnalysisService
from app.services.portfolio_market_snapshot.service import PortfolioMarketSnapshotService
from app.watchlist.models import Watchlist, WatchlistStatistics
from app.watchlist.service import WatchlistService

__all__ = ["router"]

router = APIRouter(prefix="/portfolio", tags=["Portfolio"])

_SORTABLE_FIELDS = frozenset({"name", "created_at", "updated_at"})


def _sort_key(watchlist: Watchlist, field: str) -> object:
    if field == "name":
        return watchlist.name.lower()
    return getattr(watchlist, field)


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
        started_at=datetime.now(timezone.utc),
        trace_id=execution_id,
        participating_agents=participating_agents,
        status=WorkflowStatus.RUNNING,
    )


@router.get(
    "/summary",
    response_model=SuccessResponse[WatchlistStatistics],
    summary="Get portfolio summary statistics",
    description="On-demand confidence/composition statistics — see `WatchlistService.get_statistics`.",
    dependencies=[Depends(require_policy(RequirePermission("portfolio:read")))],
)
async def get_portfolio_summary(
    request: Request,
    portfolio_id: uuid_module.UUID = Query(...),
    service: WatchlistService = Depends(get_watchlist_service),
) -> SuccessResponse[WatchlistStatistics]:
    statistics = await service.get_statistics(str(portfolio_id))
    return build_success_response(statistics, request)


@router.get(
    "/intelligence",
    response_model=SuccessResponse[PortfolioIntelligenceReport],
    summary="Get portfolio intelligence report",
    description="Runs the existing PortfolioIntelligenceAgent over the watchlist's current companies, "
    "attaches a live market snapshot (Milestone 14) via PortfolioMarketSnapshotService — the agent "
    "itself never fetches market data — and publishes a PORTFOLIO_INTELLIGENCE_UPDATED real-time event.",
    dependencies=[Depends(require_policy(RequirePermission("portfolio:read")))],
)
async def get_portfolio_intelligence(
    request: Request,
    portfolio_id: uuid_module.UUID = Query(...),
    watchlist_service: WatchlistService = Depends(get_watchlist_service),
    agent: PortfolioIntelligenceAgent = Depends(get_portfolio_intelligence_agent),
    market_snapshot_service: PortfolioMarketSnapshotService = Depends(get_portfolio_market_snapshot_service),
    event_publisher: EventPublisher = Depends(get_event_publisher),
) -> SuccessResponse[PortfolioIntelligenceReport]:
    watchlist = await watchlist_service.get_watchlist(str(portfolio_id))
    intelligence_request = PortfolioIntelligenceRequest(
        portfolio_name=watchlist.name,
        companies=[
            PortfolioCompanyRequest(
                company_name=item.company_name or item.ticker,
                ticker=item.ticker,
                sector=item.sector,
            )
            for item in watchlist.items
        ],
    )
    context = _build_execution_context(
        workflow_id="WF-PORTFOLIO-INTELLIGENCE",
        workflow_type="portfolio_intelligence",
        participating_agents=(agent.agent_id,),
    )
    report = await agent.run(context, intelligence_request)
    market_snapshot = await market_snapshot_service.get_portfolio_snapshot(watchlist)
    report = report.model_copy(update={"market_snapshot": market_snapshot})
    await event_publisher.publish_portfolio_intelligence_updated(report)
    return build_success_response(report, request)


@router.get(
    "/risk",
    response_model=SuccessResponse[RiskAssessment],
    summary="Get the most recent portfolio risk assessment",
    description="Read-only lookup of the most-recently-stored RiskAssessment for this watchlist. "
    "No new risk assessment is computed here.",
    dependencies=[Depends(require_policy(RequirePermission("portfolio:read")))],
)
async def get_portfolio_risk(
    request: Request,
    portfolio_id: uuid_module.UUID = Query(...),
    service: RiskAnalyticsService = Depends(get_risk_service),
) -> SuccessResponse[RiskAssessment]:
    matching_requests = [r for r in await service.list_requests() if r.portfolio_id == str(portfolio_id)]
    if not matching_requests:
        raise RiskAssessmentRequestNotFoundError(str(portfolio_id))
    latest_request = max(matching_requests, key=lambda r: r.created_at)
    assessment = await service.get_assessment(latest_request.id)
    return build_success_response(assessment, request)


@router.get(
    "/recommendations",
    response_model=SuccessResponse[RecommendationResult],
    summary="Get the most recent portfolio recommendations",
    description="Read-only lookup of the most-recently-stored RecommendationResult for this watchlist. "
    "No new recommendations are generated here — see POST for that.",
    dependencies=[Depends(require_policy(RequirePermission("portfolio:read")))],
)
async def get_portfolio_recommendations(
    request: Request,
    portfolio_id: uuid_module.UUID = Query(...),
    service: PortfolioRecommendationService = Depends(get_recommendation_service),
) -> SuccessResponse[RecommendationResult]:
    matching_requests = [
        r for r in await service.list_requests() if str(portfolio_id) in r.watchlist_ids
    ]
    if not matching_requests:
        raise RecommendationRequestNotFoundError(str(portfolio_id))
    latest_request = max(matching_requests, key=lambda r: r.created_at)
    result = await service.get_result(latest_request.id)
    return build_success_response(result, request)


@router.post(
    "/recommendations",
    response_model=SuccessResponse[RecommendationResult],
    status_code=status.HTTP_201_CREATED,
    summary="Generate portfolio recommendations",
    description="Calls the existing PortfolioRecommendationService.create_request() then "
    "generate_recommendations() using client-supplied candidate evidence.",
    dependencies=[Depends(require_policy(RequirePermission("portfolio:recommend")))],
)
async def create_portfolio_recommendations(
    request: Request,
    body: GenerateRecommendationsRequest,
    service: PortfolioRecommendationService = Depends(get_recommendation_service),
    event_publisher: EventPublisher = Depends(get_event_publisher),
) -> SuccessResponse[RecommendationResult]:
    recommendation_request = await service.create_request(
        request_name=f"portfolio-{body.portfolio_id}-{uuid_module.uuid4()}",
        watchlist_ids=(str(body.portfolio_id),),
        max_recommendations=body.max_recommendations,
        minimum_score=body.minimum_score,
    )
    result = await service.generate_recommendations(recommendation_request, body.evidence)
    await event_publisher.publish_recommendation_generated(result)
    return build_success_response(result, request)


@router.get(
    "/{portfolio_id}/analysis-status",
    response_model=SuccessResponse[InitialAnalysisState],
    summary="Get a portfolio's initial-analysis status",
    description="v1.2 Priority 8: the current status of this portfolio's one-time initial "
    "Risk/Recommendation bootstrap job (ANALYZING/READY/PARTIAL/UNAVAILABLE/ERROR). Read-only — "
    "never computes anything; see POST .../analysis to trigger or retry the job itself. Raises "
    "404 if no watchlist exists for `portfolio_id`.",
    dependencies=[Depends(require_policy(RequirePermission("portfolio:read")))],
)
async def get_portfolio_analysis_status(
    request: Request,
    portfolio_id: uuid_module.UUID,
    service: InitialPortfolioAnalysisService = Depends(get_initial_analysis_service),
) -> SuccessResponse[InitialAnalysisState]:
    state = await service.get_status(str(portfolio_id))
    return build_success_response(state, request)


@router.post(
    "/{portfolio_id}/analysis",
    response_model=SuccessResponse[InitialAnalysisState],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger (or retry) a portfolio's initial Risk/Recommendation analysis",
    description="v1.2 Priority 8: dispatches InitialPortfolioAnalysisService.ensure_initial_analysis() "
    "as a background job and returns immediately with the status as of *before* that job runs — poll "
    "GET .../analysis-status, or watch the existing RECOMMENDATION_GENERATED/RISK_ASSESSMENT_COMPLETED "
    "real-time events, for the outcome. A safe no-op if analysis already exists or is already in "
    "flight for this portfolio; this is the one supported way to retry after a prior attempt ended "
    "in ERROR. Raises 404 if no watchlist exists for `portfolio_id`.",
    dependencies=[Depends(require_policy(RequirePermission("portfolio:recommend")))],
)
async def trigger_portfolio_analysis(
    request: Request,
    portfolio_id: uuid_module.UUID,
    background_tasks: BackgroundTasks,
    service: InitialPortfolioAnalysisService = Depends(get_initial_analysis_service),
) -> SuccessResponse[InitialAnalysisState]:
    state = await service.get_status(str(portfolio_id))
    background_tasks.add_task(service.ensure_initial_analysis, str(portfolio_id))
    return build_success_response(state, request)


@router.get(
    "",
    response_model=PaginatedResponse[Watchlist],
    summary="List portfolios",
    description="Paginated, filterable, sortable list of every portfolio (watchlist).",
    dependencies=[Depends(require_policy(RequirePermission("portfolio:read")))],
)
async def list_portfolios(
    request: Request,
    pagination: PaginationParams = Depends(pagination_params),
    filters: WatchlistFilterParams = Depends(watchlist_filter_params),
    service: WatchlistService = Depends(get_watchlist_service),
) -> PaginatedResponse[Watchlist]:
    watchlists = await service.list_watchlists()
    filtered = [w for w in watchlists if matches_watchlist_filters(w, filters)]
    page_items, total = paginate_items(filtered, pagination, sortable_fields=_SORTABLE_FIELDS, key_fn=_sort_key)
    return build_paginated_response(page_items, total, pagination, request)


@router.get(
    "/{portfolio_id}",
    response_model=SuccessResponse[Watchlist],
    summary="Get a portfolio",
    description="Fetch a single portfolio (watchlist), including its current companies, by id.",
    dependencies=[Depends(require_policy(RequirePermission("portfolio:read")))],
)
async def get_portfolio(
    request: Request,
    portfolio_id: uuid_module.UUID,
    service: WatchlistService = Depends(get_watchlist_service),
) -> SuccessResponse[Watchlist]:
    watchlist = await service.get_watchlist(str(portfolio_id))
    return build_success_response(watchlist, request)
