"""Unit tests for Morning Brief data preparation."""

from __future__ import annotations

from app.agents.morning_brief_generator.data_preparation import prepare_brief_data
from app.schemas.intelligence import MorningIntelligence


def test_report_date_and_default_title(sample_intelligence: MorningIntelligence) -> None:
    result = prepare_brief_data(sample_intelligence)
    assert result.report_date == "2026-08-03"
    assert result.title == "MarketMind AI — Morning Brief"


def test_explicit_title_is_preserved(sample_intelligence: MorningIntelligence) -> None:
    sample_intelligence.title = "Custom Brief Title"
    result = prepare_brief_data(sample_intelligence)
    assert result.title == "Custom Brief Title"


def test_headlines_sorted_most_recent_first(sample_intelligence: MorningIntelligence) -> None:
    result = prepare_brief_data(sample_intelligence)
    assert [h.title for h in result.headlines] == ["Tech stocks rally", "Fed holds rates steady"]


def test_stocks_sorted_by_absolute_change_descending(
    sample_intelligence: MorningIntelligence,
) -> None:
    result = prepare_brief_data(sample_intelligence)
    assert [s.ticker for s in result.stocks_to_watch] == ["TSLA", "AAPL"]


def test_sector_watch_sorted_by_change_descending(sample_intelligence: MorningIntelligence) -> None:
    result = prepare_brief_data(sample_intelligence)
    assert [s.sector for s in result.sector_watch] == ["Technology", "Energy"]


def test_global_markets_sorted_by_region_then_name(
    sample_intelligence: MorningIntelligence,
) -> None:
    result = prepare_brief_data(sample_intelligence)
    assert [m.name for m in result.global_markets] == ["Nikkei 225", "FTSE 100"]


def test_risk_alerts_sorted_by_severity_then_title(
    sample_intelligence: MorningIntelligence,
) -> None:
    result = prepare_brief_data(sample_intelligence)
    assert [r.title for r in result.risk_alerts] == ["Geopolitical tension", "Rate volatility"]


def test_sources_are_deduplicated_and_sorted(sample_intelligence: MorningIntelligence) -> None:
    result = prepare_brief_data(sample_intelligence)
    assert [s.name for s in result.sources] == ["Bloomberg", "Reuters"]
    assert len(result.sources) == 2
