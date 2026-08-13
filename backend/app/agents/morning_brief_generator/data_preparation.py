"""Deterministic data preparation for the Morning Brief.

Transforms a normalized MorningIntelligence object into BriefRenderData:
ordered, deduplicated, and bounded structures ready for direct rendering.
No markdown and no interpretation of content occurs here — only ordering,
deduplication, and bounding. Formatting is handled entirely by formatter.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.intelligence import (
    GlobalMarketIndex,
    Headline,
    MarketOverview,
    MorningIntelligence,
    RiskAlert,
    RiskSeverity,
    SectorPerformance,
    SourceRef,
    StockWatchItem,
)

__all__ = ["MAX_HEADLINES", "MAX_STOCKS_TO_WATCH", "BriefRenderData", "prepare_brief_data"]

MAX_HEADLINES = 10
MAX_STOCKS_TO_WATCH = 10

DEFAULT_TITLE = "MarketMind AI — Morning Brief"

_SEVERITY_RANK: dict[RiskSeverity, int] = {
    RiskSeverity.CRITICAL: 0,
    RiskSeverity.HIGH: 1,
    RiskSeverity.MEDIUM: 2,
    RiskSeverity.LOW: 3,
}


@dataclass(frozen=True, slots=True)
class BriefRenderData:
    """Ordered, bounded data ready for markdown rendering. No formatting logic."""

    report_date: str
    title: str
    market_overview: MarketOverview
    headlines: tuple[Headline, ...]
    stocks_to_watch: tuple[StockWatchItem, ...]
    sector_watch: tuple[SectorPerformance, ...]
    global_markets: tuple[GlobalMarketIndex, ...]
    risk_alerts: tuple[RiskAlert, ...]
    sources: tuple[SourceRef, ...]


def prepare_brief_data(intelligence: MorningIntelligence) -> BriefRenderData:
    """Prepare normalized intelligence for deterministic rendering.

    Applies ordering, deduplication, and bounding rules only; no field is
    reinterpreted or recomputed beyond what these rules require.

    Args:
        intelligence: The normalized intelligence object to prepare.

    Returns:
        A BriefRenderData instance ready to pass to `formatter.render_markdown`.
    """
    headlines = tuple(
        sorted(intelligence.headlines, key=lambda h: h.published_at, reverse=True)[:MAX_HEADLINES]
    )
    stocks_to_watch = tuple(
        sorted(
            intelligence.stocks_to_watch,
            key=lambda s: abs(s.change_percent),
            reverse=True,
        )[:MAX_STOCKS_TO_WATCH]
    )
    sector_watch = tuple(
        sorted(intelligence.sector_watch, key=lambda s: s.change_percent, reverse=True)
    )
    global_markets = tuple(
        sorted(intelligence.global_markets, key=lambda m: (m.region, m.name))
    )
    risk_alerts = tuple(
        sorted(
            intelligence.risk_alerts,
            key=lambda r: (_SEVERITY_RANK[r.severity], r.title),
        )
    )
    deduplicated_sources = {source.name: source for source in intelligence.sources}
    sources = tuple(sorted(deduplicated_sources.values(), key=lambda s: s.name))

    return BriefRenderData(
        report_date=intelligence.date.isoformat(),
        title=intelligence.title or DEFAULT_TITLE,
        market_overview=intelligence.market_overview,
        headlines=headlines,
        stocks_to_watch=stocks_to_watch,
        sector_watch=sector_watch,
        global_markets=global_markets,
        risk_alerts=risk_alerts,
        sources=sources,
    )
