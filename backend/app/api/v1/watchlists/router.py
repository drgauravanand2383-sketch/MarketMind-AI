"""FastAPI router for the Watchlist API (`/api/v1/watchlists`).

Every handler is a thin translation: resolve `WatchlistService` via
dependency injection, call exactly one of its existing methods, wrap the
result. No business logic is duplicated — `WatchlistNotFoundError`/
`DuplicateTickerError`/`TickerNotFoundError`/`WatchlistSizeLimitExceededError`/
`WatchlistValidationError` (all `WatchlistServiceError` subclasses) are
never caught here; they propagate to the centralized domain-exception
handler already registered in Sprint 55/56
(`app.api.v1.exception_handlers.handlers`), which maps them to 404/409/400
by the same naming convention every other domain package already follows.

Every endpoint requires authentication and a specific permission — see
each route's own `dependencies=[Depends(require_policy(...))]`. No inline
role/permission check exists anywhere in this module.

`PATCH /{watchlist_id}/companies/{ticker}/notes` (Frontend Milestone 3
addition): `WatchlistService.update_notes()` existed since the service
was first built but was never reachable over REST — `AddCompanyRequest.
notes` could only be set once, at add-time. Same "thin wrapper, no new
logic" shape as every other handler here.

`POST /{watchlist_id}/companies` (v1.2 Priority 8 addition): after a
company is successfully added, dispatches `InitialPortfolioAnalysisService
.ensure_initial_analysis()` as a `BackgroundTasks` job — the point at
which a watchlist first has something to evaluate. Fire-and-forget and
best-effort only: if the service isn't configured on this instance
(`app.state.initial_analysis_service is None`), the company is still
added and the response is still 200 — this is a side effect, never a
requirement for `add_company` itself to succeed. The job is internally
idempotent (`app.services.initial_analysis.service`'s own docstring), so
dispatching it on every add is always safe, never a source of duplicate
Risk/Recommendation state.
"""

from __future__ import annotations

import uuid as uuid_module
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Path, Request, status

from app.api.v1.schemas.common import PaginatedResponse, SuccessResponse, build_success_response
from app.api.v1.schemas.filters import (
    WatchlistFilterParams,
    matches_watchlist_filters,
    watchlist_filter_params,
)
from app.api.v1.schemas.pagination import (
    PaginationParams,
    build_paginated_response,
    paginate_items,
    pagination_params,
)
from app.api.v1.watchlists.dependencies import get_watchlist_service
from app.api.v1.watchlists.schemas import (
    AddCompanyRequest,
    CreateWatchlistRequest,
    RenameWatchlistRequest,
    UpdateNotesRequest,
)
from app.auth.dependencies.policy_guard import require_policy
from app.auth.policies import RequirePermission
from app.watchlist.models import Watchlist, WatchlistItem, WatchlistSnapshot
from app.watchlist.service import WatchlistService

__all__ = ["router"]

router = APIRouter(prefix="/watchlists", tags=["Watchlists"])

_SORTABLE_FIELDS = frozenset({"name", "created_at", "updated_at"})

_TICKER_PATH_PATTERN = r"^[A-Za-z0-9.\-]{1,10}$"


def _sort_key(watchlist: Watchlist, field: str) -> object:
    if field == "name":
        return watchlist.name.lower()
    return getattr(watchlist, field)


@router.get(
    "",
    response_model=PaginatedResponse[Watchlist],
    summary="List watchlists",
    description="Paginated, filterable, sortable list of every watchlist.",
    dependencies=[Depends(require_policy(RequirePermission("watchlist:read")))],
)
async def list_watchlists(
    request: Request,
    pagination: PaginationParams = Depends(pagination_params),
    filters: WatchlistFilterParams = Depends(watchlist_filter_params),
    service: WatchlistService = Depends(get_watchlist_service),
) -> PaginatedResponse[Watchlist]:
    watchlists = await service.list_watchlists()
    filtered = [w for w in watchlists if matches_watchlist_filters(w, filters)]
    page_items, total = paginate_items(filtered, pagination, sortable_fields=_SORTABLE_FIELDS, key_fn=_sort_key)
    return build_paginated_response(page_items, total, pagination, request)


@router.post(
    "",
    response_model=SuccessResponse[Watchlist],
    status_code=status.HTTP_201_CREATED,
    summary="Create a watchlist",
    description="Create a new, empty watchlist with the given name and optional description.",
    dependencies=[Depends(require_policy(RequirePermission("watchlist:create")))],
)
async def create_watchlist(
    request: Request,
    body: CreateWatchlistRequest,
    service: WatchlistService = Depends(get_watchlist_service),
) -> SuccessResponse[Watchlist]:
    watchlist = await service.create_watchlist(body.name, body.description)
    return build_success_response(watchlist, request)


