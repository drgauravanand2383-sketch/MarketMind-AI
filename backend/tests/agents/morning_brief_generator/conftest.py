"""Shared fixtures for Morning Brief Generator tests."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

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


@pytest.fixture
def sample_intelligence() -> MorningIntelligence:
    """A MorningIntelligence instance covering every section with edge cases
    (out-of-order headlines, mixed-sign changes, mixed severities, and a
    duplicate source) for deterministic ordering assertions."""
    reuters = SourceRef(name="Reuters", url="https://reuters.com")
    bloomberg = SourceRef(name="Bloomberg", url="https://bloomberg.com")

    return MorningIntelligence(
        date=date(2026, 8, 3),
        title=None,
        market_overview=MarketOverview(
            summary="Markets opened mixed amid inflation data.",
            overall_sentiment="Neutral",
            key_metrics={"S&P 500": 5123.45, "VIX": 14.2},
        ),
        headlines=[
            Headline(
                title="Fed holds rates steady",
                source=reuters,
                published_at=datetime(2026, 8, 3, 6, 0, tzinfo=timezone.utc),
                url="https://reuters.com/fed",
                summary="The Federal Reserve left rates unchanged.",
            ),
            Headline(
                title="Tech stocks rally",
                source=bloomberg,
                published_at=datetime(2026, 8, 3, 8, 0, tzinfo=timezone.utc),
                url=None,
                summary=None,
            ),
        ],
        stocks_to_watch=[
            StockWatchItem(
                ticker="AAPL", name="Apple Inc.", change_percent=1.2, reason="Earnings beat"
            ),
            StockWatchItem(
                ticker="TSLA", name="Tesla Inc.", change_percent=-3.5, reason="Delivery miss"
            ),
        ],
        sector_watch=[
            SectorPerformance(sector="Technology", change_percent=2.1, note=None),
            SectorPerformance(sector="Energy", change_percent=-1.4, note="Oil prices fell"),
        ],
        global_markets=[
            GlobalMarketIndex(name="Nikkei 225", region="Asia", change_percent=0.5, value=39000.1),
            GlobalMarketIndex(name="FTSE 100", region="Europe", change_percent=-0.2, value=8100.0),
        ],
        risk_alerts=[
            RiskAlert(
                title="Rate volatility",
                severity=RiskSeverity.MEDIUM,
                description="Bond yields fluctuating.",
            ),
            RiskAlert(
                title="Geopolitical tension",
                severity=RiskSeverity.HIGH,
                description="Escalation in trade talks.",
            ),
        ],
        sources=[reuters, bloomberg, SourceRef(name="Reuters", url="https://reuters.com")],
    )
