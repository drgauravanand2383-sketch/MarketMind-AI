"""Core domain models for Global Market Intelligence.

Phase 1 foundation: the shared taxonomy and cross-cutting data shapes
every other `app.global_markets.*` subpackage (calendar, session,
performance, ranking, eligibility) and `app.workflows.global_markets`
build on. No I/O, no provider-specific logic, no ranking formula lives
here — this module only defines what a "market region," a "report
category," a "trading session," and a "normalized asset snapshot" *are*.

Two orthogonal axes, deliberately kept separate (never merged into one
enum): `MarketRegion` (a calendar/timezone concern — which market's
trading calendar governs freshness) and `AssetClass` (what kind of
instrument this is). `ReportCategory` is the one fixed, user-facing
taxonomy of the nine reporting categories this module produces, each an
explicit `(MarketRegion, AssetClass)` pair via
`REPORT_CATEGORY_DEFINITIONS` — never recomputed or hardcoded ad hoc
inside an agent or workflow, per this module's own "centralized
enums/configuration/domain models" requirement.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "MarketRegion",
    "AssetClass",
    "ReportCategory",
    "ReportCategoryDefinition",
    "REPORT_CATEGORY_DEFINITIONS",
    "PerformanceWindow",
    "DataFreshnessStatus",
    "DataProvenance",
    "MarketSession",
    "MarketSessionContext",
    "WindowedPerformance",
    "AssetPerformanceProfile",
    "NormalizedAssetSnapshot",
    "IntelligenceRunStatus",
    "CategoryRunOutcome",
    "IntelligenceRun",
]


class MarketRegion(StrEnum):
    """Which market's trading calendar/timezone governs a result's
    freshness. A calendar concern, not an instrument-type concern —
    FOREX and CRYPTO carry their own members (rather than folding under a
    generic GLOBAL) precisely because they need their own session/freshness
    rules (§ approved Decision 1/2), not because they belong to a country.
    """

    INDIA = "INDIA"
    US = "US"
    CHINA = "CHINA"
    FOREX = "FOREX"
    CRYPTO = "CRYPTO"


class AssetClass(StrEnum):
    """What kind of instrument a ranked asset is — orthogonal to `MarketRegion`.

    `PENNY_STOCK` and `MICROCAP_CRYPTO` are distinct from `EQUITY`/`CRYPTO`
    because eligibility rules genuinely differ (a normal equity ranking has
    no penny-stock-style eligibility gate at all), not because the
    underlying instrument type differs.
    """

    EQUITY = "EQUITY"
    FOREX = "FOREX"
    CRYPTO = "CRYPTO"
    PENNY_STOCK = "PENNY_STOCK"
    MICROCAP_CRYPTO = "MICROCAP_CRYPTO"


class ReportCategory(StrEnum):
    """The nine fixed, user-facing reporting categories.

    Every category maps to exactly one `(MarketRegion, AssetClass)` pair
    via `REPORT_CATEGORY_DEFINITIONS` below — the single source of truth
    for that mapping and for each category's `top_n`/display name. Never
    combine categories into one mixed ranking (explicit product
    requirement) — each category is ranked, filtered, and reported
    independently throughout this module.
    """

    INDIA_EQUITY = "INDIA_EQUITY"
    US_EQUITY = "US_EQUITY"
    CHINA_EQUITY = "CHINA_EQUITY"
    FOREX = "FOREX"
    CRYPTO = "CRYPTO"
    INDIA_PENNY_STOCK = "INDIA_PENNY_STOCK"
    US_PENNY_STOCK = "US_PENNY_STOCK"
    CHINA_PENNY_STOCK = "CHINA_PENNY_STOCK"
    LOW_CAP_CRYPTO = "LOW_CAP_CRYPTO"


class ReportCategoryDefinition(BaseModel):
    """One category's fixed identity: which market region governs its
    calendar, what kind of instrument it ranks, how many assets it reports,
    and its product-facing display name."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: ReportCategory
    market_region: MarketRegion
    asset_class: AssetClass
    top_n: int = Field(gt=0)
    display_name: str