@router.get(
    "/{watchlist_id}",
    response_model=SuccessResponse[Watchlist],
    summary="Get a watchlist",
    description="Fetch a single watchlist, including its current companies, by id.",
    dependencies=[Depends(require_policy(RequirePermission("watchlist:read")))],
)
async def get_watchlist(
    request: Request,
    watchlist_id: uuid_module.UUID,
    service: WatchlistService = Depends(get_watchlist_service),
) -> SuccessResponse[Watchlist]:
    watchlist = await service.get_watchlist(str(watchlist_id))
    return build_success_response(watchlist, request)


@router.patch(
    "/{watchlist_id}",
    response_model=SuccessResponse[Watchlist],
    summary="Rename a watchlist",
    description="The only update `WatchlistService` exposes is a rename.",
    dependencies=[Depends(require_policy(RequirePermission("watchlist:update")))],
)
async def rename_watchlist(
    request: Request,
    watchlist_id: uuid_module.UUID,
    body: RenameWatchlistRequest,
    service: WatchlistService = Depends(get_watchlist_service),
) -> SuccessResponse[Watchlist]:
    watchlist = await service.rename_watchlist(str(watchlist_id), body.name)
    return build_success_response(watchlist, request)


@router.delete(
    "/{watchlist_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a watchlist",
    description="Permanently delete a watchlist and every company tracked within it.",
    dependencies=[Depends(require_policy(RequirePermission("watchlist:delete")))],
)
async def delete_watchlist(
    watchlist_id: uuid_module.UUID,
    service: WatchlistService = Depends(get_watchlist_service),
) -> None:
    await service.delete_watchlist(str(watchlist_id))


@router.post(
    "/{watchlist_id}/companies",
    response_model=SuccessResponse[Watchlist],
    status_code=status.HTTP_201_CREATED,
    summary="Add a company to a watchlist",
    description="Track a new company on this watchlist by ticker. Fails with 409 if the ticker is already tracked.",
    dependencies=[Depends(require_policy(RequirePermission("watchlist:create")))],
)
async def add_company(
    request: Request,
    watchlist_id: uuid_module.UUID,
    body: AddCompanyRequest,
    background_tasks: BackgroundTasks,
    service: WatchlistService = Depends(get_watchlist_service),
) -> SuccessResponse[Watchlist]:
    item = WatchlistItem(**body.model_dump(), added_at=datetime.now(UTC))
    watchlist = await service.add_company(str(watchlist_id), item)

    initial_analysis_service = getattr(request.app.state, "initial_analysis_service", None)
    if initial_analysis_service is not None:
        background_tasks.add_task(initial_analysis_service.ensure_initial_analysis, str(watchlist_id))

    return build_success_response(watchlist, request)


@router.delete(
    "/{watchlist_id}/companies/{ticker}",
    response_model=SuccessResponse[Watchlist],
    summary="Remove a company from a watchlist",
    description="Stop tracking a company on this watchlist by ticker.",
    dependencies=[Depends(require_policy(RequirePermission("watchlist:delete")))],
)
async def remove_company(
    request: Request,
    watchlist_id: uuid_module.UUID,
    ticker: str = Path(..., pattern=_TICKER_PATH_PATTERN),
    service: WatchlistService = Depends(get_watchlist_service),
) -> SuccessResponse[Watchlist]:
    watchlist = await service.remove_company(str(watchlist_id), ticker.strip().upper())
    return build_success_response(watchlist, request)


@router.patch(
    "/{watchlist_id}/companies/{ticker}/notes",
    response_model=SuccessResponse[Watchlist],
    summary="Update a company's notes",
    description="Replace the free-text notes on a company already tracked in this watchlist.",
    dependencies=[Depends(require_policy(RequirePermission("watchlist:update")))],
)
async def update_company_notes(
    request: Request,
    watchlist_id: uuid_module.UUID,
    body: UpdateNotesRequest,
    ticker: str = Path(..., pattern=_TICKER_PATH_PATTERN),
    service: WatchlistService = Depends(get_watchlist_service),
) -> SuccessResponse[Watchlist]:
    watchlist = await service.update_notes(str(watchlist_id), ticker.strip().upper(), body.notes)
    return build_success_response(watchlist, request)


@router.get(
    "/{watchlist_id}/snapshot",
    response_model=SuccessResponse[WatchlistSnapshot],
    summary="Generate a watchlist snapshot",
    description="A fresh, persisted point-in-time intelligence snapshot — see `WatchlistService.generate_snapshot`.",
    dependencies=[Depends(require_policy(RequirePermission("watchlist:read")))],
)
async def get_watchlist_snapshot(
    request: Request,
    watchlist_id: uuid_module.UUID,
    service: WatchlistService = Depends(get_watchlist_service),
) -> SuccessResponse[WatchlistSnapshot]:
    snapshot = await service.generate_snapshot(str(watchlist_id))
    return build_success_response(snapshot, request)
