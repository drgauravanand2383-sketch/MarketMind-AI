"""Alert Rule / Alert Repositories: persistence contracts for the Alert &
Notification Engine.

No database implementation and no business rules exist in this package's
top level — abstract interfaces only.
"""

from app.repositories.alerts.repository import BaseAlertRepository, BaseAlertRuleRepository

__all__ = ["BaseAlertRuleRepository", "BaseAlertRepository"]
