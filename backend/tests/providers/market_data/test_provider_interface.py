"""Tests that `MarketDataProvider` is a genuine abstract contract: it
cannot be instantiated directly, and every required method is abstract."""

from __future__ import annotations

import pytest

from app.providers.market_data.provider import MarketDataProvider


def test_market_data_provider_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        MarketDataProvider()  # type: ignore[abstract]


@pytest.mark.parametrize(
    "method_name",
    [
        "get_quote",
        "get_quotes",
        "get_company_profile",
        "get_fundamentals",
        "get_financial_ratios",
        "get_market_cap",
        "get_earnings",
        "get_dividends",
        "get_price_history",
        "search_symbol",
        "provider_name",
        "health",
        "capabilities",
    ],
)
def test_every_required_method_is_abstract(method_name: str) -> None:
    assert method_name in MarketDataProvider.__abstractmethods__


def test_incomplete_subclass_cannot_be_instantiated() -> None:
    class IncompleteProvider(MarketDataProvider):
        def provider_name(self) -> str:
            return "Incomplete"

    with pytest.raises(TypeError):
        IncompleteProvider()  # type: ignore[abstract]
