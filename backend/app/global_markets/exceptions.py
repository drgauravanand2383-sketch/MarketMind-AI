"""Exception hierarchy for Global Market Intelligence.

One base class (`GlobalMarketsError`) so a future `/api/v1/global-markets`
router can register it once against the centralized `handle_domain_error`
handler, exactly like every other domain package's own base exception
class (see `app.api.v1.exception_handlers.handlers`) — not introduced in
Phase 1 itself, but the exception hierarchy is created now so later
phases never need to retrofit one.
"""

from __future__ import annotations

__all__ = [
    "GlobalMarketsError",
    "UnsupportedMarketRegionError",
    "TradingCalendarUnavailableError",
]


class GlobalMarketsError(Exception):
    """Base class for every Global Market Intelligence error."""


class UnsupportedMarketRegionError(GlobalMarketsError):
    """Raised when a `MarketRegion` has no registered `TradingCalendarProvider`."""

    def __init__(self, market_region: object) -> None:
        self.market_region = market_region
        super().__init__(f"No TradingCalendarProvider registered for market region {market_region!r}")


class TradingCalendarUnavailableError(GlobalMarketsError):
    """Raised when a calendar provider fails to resolve session data for a market."""

    def __init__(self, market_region: object, reason: str) -> None:
        self.market_region = market_region
        self.reason = reason
        super().__init__(f"Trading calendar unavailable for {market_region!r}: {reason}")
