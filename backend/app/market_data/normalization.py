"""NormalizationService: provider-agnostic normalization for market data.

Provides the shared normalization primitives (ticker formatting, currency,
exchange, timezone, numeric precision, date, missing-field handling) any
future real `MarketDataProvider` implementation calls before returning
data — so no individual provider needs to reimplement this logic, and
callers of the abstraction never see provider-specific formatting quirks
(e.g. one vendor returning "aapl.US", another "AAPL", a third a
naive/local-time timestamp instead of UTC).

No provider-specific logic lives here — nothing in this module knows about
Alpha Vantage, Finnhub, Yahoo Finance, or any other vendor. It operates
purely on this sprint's own domain models (`app.market_data.models`) and
plain Python primitives (`str`, `float`, `datetime`, `date`).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from app.market_data.models import Currency, Exchange, HistoricalPrice, HistoricalSeries, MarketQuote

__all__ = ["NormalizationService"]

_DEFAULT_PRICE_PRECISION = 2

_EXCHANGE_ALIASES: dict[str, Exchange] = {
    "NEW YORK STOCK EXCHANGE": Exchange.NYSE,
    "NASDAQ GLOBAL SELECT": Exchange.NASDAQ,
    "NATIONAL STOCK EXCHANGE OF INDIA": Exchange.NSE,
    "BOMBAY STOCK EXCHANGE": Exchange.BSE,
    "LONDON STOCK EXCHANGE": Exchange.LSE,
    "TOKYO STOCK EXCHANGE": Exchange.TSE,
    "HONG KONG STOCK EXCHANGE": Exchange.HKEX,
    "SHANGHAI STOCK EXCHANGE": Exchange.SSE,
    "SHENZHEN STOCK EXCHANGE": Exchange.SZSE,
    "TORONTO STOCK EXCHANGE": Exchange.TSX,
    "AUSTRALIAN SECURITIES EXCHANGE": Exchange.ASX,
    # Milestone 13: real full-exchange-name strings observed from Yahoo
    # Finance's own chart endpoint (`meta.fullExchangeName`).
    "NASDAQGS": Exchange.NASDAQ,
    "NASDAQGM": Exchange.NASDAQ,
    "NASDAQCM": Exchange.NASDAQ,
    "NYSEAMERICAN": Exchange.AMEX,
    "NYSEARCA": Exchange.NYSE,
}


class NormalizationService:
    """Stateless normalization primitives plus two composite entry points
    (`normalize_quote`, `normalize_historical_series`) that apply them
    across an entire domain model at once. No dependencies, no I/O — safe
    to construct freely and share across every provider."""

    def normalize_ticker(self, ticker: str) -> str:
        """Strip surrounding whitespace and upper-case. This is the same
        normalization every domain model already applies to its own
        `ticker` field validator — exposed here as a standalone primitive
        so a provider can normalize a ticker *before* constructing a
        model (e.g. to look up a local cache key)."""
        return ticker.strip().upper()

    def normalize_currency(self, value: str | Currency) -> Currency:
        """Resolve a currency code (case-insensitively) to a `Currency` member.

        Raises:
            ValueError: `value` is not a supported currency code.
        """
        if isinstance(value, Currency):
            return value
        try:
            return Currency(value.strip().upper())
        except ValueError:
            raise ValueError(f"Unsupported currency code: {value!r}.") from None

    def normalize_exchange(self, value: str | Exchange) -> Exchange:
        """Resolve an exchange code or common full name (case-insensitively)
        to an `Exchange` member. Falls back to `Exchange.OTHER` for any
        recognizable-but-unmapped input rather than raising — an unknown
        exchange should not block ingestion of an otherwise-valid quote.
        """
        if isinstance(value, Exchange):
            return value
        cleaned = value.strip().upper()
        try:
            return Exchange(cleaned)
        except ValueError:
            pass
        return _EXCHANGE_ALIASES.get(cleaned, Exchange.OTHER)

    def normalize_timestamp(self, value: datetime) -> datetime:
        """Convert to UTC. A naive `datetime` is assumed to already be UTC
        (the safest assumption absent any provider-specific timezone
        metadata — providers must supply timezone-aware data if their
        source timezone differs) and is stamped as such, not shifted."""
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def normalize_date(self, value: date | datetime) -> date:
        """Collapse a `datetime` to its calendar `date`; a `date` passes through unchanged."""
        if isinstance(value, datetime):
            return value.date()
        return value

    def round_price(self, value: float, precision: int = _DEFAULT_PRICE_PRECISION) -> float:
        """Round a price to `precision` decimal places (2 by default — cents)."""
        return round(value, precision)

    def fill_missing(self, value: object, default: object) -> object:
        """Return `default` when `value` is `None`, else `value` unchanged.
        The single shared rule every composite normalization method below
        applies for an absent field: substitute the caller-supplied
        default rather than leaving `None` silently propagate."""
        return default if value is None else value

    def normalize_quote(self, quote: MarketQuote, *, price_precision: int = _DEFAULT_PRICE_PRECISION) -> MarketQuote:
        """Apply every relevant primitive above to a `MarketQuote`: ticker
        formatting, timestamp timezone, and price-field rounding. Currency/
        exchange are left as already-typed enum members (or `None`) since
        `MarketQuote` itself only ever holds a valid `Currency`/`Exchange`
        member or `None` — there is nothing further to normalize once a
        model already exists; `normalize_currency`/`normalize_exchange`
        exist for a provider building a quote from raw vendor strings.
        """
        updates: dict[str, object] = {
            "ticker": self.normalize_ticker(quote.ticker),
            "timestamp": self.normalize_timestamp(quote.timestamp),
            "price": self.round_price(quote.price, price_precision),
        }
        for field_name in ("previous_close", "open", "day_high", "day_low"):
            current = getattr(quote, field_name)
            if current is not None:
                updates[field_name] = self.round_price(current, price_precision)
        return quote.model_copy(update=updates)

    def normalize_historical_series(
        self, series: HistoricalSeries, *, price_precision: int = _DEFAULT_PRICE_PRECISION
    ) -> HistoricalSeries:
        """Apply ticker formatting and price-field rounding across every
        bar in a `HistoricalSeries`. Ordering/uniqueness of `date` is
        already enforced by `HistoricalSeries`'s own validation — this
        method never reorders or drops a bar, only rounds its prices.
        """
        normalized_prices = tuple(
            self._normalize_price_bar(bar, price_precision) for bar in series.prices
        )
        return series.model_copy(
            update={"ticker": self.normalize_ticker(series.ticker), "prices": normalized_prices}
        )

    def _normalize_price_bar(self, bar: HistoricalPrice, price_precision: int) -> HistoricalPrice:
        updates: dict[str, object] = {
            "open": self.round_price(bar.open, price_precision),
            "high": self.round_price(bar.high, price_precision),
            "low": self.round_price(bar.low, price_precision),
            "close": self.round_price(bar.close, price_precision),
        }
        if bar.adjusted_close is not None:
            updates["adjusted_close"] = self.round_price(bar.adjusted_close, price_precision)
        return bar.model_copy(update=updates)
