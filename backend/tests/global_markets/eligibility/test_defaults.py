"""Tests for `DEFAULT_ELIGIBILITY_CRITERIA` / `eligibility_provider_for_category`
(`app.global_markets.eligibility.defaults`)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.global_markets.eligibility.defaults import (
    DEFAULT_ELIGIBILITY_CRITERIA,
    PENNY_STOCK_MARKET_FOR_CATEGORY,
    eligibility_provider_for_category,
)
from app.global_markets.eligibility.models import PennyStockMarket
from app.global_markets.models import (
    MAIN_REPORT_CATEGORIES,
    PENNY_MICROCAP_REPORT_CATEGORIES,
    DataFreshnessStatus,
    DataProvenance,
    NormalizedAssetSnapshot,
    ReportCategory,
)

_PROVENANCE = DataProvenance(
    source_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
    provider="test-fixture",
    data_freshness_status=DataFreshnessStatus.LIVE,
)


def _snapshot(report_category: ReportCategory, **overrides: object) -> NormalizedAssetSnapshot:
    defaults: dict[str, object] = {
        "ticker": "TEST",
        "report_category": report_category,
        "price": 1.0,
        "market_cap": 100_000_000.0,
        "avg_daily_traded_value": 1_000_000_000.0,
        "avg_daily_volume": 10_000_000.0,
        "trading_history_days": 3650,
        "is_suspended": False,
        "is_delisted": False,
        "bid_ask_spread_percent": 0.1,
        "provenance": _PROVENANCE,
    }
    defaults.update(overrides)
    return NormalizedAssetSnapshot(**defaults)  # type: ignore[arg-type]


@pytest.mark.parametrize("category", MAIN_REPORT_CATEGORIES)
def test_main_categories_get_no_eligibility_provider(category: ReportCategory) -> None:
    assert eligibility_provider_for_category(category) is None


@pytest.mark.parametrize("category", PENNY_MICROCAP_REPORT_CATEGORIES)
def test_every_penny_microcap_category_gets_a_real_eligibility_provider(category: ReportCategory) -> None:
    assert eligibility_provider_for_category(category) is not None


def test_every_penny_stock_market_has_configured_criteria() -> None:
    assert set(DEFAULT_ELIGIBILITY_CRITERIA) == set(PennyStockMarket)


def test_category_to_market_mapping_covers_every_penny_microcap_category() -> None:
    assert set(PENNY_STOCK_MARKET_FOR_CATEGORY) == set(PENNY_MICROCAP_REPORT_CATEGORIES)


def test_us_penny_stock_uses_the_secs_own_5_dollar_penny_stock_threshold() -> None:
    provider = eligibility_provider_for_category(ReportCategory.US_PENNY_STOCK)
    assert provider is not None

    result = provider.evaluate(_snapshot(ReportCategory.US_PENNY_STOCK, price=5.01))

    assert result.eligible is False
    assert any("price" in reason for reason in result.failed_reasons)

    result = provider.evaluate(_snapshot(ReportCategory.US_PENNY_STOCK, price=4.99))
    assert "price 4.99 exceeds max 5.0" not in result.failed_reasons


def test_india_penny_stock_uses_the_rs_20_market_convention() -> None:
    provider = eligibility_provider_for_category(ReportCategory.INDIA_PENNY_STOCK)
    assert provider is not None

    result = provider.evaluate(_snapshot(ReportCategory.INDIA_PENNY_STOCK, price=20.01))

    assert result.eligible is False
    assert any("price" in reason for reason in result.failed_reasons)


def test_china_penny_stock_uses_the_10_yuan_convention() -> None:
    provider = eligibility_provider_for_category(ReportCategory.CHINA_PENNY_STOCK)
    assert provider is not None

    result = provider.evaluate(_snapshot(ReportCategory.CHINA_PENNY_STOCK, price=10.01))

    assert result.eligible is False
    assert any("price" in reason for reason in result.failed_reasons)


def test_low_cap_crypto_is_never_gated_by_unit_token_price() -> None:
    criteria = DEFAULT_ELIGIBILITY_CRITERIA[PennyStockMarket.LOW_CAP_CRYPTO]
    assert criteria.max_price is None

    provider = eligibility_provider_for_category(ReportCategory.LOW_CAP_CRYPTO)
    assert provider is not None

    # An implausibly high unit price must never itself cause rejection.
    result = provider.evaluate(
        _snapshot(
            ReportCategory.LOW_CAP_CRYPTO, price=1_000_000.0, market_cap=100_000_000.0, avg_daily_volume=1_000_000.0
        )
    )
    assert not any("price" in reason for reason in result.failed_reasons)


def test_low_cap_crypto_rejects_a_token_priced_out_by_market_cap_and_volume() -> None:
    provider = eligibility_provider_for_category(ReportCategory.LOW_CAP_CRYPTO)
    assert provider is not None

    result = provider.evaluate(
        _snapshot(
            ReportCategory.LOW_CAP_CRYPTO,
            price=0.0001,
            market_cap=900_000_000.0,  # above the $500M ceiling
            avg_daily_volume=1_000.0,  # below the $50,000 floor
        )
    )

    assert result.eligible is False
    assert any("market_cap" in reason for reason in result.failed_reasons)
    assert any("avg_daily_volume" in reason for reason in result.failed_reasons)


def test_a_snapshot_with_no_market_cap_data_is_not_rejected_on_market_cap_alone() -> None:
    """The live pipeline never populates `market_cap` today (see
    `MarketDataNormalizer`'s own docstring) — a missing field must reduce
    `data_completeness_ratio`, never be treated as a failure."""
    provider = eligibility_provider_for_category(ReportCategory.US_PENNY_STOCK)
    assert provider is not None

    result = provider.evaluate(_snapshot(ReportCategory.US_PENNY_STOCK, price=1.0, market_cap=None))

    assert result.eligible is True
    assert result.data_completeness_ratio < 1.0


_MARKET_CAP_WITHIN_BAND: dict[ReportCategory, float] = {
    # Each within its own market's [min_market_cap, max_market_cap] band
    # (see DEFAULT_ELIGIBILITY_CRITERIA) — the fixture's flat 100M default
    # only happens to satisfy US/crypto, not India's/China's higher bands.
    ReportCategory.US_PENNY_STOCK: 100_000_000.0,
    ReportCategory.INDIA_PENNY_STOCK: 1_000_000_000.0,
    ReportCategory.CHINA_PENNY_STOCK: 1_000_000_000.0,
    ReportCategory.LOW_CAP_CRYPTO: 100_000_000.0,
}


def test_an_otherwise_eligible_asset_passes_every_market() -> None:
    for category in PENNY_MICROCAP_REPORT_CATEGORIES:
        provider = eligibility_provider_for_category(category)
        assert provider is not None
        result = provider.evaluate(_snapshot(category, price=0.5, market_cap=_MARKET_CAP_WITHIN_BAND[category]))
        assert result.eligible is True, f"{category}: {result.failed_reasons}"
