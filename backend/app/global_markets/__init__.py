"""Global Market Intelligence — Phase 1 foundation.

Daily, multi-market intelligence covering nine reporting categories
across five market regions (India, US, China, Forex, Crypto), split
between five "main" Top-15 categories and four penny/micro-cap Top-20
sub-categories (see `REPORT_CATEGORY_DEFINITIONS`). Phase 1 establishes
the deterministic foundation — taxonomy, trading-calendar/session
resolution, performance-window calculation, ranking contract, and
penny/micro-cap eligibility — that later phases (real per-market data
providers, the two LLM agents, report generation, the API surface) build
on. No LLM agent, no live provider integration, and no final ranking
formula exists yet in this phase, by design.

Every submodule follows this codebase's own established layered
convention: `models.py` (Domain, no I/O), `*/engine.py` or
`*/provider.py` (Application, deterministic), no direct dependency on
any third-party library outside the one module that wraps it (see
`app.global_markets.calendar.pandas_calendar`'s own docstring for the
`pandas_market_calendars` boundary).
"""

from app.global_markets.intelligence_report import (
    AssetCommentary,
    CategoryIntelligenceReport,
    CategoryNarrative,
)
from app.global_markets.models import (
    MAIN_REPORT_CATEGORIES,
    PENNY_MICROCAP_REPORT_CATEGORIES,
    REPORT_CATEGORY_DEFINITIONS,
    AssetClass,
    AssetPerformanceProfile,
    CategoryRunOutcome,
    DataFreshnessStatus,
    DataProvenance,
    IntelligenceRun,
    IntelligenceRunStatus,
    MarketRegion,
    MarketSession,
    MarketSessionContext,
    NormalizedAssetSnapshot,
    PerformanceWindow,
    ReportCategory,
    ReportCategoryDefinition,
    WindowedPerformance,
)
from app.global_markets.ranked_asset import RankedAsset

__all__ = [
    "MarketRegion",
    "AssetClass",
    "ReportCategory",
    "ReportCategoryDefinition",
    "REPORT_CATEGORY_DEFINITIONS",
    "MAIN_REPORT_CATEGORIES",
    "PENNY_MICROCAP_REPORT_CATEGORIES",
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
    "RankedAsset",
    "AssetCommentary",
    "CategoryNarrative",
    "CategoryIntelligenceReport",
]
