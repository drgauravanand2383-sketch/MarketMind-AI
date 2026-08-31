"""TradingCalendarRegistry — resolves the correct `TradingCalendarProvider`
for a `MarketRegion`.

Distinct from `app.providers.registry.ProviderRegistry` (a general
provider-class registry constructing instances on demand from a plugin
map): this registry holds five already-constructed provider *instances*
(one per `MarketRegion`, a fixed, closed set — new asset classes per
approved Decision 2/§I extensibility notes still only ever add one more
entry here, never a redesign) rather than registering provider classes by
string id. A lighter shape for a smaller, fixed problem — introducing
`ProviderRegistry`'s full class-registration machinery here would be
unnecessary indirection for five fixed, known regions.
"""

from __future__ import annotations

from app.global_markets.calendar.provider import TradingCalendarProvider
from app.global_markets.exceptions import UnsupportedMarketRegionError
from app.global_markets.models import MarketRegion

__all__ = ["TradingCalendarRegistry"]


class TradingCalendarRegistry:
    """Maps each `MarketRegion` to its already-constructed `TradingCalendarProvider`."""

    def __init__(self, providers: dict[MarketRegion, TradingCalendarProvider]) -> None:
        self._providers = dict(providers)

    def get(self, market_region: MarketRegion) -> TradingCalendarProvider:
        """The `TradingCalendarProvider` for `market_region`.

        Raises:
            UnsupportedMarketRegionError: If no provider is registered for `market_region`.
        """
        try:
            return self._providers[market_region]
        except KeyError as exc:
            raise UnsupportedMarketRegionError(market_region) from exc

    def supported_regions(self) -> tuple[MarketRegion, ...]:
        """Every `MarketRegion` this registry currently has a provider for."""
        return tuple(sorted(self._providers, key=lambda region: region.value))