REPORT_CATEGORY_DEFINITIONS: dict[ReportCategory, ReportCategoryDefinition] = {
    ReportCategory.INDIA_EQUITY: ReportCategoryDefinition(
        category=ReportCategory.INDIA_EQUITY,
        market_region=MarketRegion.INDIA,
        asset_class=AssetClass.EQUITY,
        top_n=15,
        display_name="India Stocks",
    ),
    ReportCategory.US_EQUITY: ReportCategoryDefinition(
        category=ReportCategory.US_EQUITY,
        market_region=MarketRegion.US,
        asset_class=AssetClass.EQUITY,
        top_n=15,
        display_name="US Stocks",
    ),
    ReportCategory.CHINA_EQUITY: ReportCategoryDefinition(
        category=ReportCategory.CHINA_EQUITY,
        market_region=MarketRegion.CHINA,
        asset_class=AssetClass.EQUITY,
        top_n=15,
        display_name="China Stocks",
    ),
    ReportCategory.FOREX: ReportCategoryDefinition(
        category=ReportCategory.FOREX,
        market_region=MarketRegion.FOREX,
        asset_class=AssetClass.FOREX,
        top_n=15,
        display_name="Forex",
    ),
    ReportCategory.CRYPTO: ReportCategoryDefinition(
        category=ReportCategory.CRYPTO,
        market_region=MarketRegion.CRYPTO,
        asset_class=AssetClass.CRYPTO,
        top_n=15,
        display_name="Major Crypto",
    ),
    ReportCategory.INDIA_PENNY_STOCK: ReportCategoryDefinition(
        category=ReportCategory.INDIA_PENNY_STOCK,
        market_region=MarketRegion.INDIA,
        asset_class=AssetClass.PENNY_STOCK,
        top_n=20,
        display_name="India Penny Stocks",
    ),
    ReportCategory.US_PENNY_STOCK: ReportCategoryDefinition(
        category=ReportCategory.US_PENNY_STOCK,
        market_region=MarketRegion.US,
        asset_class=AssetClass.PENNY_STOCK,
        top_n=20,
        display_name="US Penny Stocks",
    ),
    ReportCategory.CHINA_PENNY_STOCK: ReportCategoryDefinition(
        category=ReportCategory.CHINA_PENNY_STOCK,
        market_region=MarketRegion.CHINA,
        asset_class=AssetClass.PENNY_STOCK,
        top_n=20,
        display_name="China Penny Stocks",
    ),
    ReportCategory.LOW_CAP_CRYPTO: ReportCategoryDefinition(
        category=ReportCategory.LOW_CAP_CRYPTO,
        market_region=MarketRegion.CRYPTO,
        asset_class=AssetClass.MICROCAP_CRYPTO,
        top_n=20,
        # Deliberately not "Low-Cap Penny Crypto"/"Penny Coins" — a token's
        # low unit price alone does not imply it is small-cap or
        # undervalued; see PennyStockEligibilityCriteria's own docstring.
        display_name="Low-Cap Crypto Discovery",
    ),
}

MAIN_REPORT_CATEGORIES: tuple[ReportCategory, ...] = (
    ReportCategory.INDIA_EQUITY,
    ReportCategory.US_EQUITY,
    ReportCategory.CHINA_EQUITY,
    ReportCategory.FOREX,
    ReportCategory.CRYPTO,
)
"""The five categories `GlobalMarketsResearchAgent` (a later phase) is responsible for."""

PENNY_MICROCAP_REPORT_CATEGORIES: tuple[ReportCategory, ...] = (
    ReportCategory.INDIA_PENNY_STOCK,
    ReportCategory.US_PENNY_STOCK,
    ReportCategory.CHINA_PENNY_STOCK,
    ReportCategory.LOW_CAP_CRYPTO,
)
"""The four categories `PennyMicrocapIntelligenceAgent` (a later phase) is responsible for."""


class PerformanceWindow(StrEnum):
    """A trailing performance lookback window. See
    `app.global_markets.performance.engine.PerformanceCalculationService`
    for how each window's *observation methodology* differs by
    `MarketRegion` (trading-session-aware for equities, continuous for
    crypto, market-week-aware for forex) — this enum only names the six
    windows, it carries no methodology itself.
    """

    D10 = "10D"
    D15 = "15D"
    M1 = "1M"
    M3 = "3M"
    M6 = "6M"
    Y1 = "1Y"


