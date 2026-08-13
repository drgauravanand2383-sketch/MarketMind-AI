"""Watchlist API (`/api/v1/watchlists`, Sprint 57): exposes
`app.watchlist.service.WatchlistService` — every endpoint delegates
directly to an existing method; no business logic is duplicated."""

from app.api.v1.watchlists.router import router

__all__ = ["router"]
