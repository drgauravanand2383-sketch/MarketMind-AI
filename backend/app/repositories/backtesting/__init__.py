"""Backtesting Repository: persistence contract for the Backtesting Framework.

No database implementation and no business rules exist in this package's
top level — abstract interface only.
"""

from app.repositories.backtesting.repository import BaseBacktestingRepository

__all__ = ["BaseBacktestingRepository"]
