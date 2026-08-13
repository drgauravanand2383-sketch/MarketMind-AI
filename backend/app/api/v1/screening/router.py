"""FastAPI router for the Screening API (`/api/v1/screening`).

Profile CRUD handlers are a thin translation: resolve `ScreeningEngine`
via dependency injection, call exactly one of its existing methods, wrap
the result. `ScreeningError` subclasses are never caught here; they
propagate to the centralized domain-exception handler already registered
in Sprint 55/56.

`POST /run` calls the engine's existing, synchronous, stateless
`evaluate_companies()` directly and caches the results in a thin
HTTP-layer-only store purely so `GET /results/{result_id}` has something
to return — see `app.api.v1.screening.schemas`'s module docstring for why
this cache exists and its known limitation (in-process only).

Frontend Milestone 4 additions:
- `POST /profiles/{profile_id}/duplicate` — wraps the already-existing
  `ScreeningEngine.duplicate_profile()`, never reachable over REST before.
- `name` filter on `GET /profiles` — case-insensitive substring match
  against the profile's own `name`, applied in-memory over whatever
  `list_profiles()` already returned, exactly like pagination/sorting
  already are on this endpoint. Mirrors the `name` filter added to
  `GET /watchlists` in Milestone 3 for the identical reason (the
  frontend needed a server-side way to search saved profiles by name).
"""

from __future__ import annotations

import uuid as uuid_module

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.v1.schemas.common import PaginatedResponse, SuccessResponse, build_success_response
from app.api.v1.schemas.pagination import PaginationParams, build_paginated_response, paginate_items, pagination_params
from app.api.v1.schemas.result_store import InMemoryResultStore
from app.api.v1.screening.dependencies import get_screening_engine, get_screening_result_store
from app.api.v1.screening.schemas import (
    CreateScreeningProfileRequest,
    DuplicateScreeningProfileRequest,
    RunScreeningRequest,
    ScreeningRunEnvelope,
    UpdateScreeningProfileRequest,
)
from app.auth.dependencies.policy_guard import require_policy
from app.auth.policies import RequirePermission
from app.screening.engine import ScreeningEngine
from app.screening.models import ScreeningProfile, ScreenResult

__all__ = ["router"]

router = APIRouter(prefix="/screening", tags=["Screening"])

_SORTABLE_FIELDS = frozenset({"name", "created_at", "updated_at"})


def _sort_key(profile: ScreeningProfile, field: str) -> object:
    if field == "name":
        return profile.name.lower()
    return getattr(profile, field)


@router.get(
    "/profiles",
    response_model=PaginatedResponse[ScreeningProfile],
    summary="List screening profiles",
    description="Paginated, sortable list of every screening profile.",
    dependencies=[Depends(require_policy(RequirePermission("screening:read")))],
)
async def list_screening_profiles(
    request: Request,
    pagination: PaginationParams = Depends(pagination_params),
    name: str | None = Query(None, description="Match profiles whose name contains this substring (case-insensitive)."),
    engine: ScreeningEngine = Depends(get_screening_engine),
) -> PaginatedResponse[ScreeningProfile]:
    profiles = await engine.list_profiles()
    if name is not None:
        needle = name.lower()
        profiles = [profile for profile in profiles if needle in profile.name.lower()]
    page_items, total = paginate_items(profiles, pagination, sortable_fields=_SORTABLE_FIELDS, key_fn=_sort_key)
    return build_paginated_response(page_items, total, pagination, request)


@router.post(
    "/profiles",
    response_model=SuccessResponse[ScreeningProfile],
    status_code=status.HTTP_201_CREATED,
    summary="Create a screening profile",
    description="Create a new named screening profile with the given filters and groups.",
    dependencies=[Depends(require_policy(RequirePermission("screening:create")))],
)
async def create_screening_profile(
    request: Request,
    body: CreateScreeningProfileRequest,
    engine: ScreeningEngine = Depends(get_screening_engine),
) -> SuccessResponse[ScreeningProfile]:
    profile = await engine.create_profile(
        body.name,
        description=body.description,
        is_default=body.is_default,
        filters=body.filters,
        groups=body.groups,
    )
    return build_success_response(profile, request)