class DataFreshnessStatus(StrEnum):
    """How current a result is, relative to that market's own trading
    calendar — never inferred from wall-clock recency alone. Distinct from
    (but conceptually aligned with) `app.services.market_snapshot.models
    .MarketSnapshotStatus.FRESH/STALE`: that enum also encodes provider
    *failure* outcomes (rate-limited, unavailable, ...), which belong to a
    provider-fetch result, not to a calendar-freshness judgement — kept
    separate rather than overloading one enum with two concerns.
    """

    LIVE = "LIVE"
    """Within the market's own currently-open session."""
    PREVIOUS_CLOSE = "PREVIOUS_CLOSE"
    """The market is closed; this is its last completed session's data —
    never presented as "today's" performance for a session that hasn't
    happened yet."""
    STALE = "STALE"
    """Older than the market-specific freshness cutoff — the underlying
    provider/session data could not be refreshed as recently as expected."""
    UNAVAILABLE = "UNAVAILABLE"
    """No usable session/data could be resolved at all."""


class DataProvenance(BaseModel):
    """Per-datapoint provenance, attached to any fetched or derived value
    so it is always traceable to what produced it and when — the
    `source_timestamp`/`retrieved_at`/`data_freshness_status` fields the
    architectural rule requires, at the granularity of one data point
    (see `MarketSessionContext` for the market-level calendar facts these
    per-datapoint values are judged against).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_timestamp: datetime
    """The provider's own timestamp for this value (e.g. a quote's or bar's own time)."""
    retrieved_at: datetime
    """When this system fetched/computed this value."""
    provider: str
    data_freshness_status: DataFreshnessStatus


class MarketSession(BaseModel):
    """One resolved trading session for a `MarketRegion` — its own local
    trading-calendar date, and open/close instants in UTC (always
    timezone-aware; never a naive datetime, matching this codebase's
    existing convention throughout `app.services.market_snapshot`).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    market_region: MarketRegion
    session_date: date
    open_at: datetime
    close_at: datetime


class MarketSessionContext(BaseModel):
    """The full "what does this market's calendar say right now" bundle —
    built once per `MarketRegion` per run by
    `app.global_markets.session.resolver.MarketSessionResolutionService`,
    and read by every downstream stage instead of each re-deriving
    calendar facts itself. This is the architectural rule's own required
    field set, made concrete: `market_timezone`, `market_session_date`,
    `last_completed_session`, `data_freshness_status`, `as_of_timestamp`,
    and `retrieved_at` all appear below.

    Never assume two `MarketSessionContext`s built in the same run share a
    `market_session_date` — that is the entire point of resolving one
    independently per market region (approved Decision 1).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    market_region: MarketRegion
    market_timezone: str
    """IANA timezone name, e.g. "Asia/Kolkata" — never a fixed UTC offset."""
    retrieved_at: datetime
    """When this context itself was computed (UTC)."""
    as_of_timestamp: datetime
    """The instant every "is it open"/"what's the latest session" fact below was evaluated against (UTC)."""
    is_trading_now: bool
    is_holiday: bool
    market_session_date: date
    """The current (if open) or most recently started local trading date."""
    last_completed_session: MarketSession | None
    """`None` only if this market has never had a session in the queried range."""
    data_freshness_status: DataFreshnessStatus
    freshness_cutoff: datetime | None
    """The UTC instant beyond which a *later fetch stage's* own retrieved
    data for this market should be considered `STALE` rather than
    `PREVIOUS_CLOSE` — informational only, never applied to this
    context's own `data_freshness_status` (which is always exactly
    `LIVE`/`PREVIOUS_CLOSE`/`UNAVAILABLE`, determined purely from the
    calendar, never a wall-clock-elapsed heuristic — see
    `MarketSessionResolutionService.resolve`'s own comment for why).
    `None` when not applicable (the market is currently open, or no
    completed session exists at all)."""


class WindowedPerformance(BaseModel):
    """One `PerformanceWindow`'s computed return for one asset, with both
    the raw values and the observation metadata the architectural rule
    requires ("expose both raw return values and metadata explaining the
    observation window/source timestamp").
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    window: PerformanceWindow
    start_value: float
    end_value: float
    percent_change: float
    observation_start: datetime
    observation_end: datetime
    periods_used: int = Field(ge=0)
    """The number of trading sessions (equities), calendar days (crypto),
    or market-week days (forex) actually used — see the performance
    engine's own docstring for the exact methodology per `MarketRegion`."""
    is_complete: bool
    """`False` when the asset's available history could not fully satisfy
    the requested window (e.g. a recently-listed company for a `1Y`
    window) — the window is still reported, never silently dropped, but
    flagged as partial rather than presented as a full-window return."""


