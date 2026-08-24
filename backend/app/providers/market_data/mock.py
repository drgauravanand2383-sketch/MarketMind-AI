"""MockMarketDataProvider: an in-memory, fully deterministic implementation
of `MarketDataProvider`.

For unit testing only — never a stand-in for a real provider. Every value
returned for a given ticker is derived from a stable SHA-256 digest of the
ticker string itself (never Python's built-in `hash()`, which is
randomized per-process by `PYTHONHASHSEED` and therefore not safe for this
purpose), so the same ticker always produces the exact same numbers across
every call, every test run, every process. No `random` module usage
anywhere in this file.

The one intentionally time-sensitive exception is `health()`'s
`last_updated` field, which reports the real wall-clock instant the health
check ran — a health check answering "how fresh is this" is inherently a
point-in-time question, unlike quote/fundamentals/history data, which this
mock always reproduces identically for a given ticker.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta

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
from app.providers.market_data.provider import MarketDataProvider

__all__ = ["MockMarketDataProvider"]

PROVIDER_NAME = "Mock Market Data Provider"

_DEFAULT_REFERENCE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
_DEFAULT_BAR_COUNT = 30
_MAX_BARS = 500

_CURRENCIES = tuple(Currency)
_EXCHANGES = tuple(e for e in Exchange if e != Exchange.OTHER)
_SECTORS = ("Technology", "Healthcare", "Financials", "Energy", "Industrials", "Consumer Discretionary")
_INDUSTRIES = ("Software", "Semiconductors", "Biotechnology", "Banking", "Oil & Gas", "Retail")
_COUNTRIES = ("US", "Canada", "Germany", "Japan", "India", "United Kingdom")

_SEARCH_CATALOG: tuple[SearchResult, ...] = (
    SearchResult(ticker="AAPL", company_name="Apple Inc.", exchange=Exchange.NASDAQ, country="US"),
    SearchResult(ticker="MSFT", company_name="Microsoft Corporation", exchange=Exchange.NASDAQ, country="US"),
    SearchResult(ticker="GOOGL", company_name="Alphabet Inc.", exchange=Exchange.NASDAQ, country="US"),
    SearchResult(ticker="AMZN", company_name="Amazon.com Inc.", exchange=Exchange.NASDAQ, country="US"),
    SearchResult(ticker="TSLA", company_name="Tesla Inc.", exchange=Exchange.NASDAQ, country="US"),
    SearchResult(ticker="NVDA", company_name="NVIDIA Corporation", exchange=Exchange.NASDAQ, country="US"),
    SearchResult(
        ticker="TSM", company_name="Taiwan Semiconductor Manufacturing", exchange=Exchange.NYSE, country="Taiwan"
    ),
    SearchResult(ticker="RELIANCE", company_name="Reliance Industries Limited", exchange=Exchange.NSE, country="India"),
)


def _digest(ticker: str) -> int:
    """A stable, non-negative integer seed derived from `ticker`. Deterministic
    across processes and Python versions — unlike the builtin `hash()`."""
    return int(hashlib.sha256(ticker.encode("utf-8")).hexdigest(), 16)


def _company_name(ticker: str) -> str:
    return f"{ticker} Mock Corp"


class MockMarketDataProvider(MarketDataProvider):
    """A complete, deterministic `MarketDataProvider` implementation backed
    by nothing but pure functions of the requested ticker string. No
    network I/O, no filesystem access, no external dependency of any kind.
    """

    def __init__(self, reference_time: datetime = _DEFAULT_REFERENCE_TIME) -> None:
        """Initialize the provider.

        Args:
            reference_time: The fixed instant every generated `MarketQuote`
                is timestamped at, and the fixed "as of" date every
                generated history/earnings/dividend series is anchored
                to — injected so callers needing a specific fixed time in
                their own assertions can supply one. Defaults to a fixed
                constant, never `datetime.now()`, so behavior never varies
                between calls or processes.
        """
        if reference_time.tzinfo is None:
            raise ValueError("reference_time must be timezone-aware.")
        self._reference_time = reference_time

    def provider_name(self) -> str:
        return PROVIDER_NAME

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_quotes=True,
            supports_history=True,
            supports_fundamentals=True,
            supports_dividends=True,
            supports_search=True,
            supports_batch=True,
            supports_intraday=True,
            rate_limit=None,
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider=PROVIDER_NAME,
            status=ProviderHealthStatus.HEALTHY,
            latency_ms=0.0,
            last_updated=datetime.now(UTC),
        )

    async def get_quote(self, ticker: str) -> MarketQuote:
        normalized = _require_ticker(ticker)
        seed = _digest(normalized)

        price = _scaled(seed, 1, low=10.0, high=900.0)
        previous_close = _scaled(seed, 2, low=10.0, high=900.0)
        change = round(price - previous_close, 2)
        change_percent = round((change / previous_close) * 100, 4) if previous_close else 0.0

        return MarketQuote(
            ticker=normalized,
            price=price,
            change=change,
            change_percent=change_percent,
            volume=_scaled_int(seed, 3, low=10_000, high=50_000_000),
            average_volume=_scaled_int(seed, 4, low=10_000, high=50_000_000),
            previous_close=previous_close,
            open=_scaled(seed, 5, low=10.0, high=900.0),
            day_high=max(price, previous_close) + _scaled(seed, 6, low=0.1, high=5.0),
            day_low=min(price, previous_close) - _scaled(seed, 7, low=0.1, high=5.0),
            timestamp=self._reference_time,
            currency=_pick(seed, 8, _CURRENCIES),
            exchange=_pick(seed, 9, _EXCHANGES),
        )

    async def get_quotes(self, tickers: list[str]) -> list[MarketQuote]:
        return [await self.get_quote(ticker) for ticker in tickers]

    async def get_company_profile(self, ticker: str) -> CompanyProfile:
        normalized = _require_ticker(ticker)
        seed = _digest(normalized)
        shares_outstanding = _scaled(seed, 10, low=1_000_000.0, high=5_000_000_000.0)
        price = _scaled(seed, 1, low=10.0, high=900.0)

        return CompanyProfile(
            ticker=normalized,
            company_name=_company_name(normalized),
            exchange=_pick(seed, 9, _EXCHANGES),
            country=_pick(seed, 11, _COUNTRIES),
            sector=_pick(seed, 12, _SECTORS),
            industry=_pick(seed, 13, _INDUSTRIES),
            description=f"{_company_name(normalized)} is a mock company generated for testing purposes.",
            website=f"https://example.com/{normalized.lower()}",
            employees=_scaled_int(seed, 14, low=10, high=500_000),
            ipo_date=date(2000, 1, 1) + timedelta(days=seed % 9000),
            currency=_pick(seed, 8, _CURRENCIES),
            market_cap=round(shares_outstanding * price, 2),
            shares_outstanding=shares_outstanding,
        )

    async def get_fundamentals(self, ticker: str) -> Fundamentals:
        normalized = _require_ticker(ticker)
        seed = _digest(normalized)
        revenue = _scaled(seed, 20, low=1_000_000.0, high=400_000_000_000.0)
        net_income = round(revenue * _fraction(seed, 21, low=0.02, high=0.30), 2)

        return Fundamentals(
            revenue=revenue,
            gross_profit=round(revenue * _fraction(seed, 22, low=0.2, high=0.7), 2),
            operating_income=round(revenue * _fraction(seed, 23, low=0.05, high=0.4), 2),
            net_income=net_income,
            ebitda=round(revenue * _fraction(seed, 24, low=0.1, high=0.5), 2),
            eps=_scaled(seed, 25, low=0.1, high=50.0),
            book_value=_scaled(seed, 26, low=1.0, high=200.0),
            cash=_scaled(seed, 27, low=1_000_000.0, high=100_000_000_000.0),
            debt=_scaled(seed, 28, low=0.0, high=80_000_000_000.0),
            assets=_scaled(seed, 29, low=10_000_000.0, high=500_000_000_000.0),
            liabilities=_scaled(seed, 30, low=5_000_000.0, high=300_000_000_000.0),
            equity=_scaled(seed, 31, low=1_000_000.0, high=200_000_000_000.0),
            cash_flow=_scaled(seed, 32, low=-1_000_000_000.0, high=100_000_000_000.0),
        )

    async def get_financial_ratios(self, ticker: str) -> FinancialRatios:
        normalized = _require_ticker(ticker)
        seed = _digest(normalized)

        return FinancialRatios(
            pe=_scaled(seed, 40, low=5.0, high=60.0),
            forward_pe=_scaled(seed, 41, low=5.0, high=55.0),
            pb=_scaled(seed, 42, low=0.5, high=20.0),
            ps=_scaled(seed, 43, low=0.5, high=25.0),
            peg=_scaled(seed, 44, low=0.2, high=4.0),
            ev_ebitda=_scaled(seed, 45, low=3.0, high=40.0),
            roe=_fraction(seed, 46, low=0.01, high=0.5),
            roa=_fraction(seed, 47, low=0.01, high=0.3),
            roic=_fraction(seed, 48, low=0.01, high=0.4),
            gross_margin=_fraction(seed, 49, low=0.1, high=0.8),
            operating_margin=_fraction(seed, 50, low=0.05, high=0.5),
            net_margin=_fraction(seed, 51, low=0.02, high=0.4),
            current_ratio=_scaled(seed, 52, low=0.5, high=5.0),
            quick_ratio=_scaled(seed, 53, low=0.3, high=4.0),
            debt_equity=_scaled(seed, 54, low=0.0, high=3.0),
            interest_coverage=_scaled(seed, 55, low=0.5, high=50.0),
            cash_ratio=_scaled(seed, 56, low=0.1, high=3.0),
            free_cash_flow=_scaled(seed, 57, low=-1_000_000_000.0, high=80_000_000_000.0),
        )

    async def get_market_cap(self, ticker: str) -> float:
        profile = await self.get_company_profile(ticker)
        assert profile.market_cap is not None  # always populated by this mock's own get_company_profile
        return profile.market_cap

    async def get_earnings(self, ticker: str) -> list[EarningsReport]:
        normalized = _require_ticker(ticker)
        seed = _digest(normalized)
        anchor = self._reference_time.date()

        reports = []
        for period_index in range(4):
            period_seed = seed + period_index
            report_date = anchor - timedelta(days=90 * (period_index + 1))
            eps_estimate = _scaled(period_seed, 60, low=0.1, high=20.0)
            eps_actual = round(eps_estimate * _fraction(period_seed, 61, low=0.85, high=1.15), 4)
            surprise_percent = round(((eps_actual - eps_estimate) / eps_estimate) * 100, 4) if eps_estimate else 0.0
            reports.append(
                EarningsReport(
                    ticker=normalized,
                    period=f"Q{4 - period_index} {report_date.year}",
                    report_date=report_date,
                    eps_actual=eps_actual,
                    eps_estimate=eps_estimate,
                    revenue_actual=_scaled(period_seed, 62, low=1_000_000.0, high=100_000_000_000.0),
                    revenue_estimate=_scaled(period_seed, 63, low=1_000_000.0, high=100_000_000_000.0),
                    surprise_percent=surprise_percent,
                )
            )
        return reports

    async def get_dividends(self, ticker: str) -> list[Dividend]:
        normalized = _require_ticker(ticker)
        seed = _digest(normalized)
        anchor = self._reference_time.date()
        frequencies = tuple(DividendFrequency)

        dividends = []
        for period_index in range(4):
            period_seed = seed + period_index
            ex_date = anchor - timedelta(days=90 * (period_index + 1))
            dividends.append(
                Dividend(
                    ex_date=ex_date,
                    payment_date=ex_date + timedelta(days=14),
                    amount=_scaled(period_seed, 70, low=0.01, high=5.0),
                    dividend_yield=_fraction(period_seed, 71, low=0.0, high=0.08),
                    frequency=_pick(seed, 72, frequencies),
                )
            )
        return dividends

    async def get_price_history(
        self,
        ticker: str,
        interval: Interval,
        start: date | None = None,
        end: date | None = None,
    ) -> HistoricalSeries:
        """`start`/`end` bound the generated window; bars are always
        generated at `interval` granularity as timezone-aware `datetime`
        values (see `HistoricalPrice.date`'s own docstring for why). When
        `start` is omitted, exactly `_DEFAULT_BAR_COUNT` bars ending at
        `end` (or the reference time) are generated — a fixed, bounded
        default regardless of `interval`, so an intraday request never
        silently produces tens of thousands of bars.
        """
        normalized = _require_ticker(ticker)
        seed = _digest(normalized)
        step = _interval_step(interval)
        anchor = _to_datetime(end) if end is not None else self._reference_time

        if start is not None:
            bar_count = max(1, min(int((anchor - _to_datetime(start)) / step) + 1, _MAX_BARS))
        else:
            bar_count = _DEFAULT_BAR_COUNT

        bars: list[HistoricalPrice] = []
        for bar_index in range(bar_count):
            bar_time = anchor - step * (bar_count - 1 - bar_index)
            bar_seed = seed + bar_index
            # Every bound below is expressed as a fraction of a strictly
            # positive price (`base`, `upper`, or `lower`), never as a
            # fixed dollar amount subtracted from it -- this guarantees
            # every OHLC field stays positive regardless of how low `base`
            # happens to land, satisfying HistoricalPrice's own "positive
            # prices" validation by construction.
            base = _scaled(bar_seed, 80, low=10.0, high=900.0)
            open_price = base
            close_price = round(_scaled(bar_seed, 82, low=base * 0.85, high=base * 1.15), 2)
            upper = max(open_price, close_price)
            lower = min(open_price, close_price)
            high_price = round(_scaled(bar_seed, 83, low=upper, high=upper * 1.05), 2)
            low_price = round(_scaled(bar_seed, 84, low=lower * 0.95, high=lower), 2)
            bars.append(
                HistoricalPrice(
                    date=bar_time,
                    open=open_price,
                    high=high_price,
                    low=low_price,
                    close=close_price,
                    adjusted_close=close_price,
                    volume=_scaled_int(bar_seed, 85, low=10_000, high=20_000_000),
                )
            )

        return HistoricalSeries(ticker=normalized, interval=interval, prices=tuple(bars))

    async def search_symbol(self, query: str) -> list[SearchResult]:
        normalized_query = query.strip().lower()
        if not normalized_query:
            return []
        return [
            result
            for result in _SEARCH_CATALOG
            if normalized_query in result.ticker.lower() or normalized_query in result.company_name.lower()
        ]


def _to_datetime(value: date) -> datetime:
    """A `date` is anchored to midnight UTC; a `datetime` (should one ever
    be passed) is trusted as-is if already timezone-aware, else stamped as
    UTC — mirrors `NormalizationService.normalize_timestamp`'s own
    naive-input convention, kept as a tiny local helper here rather than an
    import so this infrastructure module depends only on domain models,
    never on the application-layer normalization service."""
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return datetime(value.year, value.month, value.day, tzinfo=UTC)


def _require_ticker(ticker: str) -> str:
    normalized = ticker.strip().upper()
    if not normalized:
        raise ValueError("ticker must not be blank.")
    return normalized


def _scaled(seed: int, salt: int, *, low: float, high: float) -> float:
    """Deterministically map `(seed, salt)` into `[low, high]`, rounded to 2 decimals."""
    combined = _digest(f"{seed}:{salt}")
    fraction = (combined % 1_000_000) / 1_000_000
    return round(low + fraction * (high - low), 2)


def _scaled_int(seed: int, salt: int, *, low: int, high: int) -> int:
    combined = _digest(f"{seed}:{salt}")
    return low + combined % (high - low + 1)


def _fraction(seed: int, salt: int, *, low: float, high: float) -> float:
    scaled = _scaled(seed, salt, low=low, high=high)
    return round(scaled / 100 if high > 1 else scaled, 6)


def _pick[T](seed: int, salt: int, options: tuple[T, ...]) -> T:
    combined = _digest(f"{seed}:{salt}")
    return options[combined % len(options)]


def _interval_step(interval: Interval) -> timedelta:
    return {
        Interval.ONE_MINUTE: timedelta(minutes=1),
        Interval.FIVE_MINUTES: timedelta(minutes=5),
        Interval.FIFTEEN_MINUTES: timedelta(minutes=15),
        Interval.THIRTY_MINUTES: timedelta(minutes=30),
        Interval.ONE_HOUR: timedelta(hours=1),
        Interval.ONE_DAY: timedelta(days=1),
        Interval.ONE_WEEK: timedelta(weeks=1),
        Interval.ONE_MONTH: timedelta(days=30),
    }[interval]