@router.post(
    "/profiles/{profile_id}/duplicate",
    response_model=SuccessResponse[ScreeningProfile],
    status_code=status.HTTP_201_CREATED,
    summary="Duplicate a screening profile",
    description="Copy an existing profile's filters and groups into a new, separately-named profile.",
    dependencies=[Depends(require_policy(RequirePermission("screening:create")))],
)
async def duplicate_screening_profile(
    request: Request,
    profile_id: uuid_module.UUID,
    body: DuplicateScreeningProfileRequest,
    engine: ScreeningEngine = Depends(get_screening_engine),
) -> SuccessResponse[ScreeningProfile]:
    profile = await engine.duplicate_profile(str(profile_id), body.new_name)
    return build_success_response(profile, request)


@router.patch(
    "/profiles/{profile_id}",
    response_model=SuccessResponse[ScreeningProfile],
    summary="Update a screening profile",
    description="`ScreeningEngine.update_profile` is a whole-object replace — the router fetches the "
    "existing profile, applies only the fields set in the request body, then replaces it.",
    dependencies=[Depends(require_policy(RequirePermission("screening:update")))],
)
async def update_screening_profile(
    request: Request,
    profile_id: uuid_module.UUID,
    body: UpdateScreeningProfileRequest,
    engine: ScreeningEngine = Depends(get_screening_engine),
) -> SuccessResponse[ScreeningProfile]:
    existing = await engine.get_profile(str(profile_id))
    updated = existing.model_copy(update=body.model_dump(exclude_unset=True))
    profile = await engine.update_profile(updated)
    return build_success_response(profile, request)


@router.delete(
    "/profiles/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a screening profile",
    description="Permanently delete a screening profile.",
    dependencies=[Depends(require_policy(RequirePermission("screening:update")))],
)
async def delete_screening_profile(
    profile_id: uuid_module.UUID,
    engine: ScreeningEngine = Depends(get_screening_engine),
) -> None:
    await engine.delete_profile(str(profile_id))


@router.post(
    "/run",
    response_model=SuccessResponse[ScreeningRunEnvelope],
    status_code=status.HTTP_201_CREATED,
    summary="Run a screening",
    description="Evaluates the supplied companies against a screening profile and caches the results for later lookup.",
    dependencies=[Depends(require_policy(RequirePermission("screening:run")))],
)
async def run_screening(
    request: Request,
    body: RunScreeningRequest,
    engine: ScreeningEngine = Depends(get_screening_engine),
    store: InMemoryResultStore = Depends(get_screening_result_store),
) -> SuccessResponse[ScreeningRunEnvelope]:
    profile = await engine.get_profile(body.profile_id)
    results: list[ScreenResult] = engine.evaluate_companies(profile, body.companies)
    result_id = store.put((body.profile_id, results))
    return build_success_response(
        ScreeningRunEnvelope(result_id=result_id, profile_id=body.profile_id, results=results), request
    )


@router.get(
    "/results/{result_id}",
    response_model=SuccessResponse[ScreeningRunEnvelope],
    summary="Get a cached screening run",
    description="Looks up a previously computed screening run by the id returned from POST /screening/run.",
    dependencies=[Depends(require_policy(RequirePermission("screening:read")))],
)
async def get_screening_result(
    request: Request,
    result_id: uuid_module.UUID,
    store: InMemoryResultStore = Depends(get_screening_result_store),
) -> SuccessResponse[ScreeningRunEnvelope]:
    profile_id, results = store.get(str(result_id))
    return build_success_response(
        ScreeningRunEnvelope(result_id=str(result_id), profile_id=profile_id, results=results), request
    )
