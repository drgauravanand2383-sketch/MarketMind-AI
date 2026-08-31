"""MarketDataNormalizer — maps a fetched `MarketQuote` (+ optional
`HistoricalSeries`) into this module's own `NormalizedAssetSnapshot`.

The one, single place a raw `app.market_data.models.MarketQuote` is
translated into Global Market Intelligence's own cross-market-comparable
shape — every downstream stage (eligibility, factor scoring) consumes
only `NormalizedAssetSnapshot`, never a raw provider model, mirroring
this codebase's established "no raw SDK/provider object leaves its own
boundary" convention (see e.g. `app.providers.anthropic.models
.MessageResponse`'s own docstring for the same discipline applied
elsewhere).

A field the quote/history genuinely doesn't carry is `None` — never
fabricated. `market_cap` is deliberately not fetched here: verified live
against the real `YahooFinanceProvider`, `get_market_cap()` raises
`ProviderConfigurationError` unconditionally (the chart endpoint has no
market-cap data at all, for any ticker) — calling it on every asset would
be a guaranteed-useless request, so this normalizer never calls it and
leaves `market_cap`/`fully_diluted_valuation` honestly `None`. Documented
gap: `LOW_CAP_CRYPTO`'s eligibility (a later phase, once that category's
universe is populated) will need a market-cap-capable data source this
provider cannot supply.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.global_markets.models import DataFreshnessStatus, DataProvenance, NormalizedAssetSnapshot, ReportCategory
from app.market_data.models import HistoricalSeries, MarketQuote

__all__ = ["MarketDataNormalizer"]


class MarketDataNormalizer:
    """Normalizes one already-fetched `MarketQuote` into a `NormalizedAssetSnapshot`."""

    def normalize(
        self,
        *,
        quote: MarketQuote,
        report_category: ReportCategory,
        provider_name: str,
        history: HistoricalSeries | None = None,
        freshness_status: DataFreshnessStatus = DataFreshnessStatus.LIVE,
        retrieved_at: datetime | None = None,
    ) -> NormalizedAssetSnapshot:
        avg_daily_traded_value = (
            float(quote.average_volume) * quote.price if quote.average_volume is not None else None
        )
        trading_history_days = None
        if history is not None and history.prices:
            sorted_prices = sorted(history.prices, key=lambda price: price.date)
            trading_history_days = (sorted_prices[-1].date - sorted_prices[0].date).days

        provenance = DataProvenance(
            source_timestamp=quote.timestamp,
            retrieved_at=retrieved_at if retrieved_at is not None else datetime.now(UTC),
            provider=provider_name,
            data_freshness_status=freshness_status,
        )

        return NormalizedAssetSnapshot(
            ticker=quote.ticker,
            report_category=report_category,
            name=None,
            price=quote.price,
            currency=quote.currency.value if quote.currency is not None else None,
            market_cap=None,
            fully_diluted_valuation=None,
            avg_daily_volume=float(quote.average_volume) if quote.average_volume is not None else None,
            avg_daily_traded_value=avg_daily_traded_value,
            trading_history_days=trading_history_days,
            is_suspended=False,
            is_delisted=False,
            bid_ask_spread_percent=None,
            provenance=provenance,
        )
