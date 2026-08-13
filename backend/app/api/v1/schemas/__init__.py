"""HTTP-layer schemas for the `/api/v1` REST API. Pure presentation
models — no business logic. Domain data itself is returned via the
existing domain models directly (`app.operations.health.models
.ApplicationHealth`/`ReadinessStatus`, `app.watchlist.models.Watchlist`,
etc.), wrapped in these envelopes."""

from app.api.v1.schemas.common import (
    ErrorResponse,
    MetadataResponse,
    PaginatedResponse,
    SuccessResponse,
    ValidationErrorFieldError,
    ValidationErrorResponse,
    build_metadata,
    build_success_response,
    request_id_of,
)
from app.api.v1.schemas.filters import (
    WatchlistFilterParams,
    matches_watchlist_filters,
    watchlist_filter_params,
)
from app.api.v1.schemas.pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PaginationParams,
    SortDirection,
    build_paginated_response,
    paginate_items,
    pagination_params,
)
from app.api.v1.schemas.system import (
    CapabilitiesResponse,
    ConfigurationResponse,
    ServiceEntry,
    ServicesResponse,
    VersionResponse,
)

__all__ = [
    "MetadataResponse",
    "SuccessResponse",
    "ErrorResponse",
    "ValidationErrorResponse",
    "ValidationErrorFieldError",
    "PaginatedResponse",
    "build_metadata",
    "build_success_response",
    "request_id_of",
    "VersionResponse",
    "ConfigurationResponse",
    "CapabilitiesResponse",
    "ServiceEntry",
    "ServicesResponse",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "SortDirection",
    "PaginationParams",
    "pagination_params",
    "paginate_items",
    "build_paginated_response",
    "WatchlistFilterParams",
    "watchlist_filter_params",
    "matches_watchlist_filters",
]
