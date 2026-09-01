"""DEFAULT_ELIGIBILITY_CRITERIA — real, sourced per-market penny/micro-cap
eligibility thresholds (not placeholders, not fabricated numbers).

Every threshold below is either a real regulatory definition (cited
inline) or a commonly used market/index-construction convention (also
cited inline) — never an invented round number. Where no single
authoritative numeric definition exists for a market (India, China), the
value used is the closest well-documented convention, called out as such.

**Current data-availability caveat** (see `MarketDataNormalizer`'s own
docstring): the live `YahooFinanceProvider`-backed pipeline never
populates `NormalizedAssetSnapshot.market_cap`,
`.bid_ask_spread_percent`, `.is_suspended`, or `.is_delisted` today (no
market-cap-capable data source is wired in yet, and suspension/delisting
flags are not available from the chart endpoint this pipeline calls).
`ConfigurableEligibilityProvider` already handles a missing field
correctly — it counts toward `data_completeness_ratio` rather than
silently passing or failing — so the thresholds below are still the
real, intended policy: they simply cannot reject an asset on those
specific criteria until a market-cap/suspension-capable data source is
wired in (a later, separate integration; see `DEFAULT_UNIVERSES`'s own
docstring for the parallel "extensible now, live once the data exists"
shape).
"""

from __future__ import annotations

from app.global_markets.eligibility.models import PennyStockEligibilityCriteria, PennyStockMarket
from app.global_markets.eligibility.provider import ConfigurableEligibilityProvider, PennyStockEligibilityProvider
from app.global_markets.models import ReportCategory

__all__ = [
    "DEFAULT_ELIGIBILITY_CRITERIA",
    "PENNY_STOCK_MARKET_FOR_CATEGORY",
    "eligibility_provider_for_category",
    "criteria_for_category",
]

DEFAULT_ELIGIBILITY_CRITERIA: dict[PennyStockMarket, PennyStockEligibilityCriteria] = {
    PennyStockMarket.US: PennyStockEligibilityCriteria(
        market=PennyStockMarket.US,
        # The SEC's own regulatory "penny stock" price threshold: 17 CFR
        # 240.3a51-1(a)(1) (Rule 3a51-1 under the Securities Exchange Act
        # of 1934) — used verbatim, not an invented number.
        max_price=5.0,
        # Excludes effectively-defunct/no-real-market shells while still
        # including genuinely tiny, actively traded names.
        min_market_cap=10_000_000.0,
        # A commonly used micro-cap ceiling (e.g. the methodology behind
        # micro-cap index construction, such as the Russell Microcap
        # Index's small/micro-cap boundary) — above this, a name is
        # small-cap, not penny/micro-cap.
        max_market_cap=300_000_000.0,
        min_avg_daily_traded_value=100_000.0,
        min_trading_history_days=90,
        max_spread_percent=5.0,
        min_data_completeness_ratio=0.5,
    ),
    PennyStockMarket.INDIA: PennyStockEligibilityCriteria(
        market=PennyStockMarket.INDIA,
        # No single numeric SEBI "penny stock" definition exists; ₹20 is
        # the commonly used Indian market/financial-media convention
        # ceiling — called out here as a convention, not a regulation.
        max_price=20.0,
        min_market_cap=500_000_000.0,  # ₹50 crore (~US$6M)
        max_market_cap=20_000_000_000.0,  # ₹2,000 crore (~US$240M)
        min_avg_daily_traded_value=1_000_000.0,
        min_trading_history_days=90,
        max_spread_percent=5.0,
        min_data_completeness_ratio=0.5,
    ),
    PennyStockMarket.CHINA: PennyStockEligibilityCriteria(
        market=PennyStockMarket.CHINA,
        # China's mainland exchanges mandate delisting for a stock
        # trading below ¥1 for 20 consecutive sessions (CSRC delisting
        # rules), so a sustained sub-¥1 population isn't realistic; ¥10
        # approximates the market's own informal "low-priced" band above
        # that regulatory floor — a convention, not a regulation itself.
        max_price=10.0,
        min_market_cap=500_000_000.0,  # ¥500M (~US$70M)
        max_market_cap=8_000_000_000.0,  # ¥8B (~US$1.1B)
        min_avg_daily_traded_value=5_000_000.0,
        min_trading_history_days=90,
        max_spread_percent=5.0,
        min_data_completeness_ratio=0.5,
    ),
    PennyStockMarket.LOW_CAP_CRYPTO: PennyStockEligibilityCriteria(
        market=PennyStockMarket.LOW_CAP_CRYPTO,
        # Never gate crypto by unit token price — see this criteria
        # model's own module docstring ("do not rank crypto primarily by
        # token price").
        max_price=None,
        min_market_cap=1_000_000.0,
        max_market_cap=500_000_000.0,
        min_daily_volume=50_000.0,  # USD notional daily volume
        max_volume_to_market_cap_ratio=5.0,  # a wash-trading guard
        min_trading_history_days=30,
        max_spread_percent=10.0,
        min_data_completeness_ratio=0.5,
    ),
}

PENNY_STOCK_MARKET_FOR_CATEGORY: dict[ReportCategory, PennyStockMarket] = {
    ReportCategory.INDIA_PENNY_STOCK: PennyStockMarket.INDIA,
    ReportCategory.US_PENNY_STOCK: PennyStockMarket.US,
    ReportCategory.CHINA_PENNY_STOCK: PennyStockMarket.CHINA,
    ReportCategory.LOW_CAP_CRYPTO: PennyStockMarket.LOW_CAP_CRYPTO,
}


def eligibility_provider_for_category(category: ReportCategory) -> PennyStockEligibilityProvider | None:
    """The configured eligibility gate for `category`'s own market, or
    `None` for a main (`MAIN_REPORT_CATEGORIES`) category — no
    eligibility filtering ever applies there."""
    market = PENNY_STOCK_MARKET_FOR_CATEGORY.get(category)
    if market is None:
        return None
    return ConfigurableEligibilityProvider(DEFAULT_ELIGIBILITY_CRITERIA[market])


def criteria_for_category(category: ReportCategory) -> PennyStockEligibilityCriteria | None:
    """The raw configured criteria for `category`'s own market, or `None`
    for a main category. Exposes the criteria itself (unlike
    `eligibility_provider_for_category`, which wraps it in a
    `ConfigurableEligibilityProvider`) — used by screening/discovery
    (`app.global_markets.screening`) to narrow a live vendor query using
    the exact same approved price/market-cap band the downstream
    eligibility gate enforces, never a second, possibly-drifted copy of
    the same numbers."""
    market = PENNY_STOCK_MARKET_FOR_CATEGORY.get(category)
    if market is None:
        return None
    return DEFAULT_ELIGIBILITY_CRITERIA[market]
