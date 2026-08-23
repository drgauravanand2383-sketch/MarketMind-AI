"""Domain models for the Market Data Abstraction Layer.

Every model here is provider-agnostic: nothing in this module fetches,
computes, or caches real market data — these are the strongly-typed shapes
`app.providers.market_data.provider.MarketDataProvider` implementations
return, and the shapes `app.market_data.normalization.NormalizationService`
normalizes. No live API integration exists anywhere in this sprint.

Design note — required vs. optional fields: the sprint's field lists don't
mark every model's required/optional split explicitly (only the *prior*
Sprint 45 CompanyMetrics sprint stated "all optional except ticker/company"
in so many words). Applying that same, already-established convention
here: every model requires only the minimal fields that make it
meaningfully *that* thing at all (a quote needs a price and a timestamp to
be "a quote"; a profile needs a name) — every other field is optional,
matching real-world data-vendor gaps. Flagged per sprint precedent
(Watchlist/Screening's own flagged judgment calls).

Design note — additive `EarningsReport`: `get_earnings()` is a required
provider method, but no corresponding model is listed under Domain Models.
`EarningsReport` is introduced here to give it a strongly-typed return
shape — flagged, matching the precedent set by `Watchlist.items` (Sprint
44) and `PlanDependency`/`ExecutionNode` (Sprints 42-43): a structural gap
between a required capability and the literal model list, filled minimally
and explicitly called out rather than silently invented.

Design note — `Dividend.yield_`: the field is named `yield` in the sprint
spec, but `yield` is a reserved Python keyword and cannot be a field name.
Renamed to `dividend_yield` (matching `CompanyMetrics.dividend_yield` from
Sprint 45 for naming consistency across the codebase) — functionally the
same field, under a valid identifier.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
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


class Currency(StrEnum):
    """Supported currency codes (ISO 4217). An unrecognized code is
    rejected by pydantic's own enum-membership check at construction
    time — this satisfies the sprint's "Supported currencies" validation
    requirement without a separate runtime check."""

    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    JPY = "JPY"
    CNY = "CNY"
    INR = "INR"
    CAD = "CAD"
    AUD = "AUD"
    CHF = "CHF"
    HKD = "HKD"
    SGD = "SGD"
    KRW = "KRW"
    BRL = "BRL"


class Exchange(StrEnum):
    """Supported exchange codes. `OTHER` is an explicit catch-all so a
    real future provider covering an exchange not yet named here has a
    valid value to report, rather than every unmapped exchange being a
    hard validation failure."""

    NYSE = "NYSE"
    NASDAQ = "NASDAQ"
    AMEX = "AMEX"
    LSE = "LSE"
    NSE = "NSE"
    BSE = "BSE"
    TSE = "TSE"
    HKEX = "HKEX"
    SSE = "SSE"
    SZSE = "SZSE"
    TSX = "TSX"
    ASX = "ASX"
    EURONEXT = "EURONEXT"
    OTHER = "OTHER"


class Interval(StrEnum):
    """Supported historical-price intervals. `capabilities().supports_intraday`
    reports whether a provider serves the sub-daily members of this set."""

    ONE_MINUTE = "1m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    THIRTY_MINUTES = "30m"
    ONE_HOUR = "1h"
    ONE_DAY = "1d"
    ONE_WEEK = "1wk"
    ONE_MONTH = "1mo"

    @property
    def is_intraday(self) -> bool:
        return self in _INTRADAY_INTERVALS


_INTRADAY_INTERVALS = frozenset(
    {Interval.ONE_MINUTE, Interval.FIVE_MINUTES, Interval.FIFTEEN_MINUTES, Interval.THIRTY_MINUTES, Interval.ONE_HOUR}
)


class DividendFrequency(StrEnum):
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    SEMI_ANNUAL = "SEMI_ANNUAL"
    ANNUAL = "ANNUAL"
    IRREGULAR = "IRREGULAR"


class ProviderHealthStatus(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class MarketQuote(BaseModel):
    """A single point-in-time price quote for one ticker."""

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    price: float = Field(gt=0)
    timestamp: datetime

    change: float | None = None
    change_percent: float | None = None
    volume: int | None = Field(default=None, ge=0)
    average_volume: int | None = Field(default=None, ge=0)
    previous_close: float | None = Field(default=None, gt=0)
    open: float | None = Field(default=None, gt=0)
    day_high: float | None = Field(default=None, gt=0)
    day_low: float | None = Field(default=None, gt=0)
    currency: Currency | None = None
    exchange: Exchange | None = None

    @field_validator("ticker")
    @classmethod
    def _normalize_ticker(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("ticker must not be blank.")
        return normalized

    @field_validator("timestamp")
    @classmethod
    def _require_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware.")
        return value


class CompanyProfile(BaseModel):
    """Static/slow-changing descriptive information about one company."""

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    company_name: str = Field(min_length=1)

    exchange: Exchange | None = None
    country: str | None = None
    sector: str | None = None
    industry: str | None = None
    description: str | None = None
    website: str | None = None
    employees: int | None = Field(default=None, ge=0)
    ipo_date: date | None = None
    currency: Currency | None = None
    market_cap: float | None = Field(default=None, gt=0)
    shares_outstanding: float | None = Field(default=None, gt=0)

    @field_validator("ticker")
    @classmethod
    def _normalize_ticker(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("ticker must not be blank.")
        return normalized


class FinancialRatios(BaseModel):
    """A snapshot of one company's valuation/profitability/liquidity ratios.
    Every field is optional — real-world ratio coverage is always partial."""

    model_config = ConfigDict(extra="forbid")

    pe: float | None = None
    forward_pe: float | None = None
    pb: float | None = None
    ps: float | None = None
    peg: float | None = None
    ev_ebitda: float | None = None
    roe: float | None = None
    roa: float | None = None
    roic: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None
    current_ratio: float | None = None
    quick_ratio: float | None = None
    debt_equity: float | None = None
    interest_coverage: float | None = None
    cash_ratio: float | None = None
    free_cash_flow: float | None = None


class Fundamentals(BaseModel):
    """A snapshot of one company's core financial-statement line items.
    Every field is optional — real-world statement coverage is always partial."""

    model_config = ConfigDict(extra="forbid")

    revenue: float | None = None
    gross_profit: float | None = None
    operating_income: float | None = None
    net_income: float | None = None
    ebitda: float | None = None
    eps: float | None = None
    book_value: float | None = None
    cash: float | None = None
    debt: float | None = None
    assets: float | None = None
    liabilities: float | None = None
    equity: float | None = None
    cash_flow: float | None = None


class HistoricalPrice(BaseModel):
    """One OHLCV bar.

    Design note — `date` is typed `datetime`, not `datetime.date`: a plain
    calendar date cannot uniquely identify an intraday bar (e.g. two
    separate 1-minute bars on the same calendar day), and `Interval`
    includes intraday members (`ONE_MINUTE` through `ONE_HOUR`) alongside
    daily-and-above ones. Typing `date` as a timezone-aware `datetime`
    keeps one field name and one model shape working correctly across
    every supported interval — for `ONE_DAY`/`ONE_WEEK`/`ONE_MONTH` bars
    it simply carries a fixed time-of-day (typically midnight UTC).
    """

    model_config = ConfigDict(extra="forbid")

    date: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    adjusted_close: float | None = Field(default=None, gt=0)
    volume: int = Field(ge=0)

    @field_validator("date")
    @classmethod
    def _require_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("date must be timezone-aware.")
        return value

    @model_validator(mode="after")
    def _validate_ohlc_consistency(self) -> HistoricalPrice:
        if self.high < self.low:
            raise ValueError(f"HistoricalPrice for {self.date}: high ({self.high}) is below low ({self.low}).")
        return self


class HistoricalSeries(BaseModel):
    """An ordered price history for one ticker at a fixed interval."""

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    interval: Interval
    prices: tuple[HistoricalPrice, ...] = Field(default_factory=tuple)

    @field_validator("ticker")
    @classmethod
    def _normalize_ticker(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("ticker must not be blank.")
        return normalized

    @model_validator(mode="after")
    def _validate_prices_ordered_and_unique(self) -> HistoricalSeries:
        dates = [bar.date for bar in self.prices]
        for earlier, later in zip(dates, dates[1:], strict=False):
            if later < earlier:
                raise ValueError("HistoricalSeries.prices must be ordered by date, ascending.")
            if later == earlier:
                raise ValueError(f"HistoricalSeries.prices contains a duplicate date: {later}.")
        return self


class Dividend(BaseModel):
    """One declared dividend payment."""

    model_config = ConfigDict(extra="forbid")

    ex_date: date
    payment_date: date | None = None
    amount: float = Field(gt=0)
    dividend_yield: float | None = Field(default=None, ge=0)
    frequency: DividendFrequency | None = None


class EarningsReport(BaseModel):
    """One reported (or estimated) earnings period for one ticker."""

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    period: str = Field(min_length=1)
    report_date: date
    eps_actual: float | None = None
    eps_estimate: float | None = None
    revenue_actual: float | None = None
    revenue_estimate: float | None = None
    surprise_percent: float | None = None

    @field_validator("ticker")
    @classmethod
    def _normalize_ticker(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("ticker must not be blank.")
        return normalized


class SearchResult(BaseModel):
    """One ticker-search match."""

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    company_name: str = Field(min_length=1)
    exchange: Exchange | None = None
    country: str | None = None

    @field_validator("ticker")
    @classmethod
    def _normalize_ticker(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("ticker must not be blank.")
        return normalized


class ProviderHealth(BaseModel):
    """The outcome of `MarketDataProvider.health()`. Must never require a
    real market-data request to produce — see the provider interface's
    own docstring."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1)
    status: ProviderHealthStatus
    latency_ms: float | None = Field(default=None, ge=0)
    last_updated: datetime


class ProviderCapabilities(BaseModel):
    """What one `MarketDataProvider` implementation supports. Lets calling
    code branch on capability rather than trial-and-error calling a method
    an implementation doesn't meaningfully back."""

    model_config = ConfigDict(extra="forbid")

    supports_quotes: bool = True
    supports_history: bool = True
    supports_fundamentals: bool = True
    supports_dividends: bool = True
    supports_search: bool = True
    supports_batch: bool = True
    supports_intraday: bool = True
    rate_limit: int | None = Field(default=None, ge=0)
