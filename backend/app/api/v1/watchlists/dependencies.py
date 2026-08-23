"""FastAPI dependency providers for the Watchlist API — resolves
`WatchlistService` from `request.app.state`, the exact pattern
`app.api.v1.dependencies.state` already established for the system
endpoints. Nothing here constructs a service.
"""

from __future__ import annotations

from fastapi import Request

from app.api.dependencies.state import resolve_app_state
from app.watchlist.service import WatchlistService

__all__ = ["get_watchlist_service"]


def get_watchlist_service(request: Request) -> WatchlistService:
    return resolve_app_state(request, "watchlist_service", WatchlistService, label="WatchlistService")
