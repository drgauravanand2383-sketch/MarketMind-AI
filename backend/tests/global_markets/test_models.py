"""Tests for the Global Market Intelligence taxonomy
(`app.global_markets.models`)."""

from __future__ import annotations

from app.global_markets.models import (
    MAIN_REPORT_CATEGORIES,
    PENNY_MICROCAP_REPORT_CATEGORIES,
    REPORT_CATEGORY_DEFINITIONS,
    AssetClass,
    ReportCategory,
)


def test_every_report_category_has_a_definition() -> None:
    assert set(REPORT_CATEGORY_DEFINITIONS.keys()) == set(ReportCategory)


def test_five_main_categories_rank_top_15() -> None:
    for category in MAIN_REPORT_CATEGORIES:
        assert REPORT_CATEGORY_DEFINITIONS[category].top_n == 15


def test_four_penny_microcap_categories_rank_top_20() -> None:
    for category in PENNY_MICROCAP_REPORT_CATEGORIES:
        assert REPORT_CATEGORY_DEFINITIONS[category].top_n == 20


def test_main_and_penny_categories_are_disjoint_and_cover_everything() -> None:
    main = set(MAIN_REPORT_CATEGORIES)
    penny = set(PENNY_MICROCAP_REPORT_CATEGORIES)
    assert main.isdisjoint(penny)
    assert main | penny == set(ReportCategory)


def test_total_daily_coverage_is_155_assets() -> None:
    total = sum(REPORT_CATEGORY_DEFINITIONS[category].top_n for category in ReportCategory)
    assert total == 15 * 5 + 20 * 4 == 155


def test_penny_categories_use_the_penny_stock_or_microcap_crypto_asset_class() -> None:
    for category in PENNY_MICROCAP_REPORT_CATEGORIES:
        asset_class = REPORT_CATEGORY_DEFINITIONS[category].asset_class
        assert asset_class in (AssetClass.PENNY_STOCK, AssetClass.MICROCAP_CRYPTO)


def test_low_cap_crypto_display_name_avoids_penny_coin_terminology() -> None:
    """Explicit product requirement: never call it a "penny coin" — a
    low unit price does not imply small-cap or undervalued."""
    display_name = REPORT_CATEGORY_DEFINITIONS[ReportCategory.LOW_CAP_CRYPTO].display_name
    assert display_name == "Low-Cap Crypto Discovery"
    assert "penny" not in display_name.lower()
