"""Market Data Abstraction Layer: the provider-agnostic domain contract
between MarketMind's business logic and any future market-data provider.

No live API integration exists anywhere in this package — only typed
domain models and the normalization service that operates on them. See
`app.providers.market_data` for the provider interface and the
in-memory `MockMarketDataProvider` used for testing.
"""

from __future__ import annotations

from app.market_data.models import (
    CompanyProfile,
    Currency,
    Dividend,
    DividendFrequency,
    EarningsReport,
    Exchange,
    FinancialRatios,
    Fundamentals,
    HistoricalPrice,
    HistoricalSeries,
    Interval,
    MarketQuote,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
    SearchResult,
)
from app.market_data.normalization import NormalizationService

__all__ = [
    "NormalizationService",
    "Currency",
    "Exchange",
    "Interval",
    "DividendFrequency",
    "ProviderHealthStatus",
    "MarketQuote",
    "CompanyProfile",
    "FinancialRatios",
    "Fundamentals",
    "HistoricalPrice",
    "HistoricalSeries",
    "Dividend",
    "EarningsReport",
    "SearchResult",
    "ProviderHealth",
    "ProviderCapabilities",
]
