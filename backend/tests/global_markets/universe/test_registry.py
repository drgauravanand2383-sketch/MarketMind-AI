"""Tests for `UniverseRegistry` and `DEFAULT_UNIVERSES`."""

from __future__ import annotations

from app.global_markets.models import ReportCategory
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


def test_default_main_category_universes_support_top_15() -> None:
    """Each main category ships >= 15 verified candidates so a "Top 15"
    selection never runs short before ranking."""
    for category in (
        ReportCategory.INDIA_EQUITY,
        ReportCategory.US_EQUITY,
        ReportCategory.CHINA_EQUITY,
        ReportCategory.FOREX,
        ReportCategory.CRYPTO,
    ):
        assert len(DEFAULT_UNIVERSES[category]) >= 15


def test_low_cap_crypto_universe_is_deliberately_empty() -> None:
    """Its eligibility gate structurally rejects every candidate without a
    market-cap source — a static universe would only produce names that
    can never pass. See DEFAULT_UNIVERSES's own docstring."""
    assert DEFAULT_UNIVERSES[ReportCategory.LOW_CAP_CRYPTO] == ()


def test_equity_penny_fallback_universes_are_present_but_modest() -> None:
    """The three equity penny categories carry a small FALLBACK-ONLY
    static universe (live discovery is primary). Deliberately short — not
    padded to top_n — so it holds only verifiable names."""
    for category in (
        ReportCategory.INDIA_PENNY_STOCK,
        ReportCategory.US_PENNY_STOCK,
        ReportCategory.CHINA_PENNY_STOCK,
    ):
        entries = DEFAULT_UNIVERSES[category]
        assert 0 < len(entries) <= 20


def test_penny_fallback_universes_do_not_overlap_their_main_category() -> None:
    """A penny fallback name must not also be a main-category large-cap."""
    pairs = (
        (ReportCategory.INDIA_PENNY_STOCK, ReportCategory.INDIA_EQUITY),
        (ReportCategory.US_PENNY_STOCK, ReportCategory.US_EQUITY),
        (ReportCategory.CHINA_PENNY_STOCK, ReportCategory.CHINA_EQUITY),
    )
    for penny, main in pairs:
        penny_tickers = {e.ticker for e in DEFAULT_UNIVERSES[penny]}
        main_tickers = {e.ticker for e in DEFAULT_UNIVERSES[main]}
        assert not (penny_tickers & main_tickers), f"{penny} overlaps {main}"


def test_no_duplicate_tickers_within_one_category() -> None:
    for category, entries in DEFAULT_UNIVERSES.items():
        tickers = [entry.ticker for entry in entries]
        assert len(tickers) == len(set(tickers)), f"duplicate ticker in {category}"
