"""CompositePennyStockScreeningProvider — routes `discover()` to the one
sub-provider actually responsible for `category`'s market
(`YahooScreenerProvider` for the three equity penny categories,
`CoinGeckoScreeningProvider` for `LOW_CAP_CRYPTO`), so
`GlobalMarketIntelligenceWorkflow` only ever needs one injected
`screening_provider` — the same "one optional dependency" shape every
other Phase 2/3/5 integration point already uses.
"""

from __future__ import annotations

from app.global_markets.eligibility.models import PennyStockEligibilityCriteria
from app.global_markets.models import ReportCategory
from app.global_markets.screening.provider import PennyStockScreeningProvider
from app.global_markets.universe.models import UniverseEntry

__all__ = ["CompositePennyStockScreeningProvider"]


class CompositePennyStockScreeningProvider(PennyStockScreeningProvider):
    """Dispatches to `equity_screener` (for the three equity penny
    categories) or `crypto_screener` (for `LOW_CAP_CRYPTO`) — either may
    be `None` to leave that side of the composite unconfigured, degrading
    to `()` for the categories it would have covered."""

    def __init__(
        self,
        *,
        equity_screener: PennyStockScreeningProvider | None = None,
        crypto_screener: PennyStockScreeningProvider | None = None,
    ) -> None:
        self._equity_screener = equity_screener
        self._crypto_screener = crypto_screener

    async def discover(
        self, category: ReportCategory, criteria: PennyStockEligibilityCriteria, limit: int
    ) -> tuple[UniverseEntry, ...]:
        provider = self._crypto_screener if category is ReportCategory.LOW_CAP_CRYPTO else self._equity_screener
        if provider is None:
            return ()
        return await provider.discover(category, criteria, limit)
