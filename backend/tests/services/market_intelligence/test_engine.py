"""Unit tests for MarketIntelligenceEngine.

All detection exercised here is deterministic keyword/frequency matching —
no LLM, sentiment analysis, prediction, or recommendation is involved
anywhere in the engine under test.
"""

from __future__ import annotations

from typing import Any

from app.repositories.knowledge.models import KnowledgeRecord
from app.services.market_intelligence.engine import MarketIntelligenceEngine


def _record(**overrides: Any) -> KnowledgeRecord:
    defaults: dict[str, Any] = {
        "id": "rec-1",
        "title": None,
        "text": None,
        "url": None,
        "published_at": None,
        "source_provider_id": "rss",
        "metadata": {},
    }
    defaults.update(overrides)
    return KnowledgeRecord(**defaults)


# --- Unit tests -----------------------------------------------------------


def test_analyze_with_no_records_returns_empty_intelligence() -> None:
    engine = MarketIntelligenceEngine()
    result = engine.analyze([])

    assert result.total_records_analyzed == 0
    assert result.groups == []
    assert result.companies == []
    assert result.sectors == []
    assert result.countries == []
    assert result.themes == []
    assert result.unmatched_record_ids == []


def test_detects_single_company() -> None:
    engine = MarketIntelligenceEngine()
    record = _record(
        id="rec-1",
        title="Apple reports record iPhone sales",
        text="Apple Inc. posted strong quarterly earnings driven by iPhone demand.",
    )

    result = engine.analyze([record])

    assert len(result.companies) == 1
    assert result.companies[0].name == "Apple Inc."
    assert result.companies[0].mention_count == 1
    assert result.companies[0].supporting_record_ids == ["rec-1"]


def test_detects_sector() -> None:
    engine = MarketIntelligenceEngine()
    record = _record(
        id="rec-2",
        title="Tesla unveils new EV model",
        text="Tesla Inc. announced a new electric vehicle lineup this week.",
    )

    result = engine.analyze([record])

    sector_names = {sector.name for sector in result.sectors}
    assert "Automotive" in sector_names


def test_detects_country() -> None:
    engine = MarketIntelligenceEngine()
    record = _record(
        id="rec-4",
        title="Fed holds rates steady",
        text="The Federal Reserve left interest rates unchanged Monday.",
    )

    result = engine.analyze([record])

    country_names = {country.name for country in result.countries}
    assert "United States" in country_names


def test_detects_recurring_theme_across_multiple_records() -> None:
    engine = MarketIntelligenceEngine()
    records = [
        _record(
            id="rec-1",
            title="Apple reports record iPhone sales",
            text="Apple Inc. posted strong quarterly earnings driven by iPhone demand.",
        ),
        _record(
            id="rec-3",
            title="Apple and Tesla both surge on strong earnings",
            text="Shares of Apple and Tesla rallied after both reported strong quarterly earnings.",
        ),
    ]

    result = engine.analyze(records)

    theme_keywords = {theme.keyword for theme in result.themes}
    assert "earnings" in theme_keywords
    earnings_theme = next(theme for theme in result.themes if theme.keyword == "earnings")
    assert earnings_theme.occurrence_count == 2
    assert set(earnings_theme.supporting_record_ids) == {"rec-1", "rec-3"}


def test_theme_not_detected_when_it_appears_in_only_one_record() -> None:
    engine = MarketIntelligenceEngine()
    record = _record(id="rec-1", title="A unique headline", text="A wholly unique sentence.")

    result = engine.analyze([record])

    assert result.themes == []


def test_confidence_score_scales_with_supporting_record_count() -> None:
    engine = MarketIntelligenceEngine()
    records = [
        _record(id=f"rec-{i}", title="Apple reports earnings", text="Apple Inc. results.")
        for i in range(2)
    ]

    result = engine.analyze(records)

    apple_group = next(group for group in result.groups if group.group_key == "Apple Inc.")
    assert apple_group.confidence_score == 0.4  # 2 / MIN_RECORDS_FOR_FULL_CONFIDENCE (5)


def test_confidence_score_caps_at_one() -> None:
    engine = MarketIntelligenceEngine()
    records = [
        _record(id=f"rec-{i}", title="Apple reports earnings", text="Apple Inc. results.")
        for i in range(8)
    ]

    result = engine.analyze(records)

    apple_group = next(group for group in result.groups if group.group_key == "Apple Inc.")
    assert apple_group.confidence_score == 1.0


def test_traceability_supporting_record_ids_present_on_every_detection() -> None:
    engine = MarketIntelligenceEngine()
    record = _record(
        id="rec-1",
        title="Apple reports record iPhone sales",
        text="Apple Inc. posted strong quarterly earnings.",
    )

    result = engine.analyze([record])

    assert result.companies[0].supporting_record_ids == ["rec-1"]
    assert all("rec-1" in group.record_ids for group in result.groups)


