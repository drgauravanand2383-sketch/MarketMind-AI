"""Exception hierarchy for the Alert & Notification Engine's application layer.

Self-contained model constraints (unknown operator, unknown field, invalid
BETWEEN, empty IN/NOT_IN, missing value, negative cooldown, unknown
notification channel, duplicate condition id) are enforced by
`app.alerts.models` itself and raise a plain `pydantic.ValidationError` —
see that module's docstring. This hierarchy covers only what
`AlertService` enforces: rules that need injected, runtime-configurable
state (a maximum rule count, a maximum channel count, duplicate rule
names) or that depend on existing repository state (not found).
"""

from __future__ import annotations

__all__ = [
    "AlertEngineError",
    "AlertRuleNotFoundError",
    "AlertNotFoundError",
    "DuplicateAlertRuleNameError",
    "MaxAlertRulesExceededError",
    "MaxChannelsExceededError",
]


class AlertEngineError(Exception):
    """Base class for every error raised by the Alert & Notification Engine's application layer."""

    def __init__(self, message: str, *, rule_id: str | None = None, alert_id: str | None = None) -> None:
        self.rule_id = rule_id
        self.alert_id = alert_id
        super().__init__(message)


class AlertRuleNotFoundError(AlertEngineError):
    """Raised when no alert rule exists for the given id."""

    def __init__(self, rule_id: str) -> None:
        super().__init__(f"No alert rule found with id {rule_id!r}.", rule_id=rule_id)


class AlertNotFoundError(AlertEngineError):
    """Raised when no alert exists for the given id."""

    def __init__(self, alert_id: str) -> None:
        super().__init__(f"No alert found with id {alert_id!r}.", alert_id=alert_id)


class DuplicateAlertRuleNameError(AlertEngineError):
    """Raised when creating/renaming/duplicating a rule to a name already in use.

    Only raised when `AlertService` was constructed with
    `enforce_unique_names=True` (the default).
    """

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"An alert rule named {name!r} already exists.")


class MaxAlertRulesExceededError(AlertEngineError):
    """Raised when creating a rule would exceed the configured maximum
    number of registered alert rules."""

    def __init__(self, limit: int, actual: int) -> None:
        self.limit = limit
        self.actual = actual
        super().__init__(
            f"Already have {actual} registered alert rules, exceeding the configured maximum of {limit}."
        )


class MaxChannelsExceededError(AlertEngineError):
    """Raised when a rule's channel count would exceed the configured maximum."""

    def __init__(self, rule_id: str | None, limit: int, actual: int) -> None:
        self.limit = limit
        self.actual = actual
        super().__init__(
            f"Rule has {actual} channels, exceeding the configured maximum of {limit}.", rule_id=rule_id
        )
