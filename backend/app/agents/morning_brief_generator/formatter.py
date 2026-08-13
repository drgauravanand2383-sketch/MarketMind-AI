"""Deterministic Markdown formatting for the Morning Brief.

Every function here is a pure string-rendering step: given already-prepared
data (see data_preparation.py), it produces Markdown text. No sorting,
filtering, deduplication, or interpretation happens in this module — that is
data_preparation's responsibility. No LLM or generative summarization is
used; formatting is template-based and fully deterministic.
"""

from __future__ import annotations

from app.agents.morning_brief_generator.data_preparation import BriefRenderData
from app.schemas.intelligence import (
    GlobalMarketIndex,
    Headline,
    RiskAlert,
    SectorPerformance,
    SourceRef,
    StockWatchItem,
)

__all__ = ["render_markdown"]


def _signed_percent(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def _format_header(data: BriefRenderData) -> str:
    return f"# {data.title}\n\n**Date:** {data.report_date}\n"


def _format_market_overview(data: BriefRenderData) -> str:
    overview = data.market_overview
    lines = ["## Market Overview", "", overview.summary]
    if overview.overall_sentiment:
        lines.append(f"\n**Overall Sentiment:** {overview.overall_sentiment}")
    if overview.key_metrics:
        lines.append("")
        lines.extend(f"- **{metric}:** {value}" for metric, value in overview.key_metrics.items())
    return "\n".join(lines) + "\n"


def _format_headline(headline: Headline) -> str:
    label = f"[{headline.title}]({headline.url})" if headline.url else f"**{headline.title}**"
    line = f"- {label} — {headline.source.name} ({headline.published_at.isoformat()})"
    if headline.summary:
        line += f"\n  {headline.summary}"
    return line


def _format_top_headlines(data: BriefRenderData) -> str:
    if not data.headlines:
        return "## Top Headlines\n\n_No headlines available._\n"
    lines = ["## Top Headlines", ""]
    lines.extend(_format_headline(headline) for headline in data.headlines)
    return "\n".join(lines) + "\n"


def _format_stock(stock: StockWatchItem) -> str:
    line = f"- **{stock.ticker}** ({stock.name}): {_signed_percent(stock.change_percent)}"
    if stock.reason:
        line += f" — {stock.reason}"
    return line


def _format_stocks_to_watch(data: BriefRenderData) -> str:
    if not data.stocks_to_watch:
        return "## Stocks to Watch\n\n_No stocks flagged._\n"
    lines = ["## Stocks to Watch", ""]
    lines.extend(_format_stock(stock) for stock in data.stocks_to_watch)
    return "\n".join(lines) + "\n"


def _format_sector(sector: SectorPerformance) -> str:
    line = f"- **{sector.sector}**: {_signed_percent(sector.change_percent)}"
    if sector.note:
        line += f" — {sector.note}"
    return line


def _format_sector_watch(data: BriefRenderData) -> str:
    if not data.sector_watch:
        return "## Sector Watch\n\n_No sector data available._\n"
    lines = ["## Sector Watch", ""]
    lines.extend(_format_sector(sector) for sector in data.sector_watch)
    return "\n".join(lines) + "\n"


def _format_global_market(market: GlobalMarketIndex) -> str:
    line = f"- **{market.name}** ({market.region}): {_signed_percent(market.change_percent)}"
    if market.value is not None:
        line += f" (value: {market.value})"
    return line


def _format_global_markets(data: BriefRenderData) -> str:
    if not data.global_markets:
        return "## Global Markets\n\n_No global market data available._\n"
    lines = ["## Global Markets", ""]
    lines.extend(_format_global_market(market) for market in data.global_markets)
    return "\n".join(lines) + "\n"


def _format_risk_alert(alert: RiskAlert) -> str:
    return f"- **[{alert.severity.value.upper()}] {alert.title}** — {alert.description}"


def _format_risk_alerts(data: BriefRenderData) -> str:
    if not data.risk_alerts:
        return "## Risk Alerts\n\n_No risk alerts._\n"
    lines = ["## Risk Alerts", ""]
    lines.extend(_format_risk_alert(alert) for alert in data.risk_alerts)
    return "\n".join(lines) + "\n"


def _format_source(source: SourceRef) -> str:
    return f"- [{source.name}]({source.url})" if source.url else f"- {source.name}"


def _format_sources(data: BriefRenderData) -> str:
    if not data.sources:
        return "## Sources\n\n_No sources recorded._\n"
    lines = ["## Sources", ""]
    lines.extend(_format_source(source) for source in data.sources)
    return "\n".join(lines) + "\n"


def render_markdown(data: BriefRenderData) -> str:
    """Render fully prepared BriefRenderData into the final Markdown document.

    Args:
        data: Output of `data_preparation.prepare_brief_data`.

    Returns:
        The complete Morning Brief as a Markdown string, in section order:
        Header, Market Overview, Top Headlines, Stocks to Watch, Sector
        Watch, Global Markets, Risk Alerts, Sources.
    """
    sections = [
        _format_header(data),
        _format_market_overview(data),
        _format_top_headlines(data),
        _format_stocks_to_watch(data),
        _format_sector_watch(data),
        _format_global_markets(data),
        _format_risk_alerts(data),
        _format_sources(data),
    ]
    return "\n".join(sections)
