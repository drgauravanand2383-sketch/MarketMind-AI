"""Trading calendar abstraction for Global Market Intelligence — see
`app.global_markets.calendar.provider.TradingCalendarProvider`'s own
docstring for the full design (approved Decision 2).
"""

from app.global_markets.calendar.continuous_calendar import CryptoCalendarProvider, ForexCalendarProvider
from app.global_markets.calendar.pandas_calendar import PandasMarketCalendarProvider
from app.global_markets.calendar.provider import TradingCalendarProvider
from app.global_markets.calendar.registry import TradingCalendarRegistry

__all__ = [
    "TradingCalendarProvider",
    "TradingCalendarRegistry",
    "PandasMarketCalendarProvider",
    "CryptoCalendarProvider",
    "ForexCalendarProvider",
]
