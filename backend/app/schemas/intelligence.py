"""Normalized intelligence schemas consumed by the Morning Brief Generator.

These Pydantic models define the shape of the synthesized intelligence
(produced upstream by the Market Intelligence Engine, AGT-011) that the
Morning Brief Generator accepts as input. No formatting or agent logic
lives here — schemas only.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field

__all__ = [
    "RiskSeverity",
    "SourceRef",
    "Headline",
    "StockWatchItem",
    "SectorPerformance",
    "GlobalMarketIndex",
    "RiskAlert",
    "MarketOverview",
    "MorningIntelligence",
]


class RiskSeverity(str, Enum):
    """Severity level of a risk alert."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SourceRef(BaseModel):
    """A reference to a data or news source cited in the brief."""

    name: str
    url: str | None = None


class Headline(BaseModel):
    """A single news headline to feature in the brief."""

    title: str
    source: SourceRef
    published_at: datetime
    url: str | None = None
    summary: str | None = None


class StockWatchItem(BaseModel):
    """A single stock flagged for the Stocks to Watch section."""

    ticker: str
    name: str
    change_percent: float
    reason: str | None = None


class SectorPerformance(BaseModel):
    """Performance of a single market sector."""

    sector: str
    change_percent: float
    note: str | None = None


class GlobalMarketIndex(BaseModel):
    """Performance of a single global market index."""

    name: str
    region: str
    change_percent: float
    value: float | None = None


class RiskAlert(BaseModel):
    """A single risk alert to surface in the brief."""

    title: str
    severity: RiskSeverity
    description: str


class MarketOverview(BaseModel):
    """A high-level narrative and metrics summary of overall market conditions."""

    summary: str
    overall_sentiment: str | None = None
    key_metrics: dict[str, float] | None = None


class MorningIntelligence(BaseModel):
    """The normalized, synthesized intelligence object the Morning Brief Generator accepts.

    Produced upstream (e.g. by the Market Intelligence Engine) and passed
    into MorningBriefGenerator.generate() unchanged.
    """

    date: date
    title: str | None = None
    market_overview: MarketOverview
    headlines: list[Headline] = Field(default_factory=list)
    stocks_to_watch: list[StockWatchItem] = Field(default_factory=list)
    sector_watch: list[SectorPerformance] = Field(default_factory=list)
    global_markets: list[GlobalMarketIndex] = Field(default_factory=list)
    risk_alerts: list[RiskAlert] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)
