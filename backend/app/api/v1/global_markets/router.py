"""FastAPI router for the Global Market Intelligence API (`/api/v1/global-markets`).

Read-only: every persisted entity here (`IntelligenceRun`, `RankedAsset`,
`CategoryIntelligenceReport`) is produced by the scheduled
`GlobalMarketIntelligenceWorkflow`, never by an API request — there is no
POST/trigger endpoint, deliberately. Every handler is a thin translation:
resolve a repository via dependency injection, call exactly one of its
existing methods, wrap the result. No business logic is duplicated here.

Every repository's own `get_*`/`list_*` methods return `None`/`[]` for a
missing/absent record rather than raising a domain exception (see each
repository's own docstring), so — unlike most other `/api/v1` routers,
which rely on the centralized `handle_domain_error` — a "not found" here
is translated with a direct `raise HTTPException(404, ...)`, the same
already-established pattern `app.api.v1.auth.router` uses for a status
code the shared, naming-convention-based handler doesn't cover.

Literal path `/runs/latest` is registered before `/runs/{run_id}` — same
registration-order requirement `app/api/v1/portfolio/router.py`'s own
docstring documents (FastAPI matches routes in registration order; a
literal segment must precede a variable one at the same path depth or the
variable route would swallow it).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.v1.global_markets.dependencies import (
    get_global_market_ranked_asset_repository,
    get_global_market_report_repository,
    get_global_market_run_repository,
)
from app.api.v1.schemas.common import PaginatedResponse, SuccessResponse, build_success_response
from app.api.v1.schemas.pagination import PaginationParams, build_paginated_response, paginate_items, pagination_params
from app.auth.dependencies.policy_guard import require_policy
from app.auth.policies import RequirePermission
from app.global_markets.intelligence_report import CategoryIntelligenceReport
from app.global_markets.models import (
    REPORT_CATEGORY_DEFINITIONS,
    IntelligenceRun,
    ReportCategory,
    ReportCategoryDefinition,
)
from app.global_markets.ranked_asset import RankedAsset
from app.repositories.global_markets.ranked_asset_repository import BaseRankedAssetRepository
from app.repositories.global_markets.report_repository import BaseIntelligenceReportRepository
from app.repositories.global_markets.repository import BaseGlobalMarketRunRepository

__all__ = ["router"]

router = APIRouter(prefix="/global-markets", tags=["Global Markets"])

_READ_PERMISSION = Depends(require_policy(RequirePermission("global_markets:read")))

_RUN_SORTABLE_FIELDS = frozenset({"run_date", "status", "started_at"})
_RANKED_ASSET_SORTABLE_FIELDS = frozenset({"rank", "final_score", "ticker"})
_REPORT_SORTABLE_FIELDS = frozenset({"category", "generated_at"})


def _ranked_asset_sort_key(asset: RankedAsset, field: str) -> object:
    if field == "ticker":
        return asset.snapshot.ticker
    return getattr(asset, field)


@router.get(
    "/categories",
    response_model=SuccessResponse[tuple[ReportCategoryDefinition, ...]],
    summary="List report categories",
    description="The nine fixed reporting categories and their (market_region, asset_class, top_n) definitions.",
    dependencies=[_READ_PERMISSION],
)
async def list_categories(request: Request) -> SuccessResponse[tuple[ReportCategoryDefinition, ...]]:
    return build_success_response(tuple(REPORT_CATEGORY_DEFINITIONS.values()), request)


@router.get(
    "/runs",
    response_model=PaginatedResponse[IntelligenceRun],
    summary="List intelligence runs",
    description="Every stored Global Market Intelligence run, most recent run_date first.",
    dependencies=[_READ_PERMISSION],
)
async def list_runs(
    request: Request,
    pagination: PaginationParams = Depends(pagination_params),
    repository: BaseGlobalMarketRunRepository = Depends(get_global_market_run_repository),
) -> PaginatedResponse[IntelligenceRun]:
    runs = await repository.list_runs()
    page_items, total = paginate_items(runs, pagination, sortable_fields=_RUN_SORTABLE_FIELDS)
    return build_paginated_response(page_items, total, pagination, request)


@router.get(
    "/runs/latest",
    response_model=SuccessResponse[IntelligenceRun],
    summary="Get the most recent intelligence run",
    description="The most recently stored run, or 404 if no run has ever completed.",
    dependencies=[_READ_PERMISSION],
)
async def get_latest_run(
    request: Request,
    repository: BaseGlobalMarketRunRepository = Depends(get_global_market_run_repository),
) -> SuccessResponse[IntelligenceRun]:
    runs = await repository.list_runs()
    if not runs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No intelligence run has been stored yet.")
    return build_success_response(runs[0], request)


@router.get(
    "/runs/{run_id}",
    response_model=SuccessResponse[IntelligenceRun],
    summary="Get an intelligence run",
    description="Fetch one Global Market Intelligence run by id.",
    dependencies=[_READ_PERMISSION],
)
async def get_run(
    request: Request,
    run_id: str,
    repository: BaseGlobalMarketRunRepository = Depends(get_global_market_run_repository),
) -> SuccessResponse[IntelligenceRun]:
    run = await repository.get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No intelligence run found for id {run_id!r}."
        )
    return build_success_response(run, request)


@router.get(
    "/runs/{run_id}/ranked-assets",
    response_model=PaginatedResponse[RankedAsset],
    summary="List ranked assets for a run",
    description="Every ranked asset across all nine categories for one run.",
    dependencies=[_READ_PERMISSION],
)
async def list_ranked_assets_for_run(
    request: Request,
    run_id: str,
    pagination: PaginationParams = Depends(pagination_params),
    repository: BaseRankedAssetRepository = Depends(get_global_market_ranked_asset_repository),
) -> PaginatedResponse[RankedAsset]:
    assets = await repository.list_ranked_assets_for_run(run_id)
    page_items, total = paginate_items(
        assets, pagination, sortable_fields=_RANKED_ASSET_SORTABLE_FIELDS, key_fn=_ranked_asset_sort_key
    )
    return build_paginated_response(page_items, total, pagination, request)


@router.get(
    "/runs/{run_id}/reports",
    response_model=PaginatedResponse[CategoryIntelligenceReport],
    summary="List narrative reports for a run",
    description="Every LLM-generated narrative report across all categories for one run.",
    dependencies=[_READ_PERMISSION],
)
async def list_reports_for_run(
    request: Request,
    run_id: str,
    pagination: PaginationParams = Depends(pagination_params),
    repository: BaseIntelligenceReportRepository = Depends(get_global_market_report_repository),
) -> PaginatedResponse[CategoryIntelligenceReport]:
    reports = await repository.list_reports_for_run(run_id)
    page_items, total = paginate_items(reports, pagination, sortable_fields=_REPORT_SORTABLE_FIELDS)
    return build_paginated_response(page_items, total, pagination, request)


@router.get(
    "/runs/{run_id}/categories/{category}/ranked-assets",
    response_model=PaginatedResponse[RankedAsset],
    summary="List ranked assets for one category of a run",
    description="The Top-N ranked assets for one report category of one run, ordered by rank.",
    dependencies=[_READ_PERMISSION],
)
async def list_ranked_assets_for_category(
    request: Request,
    run_id: str,
    category: ReportCategory,
    pagination: PaginationParams = Depends(pagination_params),
    repository: BaseRankedAssetRepository = Depends(get_global_market_ranked_asset_repository),
) -> PaginatedResponse[RankedAsset]:
    assets = await repository.list_ranked_assets(run_id, category)
    page_items, total = paginate_items(
        assets, pagination, sortable_fields=_RANKED_ASSET_SORTABLE_FIELDS, key_fn=_ranked_asset_sort_key
    )
    return build_paginated_response(page_items, total, pagination, request)


@router.get(
    "/runs/{run_id}/categories/{category}/report",
    response_model=SuccessResponse[CategoryIntelligenceReport],
    summary="Get one category's narrative report for a run",
    description="The LLM-generated narrative report for one category of one run, or 404 if none was generated.",
    dependencies=[_READ_PERMISSION],
)
async def get_report_for_category(
    request: Request,
    run_id: str,
    category: ReportCategory,
    repository: BaseIntelligenceReportRepository = Depends(get_global_market_report_repository),
) -> SuccessResponse[CategoryIntelligenceReport]:
    report = await repository.get_report(run_id, category)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No narrative report found for run {run_id!r}, category {category.value!r}.",
        )
    return build_success_response(report, request)