class AssetPerformanceProfile(BaseModel):
    """All computed `WindowedPerformance` entries for one asset, plus the
    provenance of the historical series they were derived from."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ticker: str
    windows: tuple[WindowedPerformance, ...] = Field(default_factory=tuple)
    provenance: DataProvenance

    def window(self, period: PerformanceWindow) -> WindowedPerformance | None:
        """The computed performance for `period`, or `None` if it wasn't computed for this asset."""
        for entry in self.windows:
            if entry.window is period:
                return entry
        return None


class NormalizedAssetSnapshot(BaseModel):
    """One asset's normalized, cross-market-comparable snapshot — the
    shape every downstream stage (eligibility, ranking) consumes,
    regardless of which provider or `ReportCategory` produced it. Never a
    fabricated value: a field the source genuinely lacks is `None`,
    contributing to a lower observed data completeness rather than being
    guessed — matches this codebase's existing "never fabricate" rule
    (see `app.market_data.models` and `app.services.market_snapshot
    .models.MarketSnapshotResult`, the same discipline applied here).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    ticker: str
    report_category: ReportCategory
    name: str | None = None
    price: float | None = None
    currency: str | None = None
    market_cap: float | None = None
    fully_diluted_valuation: float | None = None
    avg_daily_volume: float | None = None
    avg_daily_traded_value: float | None = None
    trading_history_days: int | None = None
    is_suspended: bool = False
    is_delisted: bool = False
    bid_ask_spread_percent: float | None = None
    provenance: DataProvenance


class IntelligenceRunStatus(StrEnum):
    """One `IntelligenceRun`'s overall status, derived from its own
    `category_outcomes` (never set independently of them — see
    `IntelligenceRun.derive_status`)."""

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    """Every category succeeded."""
    PARTIAL = "PARTIAL"
    """At least one category succeeded and at least one failed — the
    "one failed source must not crash the entire report" requirement,
    made a first-class, queryable status rather than an all-or-nothing
    success flag."""
    FAILED = "FAILED"
    """Every category failed."""


class CategoryRunOutcome(BaseModel):
    """One `ReportCategory`'s own outcome within an `IntelligenceRun` —
    independently resolved, independently persisted, independently
    retryable (a later phase's concern; Phase 1 records the outcome
    shape a retry mechanism would need)."""

    model_config = ConfigDict(extra="forbid")

    category: ReportCategory
    succeeded: bool
    market_session_context: MarketSessionContext | None = None
    error: str | None = None


class IntelligenceRun(BaseModel):
    """One daily (or manual/retry) Global Market Intelligence run — the
    persisted "Persist Daily Intelligence Run" entity from this feature's
    own orchestration diagram. Phase 1 persists run-level tracking only;
    per-asset ranked results (`RankedAsset`, `AssetRiskAssessment`, ...)
    are a later phase's concern, once real per-market data/ranking
    exists to produce them — see `app.repositories.global_markets` for
    the persistence boundary.

    `run_date` is the *logical* IST calendar date this run represents
    (the master 08:30 Asia/Kolkata scheduler's own trading date) — never
    conflated with any individual category's own `market_session_date`,
    which is independently resolved per `MarketSessionContext` (approved
    Decision 1).

    Lives in this core `app.global_markets.models` module — not in
    `app.workflows.global_markets` — specifically so
    `app.repositories.global_markets` can depend on it without importing
    the workflow package (which itself depends on the repository
    package): this module has no dependency on either, breaking what
    would otherwise be a real import cycle.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    run_date: date
    status: IntelligenceRunStatus
    category_outcomes: tuple[CategoryRunOutcome, ...] = Field(default_factory=tuple)
    triggered_by: str = Field(min_length=1)
    started_at: datetime
    completed_at: datetime | None = None

    @staticmethod
    def derive_status(category_outcomes: tuple[CategoryRunOutcome, ...]) -> IntelligenceRunStatus:
        """The one place run-level status is computed from category
        outcomes — never set independently, so a run's own `status` can
        never drift from what its `category_outcomes` actually say."""
        if not category_outcomes:
            return IntelligenceRunStatus.RUNNING
        succeeded = sum(1 for outcome in category_outcomes if outcome.succeeded)
        if succeeded == len(category_outcomes):
            return IntelligenceRunStatus.COMPLETED
        if succeeded == 0:
            return IntelligenceRunStatus.FAILED
        return IntelligenceRunStatus.PARTIAL
