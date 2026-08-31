"""Tests for `UniverseRegistry` and `DEFAULT_UNIVERSES`."""

from __future__ import annotations

from app.global_markets.models import PENNY_MICROCAP_REPORT_CATEGORIES, ReportCategory
from app.global_markets.universe.defaults import DEFAULT_UNIVERSES
from app.global_markets.universe.models import UniverseEntry
from app.global_markets.universe.registry import UniverseRegistry


def test_get_returns_the_configured_universe() -> None:
    registry = UniverseRegistry(
        {ReportCategory.US_EQUITY: (UniverseEntry(ticker="AAPL", name="Apple Inc."),)}
    )
    assert registry.get(ReportCategory.US_EQUITY) == (UniverseEntry(ticker="AAPL", name="Apple Inc."),)


def test_get_returns_empty_tuple_for_an_unconfigured_category() -> None:
    registry = UniverseRegistry({})
    assert registry.get(ReportCategory.US_EQUITY) == ()


def test_default_universes_cover_every_report_category() -> None:
    assert set(DEFAULT_UNIVERSES.keys()) == set(ReportCategory)


def test_default_main_category_universes_are_non_empty() -> None:
    for category in (
        ReportCategory.INDIA_EQUITY,
        ReportCategory.US_EQUITY,
        ReportCategory.CHINA_EQUITY,
        ReportCategory.FOREX,
        ReportCategory.CRYPTO,
    ):
        assert len(DEFAULT_UNIVERSES[category]) > 0


def test_default_penny_microcap_universes_are_deliberately_empty() -> None:
    """Never fabricate specific penny/micro-cap tickers from training
    data — see DEFAULT_UNIVERSES's own docstring."""
    for category in PENNY_MICROCAP_REPORT_CATEGORIES:
        assert DEFAULT_UNIVERSES[category] == ()


def test_no_duplicate_tickers_within_one_category() -> None:
    for category, entries in DEFAULT_UNIVERSES.items():
        tickers = [entry.ticker for entry in entries]
        assert len(tickers) == len(set(tickers)), f"duplicate ticker in {category}"
