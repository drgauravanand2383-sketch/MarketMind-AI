"""Shared filtering for watchlist/portfolio list endpoints — name,
sector, country, theme, ticker, company, and a created-at date range.

Filtering is applied in-memory over whatever list a domain service's own
method already returned, exactly like `app.api.v1.schemas.pagination` —
never a new query capability added to `WatchlistService`/its repository.
A watchlist matches when it contains at least one `WatchlistItem`
satisfying every *item*-level filter supplied (sector/country/theme/
ticker/company are combined with AND across fields, OR across items);
`name`/`created_after`/`created_before` filter on the watchlist's own
fields directly, not per-item.

`name` (Frontend Milestone 3 addition): case-insensitive substring match
against the watchlist's own `name` — the frontend's watchlist-search box
needed a server-side filter, since every other filter here only matches
watchlist *contents* (holdings), and searching client-side after the
fact would desync the server's own pagination totals. Mirrors the
existing `company` substring-match convention exactly, just at the
watchlist level instead of the item level.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, Query, status
from pydantic import BaseModel, ConfigDict

from app.watchlist.models import Watchlist

__all__ = ["WatchlistFilterParams", "watchlist_filter_params", "matches_watchlist_filters"]


class WatchlistFilterParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str | None = None
    sector: str | None = None
    country: str | None = None
    theme: str | None = None
    ticker: str | None = None
    company: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None


def watchlist_filter_params(
    name: str | None = Query(None, description="Match watchlists whose name contains this substring (case-insensitive)."),
    sector: str | None = Query(None, description="Match watchlists containing a holding in this sector."),
    country: str | None = Query(None, description="Match watchlists containing a holding in this country."),
    theme: str | None = Query(None, description="Match watchlists containing a holding tagged with this theme."),
    ticker: str | None = Query(None, description="Match watchlists containing this ticker."),
    company: str | None = Query(None, description="Match watchlists containing a company name substring (case-insensitive)."),
    created_after: datetime | None = Query(None, description="Only watchlists created at or after this time."),
    created_before: datetime | None = Query(None, description="Only watchlists created at or before this time."),
) -> WatchlistFilterParams:
    params = WatchlistFilterParams(
        name=name, sector=sector, country=country, theme=theme, ticker=ticker, company=company,
        created_after=created_after, created_before=created_before,
    )
    if (
        params.created_after is not None
        and params.created_before is not None
        and params.created_after > params.created_before
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="created_after must not be after created_before.",
        )
    return params


def matches_watchlist_filters(watchlist: Watchlist, filters: WatchlistFilterParams) -> bool:
    if filters.name is not None and filters.name.lower() not in watchlist.name.lower():
        return False
    if filters.created_after is not None and watchlist.created_at < filters.created_after:
        return False
    if filters.created_before is not None and watchlist.created_at > filters.created_before:
        return False

    item_filters_active = any(
        value is not None for value in (filters.sector, filters.country, filters.theme, filters.ticker, filters.company)
    )
    if not item_filters_active:
        return True

    normalized_ticker = filters.ticker.strip().upper() if filters.ticker else None
    for item in watchlist.items:
        if filters.sector is not None and (item.sector or "").lower() != filters.sector.lower():
            continue
        if filters.country is not None and (item.country or "").lower() != filters.country.lower():
            continue
        if filters.theme is not None and (item.theme or "").lower() != filters.theme.lower():
            continue
        if normalized_ticker is not None and item.ticker != normalized_ticker:
            continue
        if filters.company is not None and filters.company.lower() not in (item.company_name or "").lower():
            continue
        return True
    return False
