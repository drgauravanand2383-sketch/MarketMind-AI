"""PennyStockScreeningProvider — the abstract "discover candidate tickers
for one penny/micro-cap ReportCategory" contract (Phase 6c).

Deliberately separate from `app.providers.market_data.provider
.MarketDataProvider` (per-ticker quote/history lookups) — screening/
discovery ("which tickers exist in this market within this price/
market-cap band") is a genuinely different capability, with no existing
"list every ticker"/"screen the market" method anywhere in this codebase
before this module.

A `PennyStockScreeningProvider` only ever *proposes* candidate
identities (ticker + display name) — it never fabricates or trusts a
candidate's price/market-cap/eligibility itself. Every proposed
candidate still goes through the exact same `MarketDataProvider
.get_quote()` -> `ConfigurableEligibilityProvider` pipeline every other
`UniverseEntry` does (`CategoryDataPipeline.run`); this module's own
`criteria` argument is used only to *narrow the discovery query itself*
(so a vendor's own filtering does the coarse work), never as a
substitute for the real downstream eligibility check.

An implementation raises on a genuine, unrecoverable failure (a network
error, an unusable response) rather than silently swallowing it to `()`
— the one degrade-to-the-static-universe point lives in
`GlobalMarketIntelligenceWorkflow._resolve_universe`, mirroring how
`CategoryDataPipeline.run`'s own per-category failure handling is
centralized one layer up in `_resolve_category`, not duplicated in every
leaf.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.global_markets.eligibility.models import PennyStockEligibilityCriteria
from app.global_markets.models import ReportCategory
from app.global_markets.universe.models import UniverseEntry

__all__ = ["PennyStockScreeningProvider"]


class PennyStockScreeningProvider(ABC):
    """Discovers candidate `UniverseEntry`s for one penny/micro-cap `ReportCategory`."""

    @abstractmethod
    async def discover(
        self, category: ReportCategory, criteria: PennyStockEligibilityCriteria, limit: int
    ) -> tuple[UniverseEntry, ...]:
        """Return up to `limit` candidate `UniverseEntry`s for `category`,
        narrowed by `criteria`'s own price/market-cap band where the
        underlying vendor query supports it. `category` values this
        provider doesn't cover return `()` (not an error — a composite
        provider routing by category relies on this).
        """
        raise NotImplementedError
