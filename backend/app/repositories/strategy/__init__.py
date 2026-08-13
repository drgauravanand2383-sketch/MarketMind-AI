"""Strategy Repository: persistence contract for the Strategy Evaluation Engine.

No database implementation and no business rules exist in this package's
top level — abstract interface only.
"""

from app.repositories.strategy.repository import BaseStrategyRepository

__all__ = ["BaseStrategyRepository"]
