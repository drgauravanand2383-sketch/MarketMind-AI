"""Abstract contract every market-data provider implementation must satisfy.

`MarketDataProvider` is defined here rather than reusing the generic
`app.providers.base.BaseProvider`/`ProviderConfig`/`ProviderResult` shape,
for the same reason `BaseLLMProvider` (Sprint 36) was defined standalone in
`app.providers.anthropic.provider` rather than forced into that generic
`fetch(**kwargs) -> ProviderResult` contract: market data needs many
distinct, strongly-typed operations (a quote is not shaped like a
dividend history), not one generic untyped fetch. This module contains no
HTTP requests, no vendor SDK calls, and no business logic — only the
abstraction. See `app.providers.market_data.mock.MockMarketDataProvider`
for the sole concrete implementation this sprint provides (deterministic,
in-memory, for tests only) — no real provider (Alpha Vantage, Finnhub,
Polygon, Twelve Data, Yahoo Finance, IEX, Alpaca, or any other) is
integrated anywhere in this codebase yet.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from app.market_data.models import (
    CompanyProfile,
    Dividend,
    EarningsReport,
    FinancialRatios,
    Fundamentals,
    HistoricalSeries,
    Interval,
    MarketQuote,
    ProviderCapabilities,
    ProviderHealth,
    SearchResult,
)

__all__ = ["MarketDataProvider"]


class MarketDataProvider(ABC):
    """Abstract base class every market-data provider implementation must inherit.

    Every method returns a strongly-typed model (or a collection of them)
    from `app.market_data.models` — never a raw dict, never a raw vendor
    SDK response. A concrete implementation is responsible for translating
    its underlying source's response shape into these models, including
    raising `app.providers.exceptions.ProviderError` (or a subclass) for
    any failure — never letting a raw vendor exception or a raw HTTP error
    propagate past this boundary.
    """

    @abstractmethod
    async def get_quote(self, ticker: str) -> MarketQuote:
        """Retrieve the current (or most recent) quote for one ticker."""
        raise NotImplementedError

    @abstractmethod
    async def get_quotes(self, tickers: list[str]) -> list[MarketQuote]:
        """Retrieve quotes for multiple tickers in one batch request.

        A provider whose `capabilities().supports_batch` is `False` may
        still implement this by issuing one `get_quote` call per ticker
        internally — the batch *contract* (accept a list, return a list)
        is what every provider must support; batching at the transport
        level is an optional optimization.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_company_profile(self, ticker: str) -> CompanyProfile:
        """Retrieve descriptive company information for one ticker."""
        raise NotImplementedError

    @abstractmethod
    async def get_fundamentals(self, ticker: str) -> Fundamentals:
        """Retrieve the most recent financial-statement fundamentals for one ticker."""
        raise NotImplementedError

    @abstractmethod
    async def get_financial_ratios(self, ticker: str) -> FinancialRatios:
        """Retrieve the most recent valuation/profitability/liquidity ratios for one ticker."""
        raise NotImplementedError

    @abstractmethod
    async def get_market_cap(self, ticker: str) -> float:
        """Retrieve the current market capitalization for one ticker.

        Returns a plain `float` rather than a dedicated model: no
        "MarketCap" model is listed among this sprint's domain models, and
        a market cap is already fully represented by a single positive
        number (`CompanyProfile.market_cap` carries the same value in its
        richer context). Must be positive.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_earnings(self, ticker: str) -> list[EarningsReport]:
        """Retrieve historical (and, where available, upcoming estimated)
        earnings reports for one ticker, ordered most-recent first."""
        raise NotImplementedError

    @abstractmethod
    async def get_dividends(self, ticker: str) -> list[Dividend]:
        """Retrieve the dividend history for one ticker."""
        raise NotImplementedError

    @abstractmethod
    async def get_price_history(
        self,
        ticker: str,
        interval: Interval,
        start: date | None = None,
        end: date | None = None,
    ) -> HistoricalSeries:
        """Retrieve historical OHLCV price bars for one ticker at `interval`.

        Args:
            ticker: The ticker to retrieve history for.
            interval: The bar interval. `capabilities().supports_intraday`
                reports whether this provider serves `interval.is_intraday`
                values.
            start: Inclusive lower date bound. `None` means "as far back as
                available."
            end: Inclusive upper date bound. `None` means "up to the most
                recent available bar."
        """
        raise NotImplementedError

    @abstractmethod
    async def search_symbol(self, query: str) -> list[SearchResult]:
        """Search for tickers matching a free-text company name or ticker fragment."""
        raise NotImplementedError

    @abstractmethod
    def provider_name(self) -> str:
        """The human-readable name of this provider (e.g. 'Mock Market Data Provider').

        A plain synchronous method, not a property — matches this sprint's
        own listing of it alongside the other method-style members
        (`health()`, `capabilities()`), and requires no I/O to answer.
        """
        raise NotImplementedError

    @abstractmethod
    async def health(self) -> ProviderHealth:
        """Report this provider's current reachability/latency.

        Implementations should make the lightest possible real check (or
        none at all, for a provider with nothing to check) — this must
        never be as expensive as a real data request.
        """
        raise NotImplementedError

    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """Report what this provider implementation supports. Requires no I/O."""
        raise NotImplementedError