# --- Multi-company tests -----------------------------------------------


def test_multiple_companies_detected_in_a_single_record() -> None:
    engine = MarketIntelligenceEngine()
    record = _record(
        id="rec-3",
        title="Apple and Tesla both surge on strong earnings",
        text="Shares of Apple and Tesla rallied after both reported strong quarterly earnings.",
    )

    result = engine.analyze([record])

    company_names = {company.name for company in result.companies}
    assert company_names == {"Apple Inc.", "Tesla Inc."}


def test_multiple_companies_each_get_their_own_group() -> None:
    engine = MarketIntelligenceEngine()
    record = _record(
        id="rec-3",
        title="Apple and Tesla both surge",
        text="Shares of Apple and Tesla rallied today.",
    )

    result = engine.analyze([record])

    group_keys = {group.group_key for group in result.groups}
    assert "Apple Inc." in group_keys
    assert "Tesla Inc." in group_keys


def test_record_belongs_to_multiple_groups_when_it_mentions_multiple_companies() -> None:
    engine = MarketIntelligenceEngine()
    record = _record(
        id="rec-3",
        title="Apple and Tesla both surge",
        text="Shares of Apple and Tesla rallied today.",
    )

    result = engine.analyze([record])

    groups_containing_record = [group for group in result.groups if "rec-3" in group.record_ids]
    assert len(groups_containing_record) == 2


# --- Duplicate news tests -----------------------------------------------


def test_duplicate_news_records_are_both_counted_as_separate_evidence() -> None:
    engine = MarketIntelligenceEngine()
    records = [
        _record(
            id="rec-4",
            title="Fed holds rates steady",
            text="The Federal Reserve left interest rates unchanged Monday.",
        ),
        _record(
            id="rec-5",
            title="Fed holds rates steady",
            text="The Federal Reserve left interest rates unchanged Monday.",
        ),
    ]

    result = engine.analyze(records)

    financial_services = next(
        sector for sector in result.sectors if sector.name == "Financial Services"
    )
    assert financial_services.mention_count == 2
    assert set(financial_services.supporting_record_ids) == {"rec-4", "rec-5"}


def test_duplicate_news_records_land_in_the_same_group() -> None:
    engine = MarketIntelligenceEngine()
    records = [
        _record(
            id="rec-4",
            title="Fed holds rates steady",
            text="The Federal Reserve left interest rates unchanged Monday.",
        ),
        _record(
            id="rec-5",
            title="Fed holds rates steady",
            text="The Federal Reserve left interest rates unchanged Monday.",
        ),
    ]

    result = engine.analyze(records)

    group = next(group for group in result.groups if group.group_key == "Financial Services")
    assert set(group.record_ids) == {"rec-4", "rec-5"}


# --- Missing metadata tests -----------------------------------------------


def test_record_with_no_title_and_no_text_is_unmatched() -> None:
    engine = MarketIntelligenceEngine()
    record = _record(id="rec-6", title=None, text=None)

    result = engine.analyze([record])

    assert result.total_records_analyzed == 1
    assert result.unmatched_record_ids == ["rec-6"]
    assert result.companies == []


def test_record_with_only_title_is_still_analyzed() -> None:
    engine = MarketIntelligenceEngine()
    record = _record(id="rec-8", title="Apple Inc. beats earnings expectations", text=None)

    result = engine.analyze([record])

    company_names = {company.name for company in result.companies}
    assert "Apple Inc." in company_names
    assert "rec-8" not in result.unmatched_record_ids


def test_record_with_only_text_is_still_analyzed() -> None:
    engine = MarketIntelligenceEngine()
    record = _record(id="rec-9", title=None, text="Tesla Inc. stock jumps on delivery numbers.")

    result = engine.analyze([record])

    company_names = {company.name for company in result.companies}
    assert "Tesla Inc." in company_names


def test_missing_metadata_records_do_not_crash_engine_and_are_not_silently_dropped() -> None:
    engine = MarketIntelligenceEngine()
    records = [
        _record(id="rec-6", title=None, text=None),
        _record(id="rec-7", title="Some headline about nothing relevant", text=None),
        _record(
            id="rec-1",
            title="Apple reports record iPhone sales",
            text="Apple Inc. posted strong quarterly earnings.",
        ),
    ]

    result = engine.analyze(records)

    assert result.total_records_analyzed == 3
    assert "rec-6" in result.unmatched_record_ids
    assert "rec-7" in result.unmatched_record_ids
    assert "rec-1" not in result.unmatched_record_ids
