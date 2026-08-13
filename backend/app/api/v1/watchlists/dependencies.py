"""FastAPI dependency providers for the Watchlist API — resolves
`WatchlistService` from `request.app.state`, the exact pattern
`app.api.v1.dependencies.state` already established for the system
endpoints. Nothing here constructs a service.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.watchlist.service import WatchlistService

__all__ = ["get_watchlist_service"]


def get_watchlist_service(request: Request) -> WatchlistService:
    service = getattr(request.app.state, "watchlist_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WatchlistService is not configured on this application instance.",
        )
    return service
