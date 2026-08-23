"""FastAPI router for the Signal Detection API (`/api/v1/signals`).

Definition CRUD handlers are a thin translation: resolve
`SignalDetectionService` via dependency injection, call exactly one of
its existing methods, wrap the result. `SignalError` subclasses are never
caught here; they propagate to the centralized domain-exception handler
already registered in Sprint 55/56.

`POST /evaluate` calls the service's existing, synchronous, stateless
`evaluate_companies()` directly and caches the batch result in a thin
HTTP-layer-only store purely so `GET /results/{result_id}` has something
to return — see `app.api.v1.signals.schemas`'s module docstring for why
this cache exists and its known limitation (in-process only).
"""

from __future__ import annotations

import uuid as uuid_module

from fastapi import APIRouter, Depends, Request, status

from app.api.v1.schemas.common import PaginatedResponse, SuccessResponse, build_success_response
from app.api.v1.schemas.pagination import PaginationParams, build_paginated_response, paginate_items, pagination_params
from app.api.v1.schemas.result_store import InMemoryResultStore
from app.api.v1.signals.dependencies import get_signal_detection_service, get_signal_result_store
from app.api.v1.signals.schemas import (
    CreateSignalDefinitionRequest,
    EvaluateSignalsRequest,
    SignalEvaluationEnvelope,
    UpdateSignalDefinitionRequest,
)
from app.auth.dependencies.policy_guard import require_policy
from app.auth.policies import RequirePermission
from app.signals.engine import SignalDetectionService
from app.signals.models import SignalBatchResult, SignalDefinition

__all__ = ["router"]

router = APIRouter(prefix="/signals", tags=["Signal Detection"])

_SORTABLE_FIELDS = frozenset({"name", "created_at", "updated_at"})


def _sort_key(definition: SignalDefinition, field: str) -> object:
    if field == "name":
        return definition.name.lower()
    return getattr(definition, field)


@router.get(
    "/definitions",
    response_model=PaginatedResponse[SignalDefinition],
    summary="List signal definitions",
    description="Paginated, sortable list of every signal definition.",
    dependencies=[Depends(require_policy(RequirePermission("signals:read")))],
)
async def list_signal_definitions(
    request: Request,
    pagination: PaginationParams = Depends(pagination_params),
    service: SignalDetectionService = Depends(get_signal_detection_service),
) -> PaginatedResponse[SignalDefinition]:
    definitions = await service.list_signal_definitions()
    page_items, total = paginate_items(definitions, pagination, sortable_fields=_SORTABLE_FIELDS, key_fn=_sort_key)
    return build_paginated_response(page_items, total, pagination, request)


@router.post(
    "/definitions",
    response_model=SuccessResponse[SignalDefinition],
    status_code=status.HTTP_201_CREATED,
    summary="Create a signal definition",
    description="Create a new named signal definition with the given conditions and groups.",
    dependencies=[Depends(require_policy(RequirePermission("signals:update")))],
)
async def create_signal_definition(
    request: Request,
    body: CreateSignalDefinitionRequest,
    service: SignalDetectionService = Depends(get_signal_detection_service),
) -> SuccessResponse[SignalDefinition]:
    definition = await service.create_signal_definition(
        body.name,
        description=body.description,
        category=body.category,
        priority=body.priority,
        enabled=body.enabled,
        conditions=body.conditions,
        groups=body.groups,
    )
    return build_success_response(definition, request)


@router.patch(
    "/definitions/{definition_id}",
    response_model=SuccessResponse[SignalDefinition],
    summary="Update a signal definition",
    description="`SignalDetectionService.update_signal_definition` is a whole-object replace — the "
    "router fetches the existing definition, applies only the fields set in the request body, then replaces it.",
    dependencies=[Depends(require_policy(RequirePermission("signals:update")))],
)
async def update_signal_definition(
    request: Request,
    definition_id: uuid_module.UUID,
    body: UpdateSignalDefinitionRequest,
    service: SignalDetectionService = Depends(get_signal_detection_service),
) -> SuccessResponse[SignalDefinition]:
    existing = await service.get_signal_definition(str(definition_id))
    updated = existing.model_copy(update=body.model_dump(exclude_unset=True))
    definition = await service.update_signal_definition(updated)
    return build_success_response(definition, request)


@router.delete(
    "/definitions/{definition_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a signal definition",
    description="Permanently delete a signal definition.",
    dependencies=[Depends(require_policy(RequirePermission("signals:update")))],
)
async def delete_signal_definition(
    definition_id: uuid_module.UUID,
    service: SignalDetectionService = Depends(get_signal_detection_service),
) -> None:
    await service.delete_signal_definition(str(definition_id))


@router.post(
    "/evaluate",
    response_model=SuccessResponse[SignalEvaluationEnvelope],
    status_code=status.HTTP_201_CREATED,
    summary="Evaluate a signal definition against market data",
    description="Evaluates the supplied market data snapshots against a signal definition and caches the result for later lookup.",
    dependencies=[Depends(require_policy(RequirePermission("signals:evaluate")))],
)
async def evaluate_signals(
    request: Request,
    body: EvaluateSignalsRequest,
    service: SignalDetectionService = Depends(get_signal_detection_service),
    store: InMemoryResultStore[tuple[str, SignalBatchResult]] = Depends(get_signal_result_store),
) -> SuccessResponse[SignalEvaluationEnvelope]:
    definition = await service.get_signal_definition(body.definition_id)
    batch_result = service.evaluate_companies(body.snapshots, definition)
    result_id = store.put((body.definition_id, batch_result))
    return build_success_response(
        SignalEvaluationEnvelope(result_id=result_id, definition_id=body.definition_id, batch_result=batch_result),
        request,
    )


@router.get(
    "/results/{result_id}",
    response_model=SuccessResponse[SignalEvaluationEnvelope],
    summary="Get a cached signal evaluation",
    description="Looks up a previously computed signal evaluation by the id returned from POST /signals/evaluate.",
    dependencies=[Depends(require_policy(RequirePermission("signals:read")))],
)
async def get_signal_result(
    request: Request,
    result_id: uuid_module.UUID,
    store: InMemoryResultStore[tuple[str, SignalBatchResult]] = Depends(get_signal_result_store),
) -> SuccessResponse[SignalEvaluationEnvelope]:
    definition_id, batch_result = store.get(str(result_id))
    return build_success_response(
        SignalEvaluationEnvelope(result_id=str(result_id), definition_id=definition_id, batch_result=batch_result),
        request,
    )
