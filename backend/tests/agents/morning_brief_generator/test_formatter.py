"""Unit tests for Morning Brief markdown formatting."""

from __future__ import annotations

from datetime import date

from app.agents.morning_brief_generator.data_preparation import prepare_brief_data
from app.agents.morning_brief_generator.formatter import render_markdown
from app.schemas.intelligence import MarketOverview, MorningIntelligence

REQUIRED_HEADINGS = (
    "## Market Overview",
    "## Top Headlines",
    "## Stocks to Watch",
    "## Sector Watch",
    "## Global Markets",
    "## Risk Alerts",
    "## Sources",
)


def test_render_markdown_contains_all_required_sections(
    sample_intelligence: MorningIntelligence,
) -> None:
    data = prepare_brief_data(sample_intelligence)
    markdown = render_markdown(data)

    assert markdown.startswith("# MarketMind AI — Morning Brief")
    for heading in REQUIRED_HEADINGS:
        assert heading in markdown


def test_sections_appear_in_required_order(sample_intelligence: MorningIntelligence) -> None:
    data = prepare_brief_data(sample_intelligence)
    markdown = render_markdown(data)

    headings = ["# MarketMind AI", *REQUIRED_HEADINGS]
    positions = [markdown.index(heading) for heading in headings]
    assert positions == sorted(positions)


def test_rendering_is_deterministic(sample_intelligence: MorningIntelligence) -> None:
    data = prepare_brief_data(sample_intelligence)
    assert render_markdown(data) == render_markdown(data)


def test_positive_and_negative_change_signs(sample_intelligence: MorningIntelligence) -> None:
    data = prepare_brief_data(sample_intelligence)
    markdown = render_markdown(data)
    assert "+1.20%" in markdown
    assert "-3.50%" in markdown


def test_risk_alert_severity_rendered_uppercase(sample_intelligence: MorningIntelligence) -> None:
    data = prepare_brief_data(sample_intelligence)
    markdown = render_markdown(data)
    assert "[HIGH] Geopolitical tension" in markdown


def test_empty_sections_render_placeholder_text() -> None:
    empty_intelligence = MorningIntelligence(
        date=date(2026, 8, 3),
        market_overview=MarketOverview(summary="No significant activity."),
    )
    data = prepare_brief_data(empty_intelligence)
    markdown = render_markdown(data)

    assert "_No headlines available._" in markdown
    assert "_No stocks flagged._" in markdown
    assert "_No sector data available._" in markdown
    assert "_No global market data available._" in markdown
    assert "_No risk alerts._" in markdown
    assert "_No sources recorded._" in markdown
