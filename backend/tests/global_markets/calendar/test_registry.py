"""Tests for `TradingCalendarRegistry` (`app.global_markets.calendar.registry`)."""

from __future__ import annotations

import pytest

from app.global_markets.calendar.continuous_calendar import CryptoCalendarProvider
from app.global_markets.calendar.registry import TradingCalendarRegistry
from app.global_markets.exceptions import UnsupportedMarketRegionError
from app.global_markets.models import MarketRegion


def test_get_returns_the_registered_provider() -> None:
    provider = CryptoCalendarProvider()
    registry = TradingCalendarRegistry({MarketRegion.CRYPTO: provider})

    assert registry.get(MarketRegion.CRYPTO) is provider


def test_get_raises_for_an_unregistered_region() -> None:
    registry = TradingCalendarRegistry({MarketRegion.CRYPTO: CryptoCalendarProvider()})

    with pytest.raises(UnsupportedMarketRegionError):
        registry.get(MarketRegion.INDIA)


def test_supported_regions_reflects_the_registered_set() -> None:
    registry = TradingCalendarRegistry({MarketRegion.CRYPTO: CryptoCalendarProvider()})

    assert registry.supported_regions() == (MarketRegion.CRYPTO,)
