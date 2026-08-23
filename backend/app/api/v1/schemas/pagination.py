"""Shared pagination for the `/api/v1` REST API.

Every paginated endpoint reuses `PaginatedResponse[T]` (`app.api.v1.schemas
.common`, defined in Sprint 55, unused until this sprint). Pagination
itself is applied in-memory, over whatever list a domain service's own
method already returned (`WatchlistService.list_watchlists()`, etc.) —
this module never re-implements a service's own logic, only paginates
its output, exactly the same "thin HTTP-layer concern" precedent Sprint
55's own system endpoints already established.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Any

from fastapi import HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.schemas.common import PaginatedResponse, build_metadata, request_id_of

__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "SortDirection",
    "PaginationParams",
    "pagination_params",
    "paginate_items",
    "build_paginated_response",
]

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class SortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


class PaginationParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)
    sort: str | None = None
    direction: SortDirection = SortDirection.ASC


def pagination_params(
    page: int = Query(1, ge=1, description="1-indexed page number."),
    page_size: int = Query(
        DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description=f"Items per page (maximum {MAX_PAGE_SIZE})."
    ),
    sort: str | None = Query(None, description="Field name to sort by. Endpoint-specific allow-list."),
    direction: SortDirection = Query(SortDirection.ASC, description="Sort direction."),
) -> PaginationParams:
    return PaginationParams(page=page, page_size=page_size, sort=sort, direction=direction)


def paginate_items[T](
    items: list[T],
    params: PaginationParams,
    *,
    sortable_fields: frozenset[str],
    key_fn: Callable[[T, str], Any] | None = None,
) -> tuple[list[T], int]:
    """Sort (if `params.sort` is set) and slice `items` for the requested
    page. `total` is the count *before* slicing (after any filtering the
    caller already applied), so a client can compute total pages.

    Raises:
        HTTPException(422): `params.sort` is not in `sortable_fields`.
    """
    if params.sort is not None:
        sort_field = params.sort
        if sort_field not in sortable_fields:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown sort field {sort_field!r}. Must be one of {sorted(sortable_fields)}.",
            )
        resolver: Callable[[T], Any] = (
            (lambda item: key_fn(item, sort_field)) if key_fn is not None else (lambda item: getattr(item, sort_field))
        )
        items = sorted(items, key=resolver, reverse=(params.direction == SortDirection.DESC))

    total = len(items)
    start = (params.page - 1) * params.page_size
    page_items = items[start : start + params.page_size]
    return page_items, total


def build_paginated_response[T](
    data: list[T], total: int, params: PaginationParams, request: Request
) -> PaginatedResponse[T]:
    return PaginatedResponse(
        data=tuple(data), total=total, page=params.page, page_size=params.page_size,
        meta=build_metadata(request_id_of(request)),
    )
