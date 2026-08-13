"""Alert & Notification Engine: consumes Signal Detection results and
decides whether an alert should be created, why, how important it is, and
which notification channels would be eligible.

No email, SMS, push notification, Telegram, Discord, Slack, or webhook
integration exists anywhere in this package, and no trade is ever
executed — this engine only makes the decision. Actual delivery providers
are implemented in a future sprint.
"""

from __future__ import annotations

from app.alerts.exceptions import (
    AlertEngineError,
    AlertNotFoundError,
    AlertRuleNotFoundError,
    DuplicateAlertRuleNameError,
    MaxAlertRulesExceededError,
    MaxChannelsExceededError,
)
from app.alerts.models import (
    Alert,
    AlertBatch,
    AlertCondition,
    AlertOperator,
    AlertPriority,
    AlertRule,
    AlertStatus,
    NotificationChannel,
)
from app.alerts.engine import AlertService

__all__ = [
    "AlertService",
    "AlertOperator",
    "NotificationChannel",
    "AlertStatus",
    "AlertPriority",
    "AlertCondition",
    "AlertRule",
    "Alert",
    "AlertBatch",
    "AlertEngineError",
    "AlertRuleNotFoundError",
    "AlertNotFoundError",
    "DuplicateAlertRuleNameError",
    "MaxAlertRulesExceededError",
    "MaxChannelsExceededError",
]
