"""Tests for `ConfigurableEligibilityProvider`
(`app.global_markets.eligibility.provider`)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.global_markets.eligibility.models import PennyStockEligibilityCriteria, PennyStockMarket
from app.global_markets.eligibility.provider import ConfigurableEligibilityProvider
from app.global_markets.models import (
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


def _snapshot(**overrides: object) -> NormalizedAssetSnapshot:
    defaults: dict[str, object] = {
        "ticker": "PENNY",
        "report_category": ReportCategory.INDIA_PENNY_STOCK,
        "price": 5.0,
        "market_cap": 1_000_000.0,
        "avg_daily_traded_value": 50_000.0,
        "avg_daily_volume": 10_000.0,
        "trading_history_days": 500,
        "is_suspended": False,
        "is_delisted": False,
        "bid_ask_spread_percent": 1.0,
        "provenance": _PROVENANCE,
    }
    defaults.update(overrides)
    return NormalizedAssetSnapshot(**defaults)  # type: ignore[arg-type]


def _criteria(**overrides: object) -> PennyStockEligibilityCriteria:
    defaults: dict[str, object] = {
        "market": PennyStockMarket.INDIA,
        "max_price": 10.0,
        "min_avg_daily_traded_value": 10_000.0,
        "min_trading_history_days": 90,
    }
    defaults.update(overrides)
    return PennyStockEligibilityCriteria(**defaults)  # type: ignore[arg-type]


def test_asset_passing_every_configured_criterion_is_eligible() -> None:
    provider = ConfigurableEligibilityProvider(_criteria())

    result = provider.evaluate(_snapshot())

    assert result.eligible is True
    assert result.failed_reasons == ()


def test_price_above_max_is_rejected_with_a_reason() -> None:
    provider = ConfigurableEligibilityProvider(_criteria(max_price=10.0))

    result = provider.evaluate(_snapshot(price=15.0))

    assert result.eligible is False
    assert any("price" in reason for reason in result.failed_reasons)


def test_suspended_asset_is_excluded_by_default() -> None:
    provider = ConfigurableEligibilityProvider(_criteria())

    result = provider.evaluate(_snapshot(is_suspended=True))

    assert result.eligible is False
    assert "suspended" in result.failed_reasons


def test_delisted_asset_is_excluded_by_default() -> None:
    provider = ConfigurableEligibilityProvider(_criteria())

    result = provider.evaluate(_snapshot(is_delisted=True))

    assert result.eligible is False
    assert "delisted" in result.failed_reasons


def test_exclude_suspended_false_lets_a_suspended_asset_pass_that_check() -> None:
    provider = ConfigurableEligibilityProvider(_criteria(exclude_suspended=False))

    result = provider.evaluate(_snapshot(is_suspended=True))

    assert "suspended" not in result.failed_reasons


def test_missing_field_reduces_completeness_but_is_not_a_pass_or_fail() -> None:
    """A genuinely missing data point must never be silently treated as a pass or a fail."""
    provider = ConfigurableEligibilityProvider(_criteria(max_price=10.0))

    result = provider.evaluate(_snapshot(price=None))

    assert result.data_completeness_ratio < 1.0
    assert not any("price" in reason for reason in result.failed_reasons)


def test_low_data_completeness_fails_eligibility_when_below_the_configured_minimum() -> None:
    provider = ConfigurableEligibilityProvider(
        _criteria(min_data_completeness_ratio=0.99, max_market_cap=None)
    )

    result = provider.evaluate(_snapshot(price=None))

    assert result.eligible is False
    assert any("completeness" in reason for reason in result.failed_reasons)


def test_crypto_market_never_gates_on_unit_token_price() -> None:
    """Explicit product requirement: a $0.001 token is not automatically
    small-cap or undervalued — a Low-Cap Crypto criteria config leaves
    max_price unset and gates on market cap / volume instead."""
    criteria = PennyStockEligibilityCriteria(
        market=PennyStockMarket.LOW_CAP_CRYPTO,
        max_price=None,
        min_market_cap=1_000_000.0,
        max_market_cap=500_000_000.0,
        min_daily_volume=50_000.0,
    )
    provider = ConfigurableEligibilityProvider(criteria)

    result = provider.evaluate(
        _snapshot(
            ticker="MICROCOIN",
            report_category=ReportCategory.LOW_CAP_CRYPTO,
            price=0.0000001,
            market_cap=5_000_000.0,
            avg_daily_volume=100_000.0,
        )
    )

    assert result.eligible is True


def test_volume_to_market_cap_ratio_above_max_is_rejected() -> None:
    criteria = _criteria(max_volume_to_market_cap_ratio=0.5, max_market_cap=None)
    provider = ConfigurableEligibilityProvider(criteria)

    result = provider.evaluate(_snapshot(avg_daily_volume=900_000.0, market_cap=1_000_000.0))

    assert result.eligible is False
    assert any("volume_to_market_cap_ratio" in reason for reason in result.failed_reasons)


def test_trading_history_below_minimum_is_rejected() -> None:
    provider = ConfigurableEligibilityProvider(_criteria(min_trading_history_days=90))

    result = provider.evaluate(_snapshot(trading_history_days=10))

    assert result.eligible is False
    assert any("trading_history_days" in reason for reason in result.failed_reasons)


def test_india_and_us_criteria_are_independently_configurable() -> None:
    """Different markets must not share thresholds — the whole point of a
    per-market eligibility profile."""
    india = PennyStockEligibilityCriteria(market=PennyStockMarket.INDIA, max_price=100.0)
    us = PennyStockEligibilityCriteria(market=PennyStockMarket.US, max_price=5.0)

    india_result = ConfigurableEligibilityProvider(india).evaluate(_snapshot(price=50.0))
    us_result = ConfigurableEligibilityProvider(us).evaluate(_snapshot(price=50.0))

    assert india_result.eligible is True
    assert us_result.eligible is False
