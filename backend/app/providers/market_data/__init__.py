"""Market-data provider abstraction: the `MarketDataProvider` interface and
its sole concrete implementation, `MockMarketDataProvider` (in-memory,
deterministic, for tests only). No real market-data API is integrated
anywhere in this package.
"""

from app.providers.market_data.mock import MockMarketDataProvider
from app.providers.market_data.provider import MarketDataProvider

__all__ = ["MarketDataProvider", "MockMarketDataProvider"]
