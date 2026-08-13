"""Risk Analytics Repository: persistence contract for the Risk Analytics Engine.

No database implementation and no business rules exist in this package's
top level — abstract interface only.
"""

from app.repositories.risk.repository import BaseRiskAnalyticsRepository

__all__ = ["BaseRiskAnalyticsRepository"]
