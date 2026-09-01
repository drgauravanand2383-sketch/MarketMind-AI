"""Yahoo Finance market-data provider (Milestone 13).

The first real (non-mock) `MarketDataProvider` implementation in this
codebase. Uses Yahoo Finance's public, unauthenticated chart endpoint
(`/v8/finance/chart/{ticker}`) — no API key/signup required, verified
live against real symbols (AAPL, DELL) during implementation. Real HTTP
via `httpx`, the same library `RSSProvider` already depends on — no new
package.

Only `get_quote`/`get_quotes`/`get_price_history` are backed by real data
this endpoint actually provides. Every other abstract method
(`get_company_profile`, `get_fundamentals`, `get_financial_ratios`,
`get_market_cap`, `get_earnings`, `get_dividends`, `search_symbol`) raises
`ProviderConfigurationError` explicitly — this endpoint has no such data,
and returning empty/zeroed models would misrepresent "not supported" as
"nothing to report," which this codebase's own "never fabricate" rule
prohibits just as much as returning a wrong number would.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.market_data.models import (
    CompanyProfile,
    Dividend,
    EarningsReport,
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
from app.providers.exceptions import (
    ProviderConfigurationError,
    ProviderConnectionError,
    ProviderNoDataError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from app.providers.market_data.provider import MarketDataProvider

__all__ = ["YahooFinanceProvider", "YahooFinanceProviderConfig"]

_logger = logging.getLogger("marketmind.providers.market_data.yahoo_finance")

PROVIDER_NAME = "Yahoo Finance"
PROVIDER_ID = "yahoo_finance"

# Yahoo's own interval tokens for the subset this codebase's Interval enum
# models. Anything not listed (there is no gap today — every Interval
# member is mapped) would be a genuine "this provider cannot serve this
# interval" case, not silently approximated.
_INTERVAL_TOKENS: dict[Interval, str] = {
    Interval.ONE_MINUTE: "1m",
    Interval.FIVE_MINUTES: "5m",
    Interval.FIFTEEN_MINUTES: "15m",
    Interval.THIRTY_MINUTES: "30m",
    Interval.ONE_HOUR: "60m",
    Interval.ONE_DAY: "1d",
    Interval.ONE_WEEK: "1wk",
    Interval.ONE_MONTH: "1mo",
}

# Bounds concurrent in-flight requests when get_quotes() loops per-ticker —
# this endpoint publishes no documented rate limit, so this is a
# conservative, configuration-independent ceiling against an accidental
# request storm (Milestone 13 §8), not a measured vendor limit.
_MAX_CONCURRENT_REQUESTS = 5

# Yahoo's chart `range` param only accepts a fixed set of tokens — it has
# no free-form "N days" form for this endpoint. For a daily series we ask
# for the shortest token that still fully covers the caller's requested
# [start, end] span (each entry is that token's own approximate day
# count), falling back to "max" for anything longer than 10y.
_DAILY_RANGE_TOKENS: tuple[tuple[int, str], ...] = (
    (5, "5d"),
    (31, "1mo"),
    (93, "3mo"),
    (186, "6mo"),
    (367, "1y"),
    (731, "2y"),
    (1827, "5y"),
    (3653, "10y"),
)
_MAX_RANGE_TOKEN = "max"
# Kept for the caller that omits `start` entirely (it wants "recent
# history", not a symbol's full listing) — unchanged from the original
# hardcoded default.
_DEFAULT_DAILY_RANGE_TOKEN = "2y"
_INTRADAY_RANGE_TOKEN = "1mo"


def _daily_range_token(start: date | None, end: date | None) -> str:
    """Smallest Yahoo daily `range` token covering `[start, end]`."""
    if start is None:
        return _DEFAULT_DAILY_RANGE_TOKEN
    reference_end = end or datetime.now(UTC).date()
    span_days = (reference_end - start).days
    for threshold, token in _DAILY_RANGE_TOKENS:
        if span_days <= threshold:
            return token
    return _MAX_RANGE_TOKEN


class YahooFinanceProviderConfig(BaseModel):
    """Configuration for YahooFinanceProvider.

    Not a subclass of `app.providers.models.ProviderConfig`: like
    `MarketDataProvider` itself (see that module's own docstring),
    market-data provider configuration is intentionally kept separate
    from the generic `BaseProvider`/`ProviderConfig` framework used by
    RSS-style providers.
    """

    model_config = ConfigDict(extra="forbid")

    base_url: str = "https://query1.finance.yahoo.com"
    timeout: float = Field(default=10.0, gt=0)
    retry_attempts: int = Field(default=1, ge=0)
    retry_backoff_seconds: float = Field(default=1.0, ge=0)
    user_agent: str = "MarketMind-AI/1.0"
    # Milestone 16 §10: how many *consecutive* fully-exhausted-retry
    # failures (across any ticker) before `health()` reports DEGRADED,
    # then UNAVAILABLE — reset to 0 by the next success. A single
    # transient failure (already absorbed by retry_attempts) never
    # degrades the reported status; only a real run of failures does.
    degraded_after_consecutive_failures: int = Field(default=3, ge=1)
    unavailable_after_consecutive_failures: int = Field(default=8, ge=1)

    @model_validator(mode="after")
    def _validate_failure_thresholds(self) -> YahooFinanceProviderConfig:
        if self.unavailable_after_consecutive_failures < self.degraded_after_consecutive_failures:
            raise ValueError(
                "unavailable_after_consecutive_failures must be >= degraded_after_consecutive_failures; "
                f"got {self.unavailable_after_consecutive_failures!r} < "
                f"{self.degraded_after_consecutive_failures!r}."
            )
        return self


class YahooFinanceProvider(MarketDataProvider):
    """A real MarketDataProvider backed by Yahoo Finance's public chart endpoint."""

    def __init__(
        self,
        config: YahooFinanceProviderConfig,
        *,
        normalization_service: NormalizationService | None = None,
        client_factory: type[httpx.AsyncClient] = httpx.AsyncClient,
    ) -> None:
        """Initialize the provider.

        Args:
            config: This provider's configuration.
            normalization_service: Injected for testability and reuse —
                defaults to a fresh `NormalizationService()` (stateless,
                safe to construct freely, per its own docstring).
            client_factory: The `httpx.AsyncClient` constructor to use.
                Production code omits it; tests inject a fake transport
                via `httpx.AsyncClient(transport=...)` construction
                indirectly (see this provider's own tests) — no test in
                this codebase makes a real network call.
        """
        self._config = config
        self._normalization = normalization_service or NormalizationService()
        self._client_factory = client_factory
        # Milestone 16 §10: real, observed failure history — not a
        # measured vendor SLA — driving `health()`'s reported status.
        self._consecutive_failures = 0
        self._last_failure_at: datetime | None = None
        self._last_success_at: datetime | None = None

    @property
    def config(self) -> YahooFinanceProviderConfig:
        return self._config

    def provider_name(self) -> str:
        return PROVIDER_NAME

    def capabilities(self) -> ProviderCapabilities:
        """Report exactly what this endpoint actually provides — never a
        capability this provider can't back with real data."""
        return ProviderCapabilities(
            supports_quotes=True,
            supports_history=True,
            supports_fundamentals=False,
            supports_dividends=False,
            supports_search=False,
            supports_batch=False,
            supports_intraday=True,
            rate_limit=None,
        )

    async def health(self) -> ProviderHealth:
        """Report status from real, observed request outcomes — no new
        request is made here (matching the ABC's own guidance that a
        health check must never be as expensive as a real data request),
        but the *reported* status now reflects `_consecutive_failures`
        accumulated by `_fetch_chart` across real prior calls, not a
        hardcoded HEALTHY regardless of what actually happened (§10:
        "clearer provider health state"). Resets to HEALTHY on the very
        next success — a past outage never permanently marks the provider
        degraded once it recovers.
        """
        if self._consecutive_failures >= self._config.unavailable_after_consecutive_failures:
            status = ProviderHealthStatus.UNAVAILABLE
        elif self._consecutive_failures >= self._config.degraded_after_consecutive_failures:
            status = ProviderHealthStatus.DEGRADED
        else:
            status = ProviderHealthStatus.HEALTHY
        return ProviderHealth(
            provider=PROVIDER_NAME,
            status=status,
            latency_ms=None,
            last_updated=datetime.now(UTC),
        )

    async def get_quote(self, ticker: str) -> MarketQuote:
        normalized_ticker = self._normalization.normalize_ticker(ticker)
        payload = await self._fetch_chart(normalized_ticker, range_="1d", interval_token="1m")
        return self._quote_from_payload(normalized_ticker, payload)

    async def get_quotes(self, tickers: list[str]) -> list[MarketQuote]:
        """Loop `get_quote` per ticker, concurrency-bounded — this
        endpoint has no true multi-symbol batch call
        (`capabilities().supports_batch` is `False`), matching the ABC's
        own documented allowance for that case. All-or-nothing: the first
        failing ticker's exception propagates, exactly like
        `MockMarketDataProvider.get_quotes`'s own behavior — partial-
        failure-tolerant batching belongs one layer up, in
        `MarketSnapshotService.get_snapshots()`, which calls `get_quote`
        per entity independently so one bad symbol can't fail the batch.
        """
        semaphore = asyncio.Semaphore(_MAX_CONCURRENT_REQUESTS)

        async def _bounded(ticker: str) -> MarketQuote:
            async with semaphore:
                return await self.get_quote(ticker)

        return list(await asyncio.gather(*(_bounded(ticker) for ticker in tickers)))

    async def get_price_history(
        self,
        ticker: str,
        interval: Interval,
        start: date | None = None,
        end: date | None = None,
    ) -> HistoricalSeries:
        normalized_ticker = self._normalization.normalize_ticker(ticker)
        interval_token = _INTERVAL_TOKENS[interval]
        range_token = _INTRADAY_RANGE_TOKEN if interval.is_intraday else _daily_range_token(start, end)
        payload = await self._fetch_chart(
            normalized_ticker, range_=range_token, interval_token=interval_token
        )
        series = self._history_from_payload(normalized_ticker, interval, payload)
        if start is not None or end is not None:
            filtered = tuple(
                bar
                for bar in series.prices
                if (start is None or bar.date.date() >= start)
                and (end is None or bar.date.date() <= end)
            )
            series = series.model_copy(update={"prices": filtered})
        return self._normalization.normalize_historical_series(series)

    async def get_company_profile(self, ticker: str) -> CompanyProfile:
        raise ProviderConfigurationError(
            "YahooFinanceProvider's chart endpoint does not provide company profile data.",
            provider_id=PROVIDER_ID,
        )

    async def get_fundamentals(self, ticker: str) -> Fundamentals:
        raise ProviderConfigurationError(
            "YahooFinanceProvider's chart endpoint does not provide fundamentals data.",
            provider_id=PROVIDER_ID,
        )

    async def get_financial_ratios(self, ticker: str) -> FinancialRatios:
        raise ProviderConfigurationError(
            "YahooFinanceProvider's chart endpoint does not provide financial ratio data.",
            provider_id=PROVIDER_ID,
        )

    async def get_market_cap(self, ticker: str) -> float:
        raise ProviderConfigurationError(
            "YahooFinanceProvider's chart endpoint does not provide market capitalization data.",
            provider_id=PROVIDER_ID,
        )

    async def get_earnings(self, ticker: str) -> list[EarningsReport]:
        raise ProviderConfigurationError(
            "YahooFinanceProvider's chart endpoint does not provide earnings data.",
            provider_id=PROVIDER_ID,
        )

    async def get_dividends(self, ticker: str) -> list[Dividend]:
        raise ProviderConfigurationError(
            "YahooFinanceProvider's chart endpoint does not provide dividend data.",
            provider_id=PROVIDER_ID,
        )

    async def search_symbol(self, query: str) -> list[SearchResult]:
        raise ProviderConfigurationError(
            "YahooFinanceProvider's chart endpoint does not provide symbol search.",
            provider_id=PROVIDER_ID,
        )

    async def _fetch_chart(
        self, ticker: str, *, range_: str, interval_token: str
    ) -> dict[str, Any]:
        """Fetch and validate the raw chart payload for one ticker,
        retrying transient failures up to `config.retry_attempts` times
        (the same retry-with-fixed-backoff technique `RSSProvider._fetch_one`
        already uses), before raising a specific `ProviderError` subclass.
        Never returns a payload that hasn't been checked to actually
        contain usable `meta`/`timestamp` data.
        """
        url = f"{self._config.base_url}/v8/finance/chart/{ticker}"
        params = {"range": range_, "interval": interval_token}
        headers = {"User-Agent": self._config.user_agent}
        attempts = max(self._config.retry_attempts, 0) + 1

        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                async with self._client_factory(timeout=self._config.timeout) as client:
                    response = await client.get(url, params=params, headers=headers)
            except httpx.TimeoutException as exc:
                message = f"Yahoo Finance request for {ticker!r} timed out: {exc}"
                last_error = ProviderTimeoutError(message, provider_id=PROVIDER_ID)
            except httpx.HTTPError as exc:
                message = f"Yahoo Finance request for {ticker!r} failed: {exc}"
                last_error = ProviderConnectionError(message, provider_id=PROVIDER_ID)
            else:
                if response.status_code == 429:
                    message = f"Yahoo Finance rate-limited the request for {ticker!r} (HTTP 429)."
                    last_error = ProviderRateLimitError(message, provider_id=PROVIDER_ID)
                elif response.status_code >= 500:
                    message = f"Yahoo Finance returned HTTP {response.status_code} for {ticker!r}."
                    last_error = ProviderConnectionError(message, provider_id=PROVIDER_ID)
                else:
                    # A response was received at all — the provider itself is
                    # reachable, regardless of whether *this ticker* turns out
                    # to have usable data (`_parse_chart_response` may still
                    # raise its own ticker-specific error, uncounted below:
                    # "no data for this symbol" is not "the provider is down").
                    self._consecutive_failures = 0
                    self._last_success_at = datetime.now(UTC)
                    return self._parse_chart_response(ticker, response)

            if attempt < attempts - 1:
                _logger.warning(
                    "yahoo_finance_request_retry",
                    extra={"ticker": ticker, "attempt": attempt + 1, "error": str(last_error)},
                )
                await asyncio.sleep(self._config.retry_backoff_seconds)

        assert last_error is not None
        self._consecutive_failures += 1
        self._last_failure_at = datetime.now(UTC)
        _logger.warning(
            "yahoo_finance_request_failed",
            extra={
                "ticker": ticker, "error": str(last_error),
                "consecutive_failures": self._consecutive_failures,
            },
        )
        raise last_error

    def _parse_chart_response(self, ticker: str, response: httpx.Response) -> dict[str, Any]:
        """Validate one HTTP response into a usable chart payload dict, or
        raise the specific ProviderError the failure shape calls for.
        Isolated from `_fetch_chart`'s retry loop so a definitively bad
        response (invalid JSON, Yahoo's own "not found" error shape) is
        never retried — retrying is for transient failures, not "this
        ticker doesn't exist."""
        if response.status_code == 404:
            message = f"Yahoo Finance has no data for ticker {ticker!r} (HTTP 404)."
            raise ProviderNoDataError(message, provider_id=PROVIDER_ID)
        if response.status_code != 200:
            status_code = response.status_code
            message = f"Yahoo Finance returned an unexpected HTTP {status_code} for {ticker!r}."
            raise ProviderResponseError(message, provider_id=PROVIDER_ID)

        try:
            body = response.json()
        except ValueError as exc:
            message = f"Yahoo Finance response for {ticker!r} was not valid JSON: {exc}"
            raise ProviderResponseError(message, provider_id=PROVIDER_ID) from exc

        chart = body.get("chart") if isinstance(body, dict) else None
        if not isinstance(chart, dict):
            message = f"Yahoo Finance response for {ticker!r} had no 'chart' object."
            raise ProviderResponseError(message, provider_id=PROVIDER_ID)

        error = chart.get("error")
        if error:
            description = error.get("description") if isinstance(error, dict) else str(error)
            message = f"Yahoo Finance has no data for ticker {ticker!r}: {description}"
            raise ProviderNoDataError(message, provider_id=PROVIDER_ID)

        result = chart.get("result")
        if not result or not isinstance(result, list) or not isinstance(result[0], dict):
            message = f"Yahoo Finance returned no result for ticker {ticker!r}."
            raise ProviderNoDataError(message, provider_id=PROVIDER_ID)

        payload = result[0]
        if not isinstance(payload.get("meta"), dict):
            message = f"Yahoo Finance response for {ticker!r} had no 'meta' object."
            raise ProviderResponseError(message, provider_id=PROVIDER_ID)
        return payload

    def _quote_from_payload(self, ticker: str, payload: dict[str, Any]) -> MarketQuote:
        meta = payload["meta"]
        price = meta.get("regularMarketPrice")
        market_time = meta.get("regularMarketTime")
        if price is None or market_time is None:
            message = f"Yahoo Finance has no current price for ticker {ticker!r}."
            raise ProviderNoDataError(message, provider_id=PROVIDER_ID)

        previous_close = meta.get("previousClose") or meta.get("chartPreviousClose")
        change = (price - previous_close) if previous_close else None
        change_percent = (
            (change / previous_close * 100) if change is not None and previous_close else None
        )

        currency = self._safe_currency(meta.get("currency"))
        exchange = self._safe_exchange(meta.get("fullExchangeName") or meta.get("exchangeName"))

        quote = MarketQuote(
            ticker=ticker,
            price=float(price),
            timestamp=datetime.fromtimestamp(market_time, tz=UTC),
            change=change,
            change_percent=change_percent,
            volume=meta.get("regularMarketVolume"),
            previous_close=previous_close,
            day_high=meta.get("regularMarketDayHigh"),
            day_low=meta.get("regularMarketDayLow"),
            currency=currency,
            exchange=exchange,
        )
        return self._normalization.normalize_quote(quote)

    def _history_from_payload(
        self, ticker: str, interval: Interval, payload: dict[str, Any]
    ) -> HistoricalSeries:
        timestamps: list[int] = payload.get("timestamp") or []
        indicators = payload.get("indicators") or {}
        quote_list = indicators.get("quote") or [{}]
        quote_data = quote_list[0] if quote_list else {}
        opens = quote_data.get("open") or []
        highs = quote_data.get("high") or []
        lows = quote_data.get("low") or []
        closes = quote_data.get("close") or []
        volumes = quote_data.get("volume") or []

        bars: list[HistoricalPrice] = []
        for index, ts in enumerate(timestamps):
            bar_open = opens[index] if index < len(opens) else None
            bar_high = highs[index] if index < len(highs) else None
            bar_low = lows[index] if index < len(lows) else None
            bar_close = closes[index] if index < len(closes) else None
            if bar_open is None or bar_high is None or bar_low is None or bar_close is None:
                continue  # a non-trading interval bar — skipped, never fabricated
            has_volume = index < len(volumes) and volumes[index] is not None
            bars.append(
                HistoricalPrice(
                    date=datetime.fromtimestamp(ts, tz=UTC),
                    open=bar_open,
                    high=bar_high,
                    low=bar_low,
                    close=bar_close,
                    volume=int(volumes[index]) if has_volume else 0,
                )
            )

        if not bars:
            message = f"Yahoo Finance returned no historical bars for ticker {ticker!r}."
            raise ProviderNoDataError(message, provider_id=PROVIDER_ID)
        return HistoricalSeries(ticker=ticker, interval=interval, prices=tuple(bars))

    def _safe_currency(self, value: str | None) -> Any:
        if not value:
            return None
        try:
            return self._normalization.normalize_currency(value)
        except ValueError:
            return None

    def _safe_exchange(self, value: str | None) -> Any:
        if not value:
            return None
        return self._normalization.normalize_exchange(value)
