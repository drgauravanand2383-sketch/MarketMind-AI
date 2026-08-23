"""AlertService: the Alert & Notification Engine's Application layer.

Decides whether a `SignalResult`/`AlertRule` pairing should become a real
alert — never sends anything, never executes a trade. Combines rule
management (delegated to an injected `BaseAlertRuleRepository`) with
evaluation (rule matching, priority combination, channel eligibility,
cooldown/deduplication — all requiring a lookup into an injected
`BaseAlertRepository` for prior alert history, which is why evaluation
here is asynchronous, unlike the purely synchronous evaluation engines in
`app.screening`/`app.signals`). No globals, no singleton: every dependency
is injected at construction time.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.alerts.exceptions import (
    AlertNotFoundError,
    AlertRuleNotFoundError,
    DuplicateAlertRuleNameError,
    MaxAlertRulesExceededError,
    MaxChannelsExceededError,
)
from app.alerts.models import (
    ALERT_TYPE_SIGNAL_TRIGGERED,
    Alert,
    AlertBatch,
    AlertCondition,
    AlertExplanation,
    AlertOperator,
    AlertPriority,
    AlertRule,
    AlertStatus,
    NotificationChannel,
)
from app.signals.models import SignalPriority, SignalResult

if TYPE_CHECKING:
    from app.repositories.alerts.repository import BaseAlertRepository, BaseAlertRuleRepository

__all__ = ["AlertService"]

DEFAULT_MAX_RULES = 100
DEFAULT_MAX_CHANNELS = len(NotificationChannel)
DEFAULT_DEDUP_FIELDS = frozenset({"ticker", "signal_name", "priority", "rule_id"})

_ALERT_PRIORITY_RANK: dict[AlertPriority, int] = {
    AlertPriority.LOW: 0,
    AlertPriority.MEDIUM: 1,
    AlertPriority.HIGH: 2,
    AlertPriority.CRITICAL: 3,
}

_SIGNAL_PRIORITY_TO_ALERT_PRIORITY: dict[SignalPriority, AlertPriority] = {
    SignalPriority.LOW: AlertPriority.LOW,
    SignalPriority.MEDIUM: AlertPriority.MEDIUM,
    SignalPriority.HIGH: AlertPriority.HIGH,
    SignalPriority.CRITICAL: AlertPriority.CRITICAL,
}

_CHANNELS_BY_PRIORITY: dict[AlertPriority, frozenset[NotificationChannel]] = {
    AlertPriority.LOW: frozenset({NotificationChannel.IN_APP, NotificationChannel.EMAIL}),
    AlertPriority.MEDIUM: frozenset(
        {NotificationChannel.IN_APP, NotificationChannel.EMAIL, NotificationChannel.PUSH}
    ),
    AlertPriority.HIGH: frozenset(
        {
            NotificationChannel.IN_APP,
            NotificationChannel.EMAIL,
            NotificationChannel.PUSH,
            NotificationChannel.SLACK,
            NotificationChannel.DISCORD,
            NotificationChannel.TELEGRAM,
            NotificationChannel.WEBHOOK,
        }
    ),
    AlertPriority.CRITICAL: frozenset(NotificationChannel),
}


def _default_now() -> datetime:
    return datetime.now(UTC)


class AlertService:
    def __init__(
        self,
        rule_repository: BaseAlertRuleRepository,
        alert_repository: BaseAlertRepository,
        *,
        max_rules: int = DEFAULT_MAX_RULES,
        max_channels: int = DEFAULT_MAX_CHANNELS,
        enforce_unique_names: bool = True,
        dedup_fields: frozenset[str] = DEFAULT_DEDUP_FIELDS,
        now_fn: Callable[[], datetime] = _default_now,
    ) -> None:
        """Initialize the service.

        Args:
            rule_repository: Persists `AlertRule`s.
            alert_repository: Persists `Alert`s and supplies prior-alert
                history for cooldown/deduplication checks.
            max_rules: Maximum number of registered alert rules allowed at
                once — a total-count cap, not a per-rule condition cap
                (this sprint does not request the latter).
            max_channels: Maximum `AlertRule.channels` length.
            enforce_unique_names: Whether rule names must be unique.
            dedup_fields: Which of `{"ticker", "signal_name", "priority",
                "rule_id"}` participate in duplicate detection — the
                sprint's own "Support configurable duplicate detection"
                requirement. Defaults to all four (the sprint's own listed
                "Duplicate criteria").
            now_fn: Returns the current time, used for cooldown
                comparisons. Injected (never `datetime.now()` called
                directly elsewhere in this class) so tests can supply a
                fixed clock — mirrors `MockMarketDataProvider`'s injectable
                `reference_time` (Sprint 46).
        """
        self._rule_repository = rule_repository
        self._alert_repository = alert_repository
        self._max_rules = max_rules
        self._max_channels = max_channels
        self._enforce_unique_names = enforce_unique_names
        self._dedup_fields = dedup_fields
        self._now_fn = now_fn

    # --- Rule management -----------------------------------------------------------

    async def create_rule(
        self,
        name: str,
        *,
        description: str = "",
        enabled: bool = True,
        priority: str = "MEDIUM",
        conditions: tuple[AlertCondition, ...] = (),
        cooldown_minutes: int = 0,
        repeat_allowed: bool = True,
        channels: tuple[NotificationChannel, ...] = (),
    ) -> AlertRule:
        """Create a new alert rule.

        Raises:
            MaxAlertRulesExceededError: creating this rule would exceed the configured maximum.
            MaxChannelsExceededError: `len(channels)` exceeds the configured maximum.
            DuplicateAlertRuleNameError: `name` is already in use (only
                when `enforce_unique_names=True`, the default).
        """
        await self._check_rule_count()
        self._check_channel_count(None, channels)
        await self._check_unique_name(name)

        now = self._now_fn()
        rule = AlertRule(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
            enabled=enabled,
            priority=AlertPriority(priority),
            conditions=conditions,
            cooldown_minutes=cooldown_minutes,
            repeat_allowed=repeat_allowed,
            channels=channels,
            created_at=now,
            updated_at=now,
        )
        return await self._rule_repository.create_rule(rule)

    async def update_rule(self, rule: AlertRule) -> AlertRule:
        """Replace an existing rule's stored state with `rule` (same id).

        Raises:
            AlertRuleNotFoundError: no rule exists for `rule.id`.
            MaxChannelsExceededError: `len(rule.channels)` exceeds the configured maximum.
            DuplicateAlertRuleNameError: `rule.name` is already in use by
                a *different* rule (only when `enforce_unique_names=True`).
        """
        self._check_channel_count(rule.id, rule.channels)
        await self._check_unique_name(rule.name, ignore_rule_id=rule.id)

        updated = rule.model_copy(update={"updated_at": self._now_fn()})
        result = await self._rule_repository.update_rule(updated)
        if result is None:
            raise AlertRuleNotFoundError(rule.id)
        return result

    async def delete_rule(self, rule_id: str) -> None:
        """Raises `AlertRuleNotFoundError` if no rule exists for `rule_id`."""
        deleted = await self._rule_repository.delete_rule(rule_id)
        if not deleted:
            raise AlertRuleNotFoundError(rule_id)

    async def list_rules(self) -> list[AlertRule]:
        return await self._rule_repository.list_rules()

    async def get_rule(self, rule_id: str) -> AlertRule:
        """Raises `AlertRuleNotFoundError` if no rule exists for `rule_id`."""
        rule = await self._rule_repository.get_rule(rule_id)
        if rule is None:
            raise AlertRuleNotFoundError(rule_id)
        return rule

    async def duplicate_rule(self, rule_id: str, new_name: str) -> AlertRule:
        """Copy an existing rule's conditions/policy into a new rule.

        Raises:
            AlertRuleNotFoundError: no rule exists for `rule_id`.
            MaxAlertRulesExceededError: creating the copy would exceed the configured maximum.
            DuplicateAlertRuleNameError: `new_name` is already in use
                (only when `enforce_unique_names=True`).
        """
        await self._check_rule_count()
        await self._check_unique_name(new_name)
        result = await self._rule_repository.duplicate_rule(rule_id, str(uuid.uuid4()), new_name)
        if result is None:
            raise AlertRuleNotFoundError(rule_id)
        return result

    async def _check_rule_count(self) -> None:
        existing = len(await self._rule_repository.list_rules())
        if existing >= self._max_rules:
            raise MaxAlertRulesExceededError(limit=self._max_rules, actual=existing + 1)

    def _check_channel_count(self, rule_id: str | None, channels: tuple[NotificationChannel, ...]) -> None:
        if len(channels) > self._max_channels:
            raise MaxChannelsExceededError(rule_id, limit=self._max_channels, actual=len(channels))

    async def _check_unique_name(self, name: str, *, ignore_rule_id: str | None = None) -> None:
        if not self._enforce_unique_names:
            return
        for existing in await self._rule_repository.list_rules():
            if existing.name == name and existing.id != ignore_rule_id:
                raise DuplicateAlertRuleNameError(name)

    async def get_alert(self, alert_id: str) -> Alert:
        """Raises `AlertNotFoundError` if no alert exists for `alert_id`."""
        alert = await self._alert_repository.get_alert(alert_id)
        if alert is None:
            raise AlertNotFoundError(alert_id)
        return alert

    async def list_alerts(self) -> list[Alert]:
        return await self._alert_repository.list_alerts()

    # --- Evaluation -----------------------------------------------------------

    async def evaluate_signal(self, signal: SignalResult, rule: AlertRule) -> Alert | None:
        """Evaluate one `SignalResult` against one `AlertRule`.

        Returns `None` if `rule`'s enabled conditions do not all match
        `signal` — no alert candidate exists at all. Otherwise always
        returns a persisted `Alert`, with `status` either `GENERATED` or
        `SUPPRESSED` (see the module docstring on what makes a duplicate).
        Does not itself check `rule.enabled` — see `evaluate_rules`/
        `evaluate_batch`, which filter to enabled rules before calling
        this for each one; a rule passed here explicitly is evaluated
        regardless of its own `enabled` flag, mirroring
        `SignalDetectionService.evaluate_company`'s identical treatment of
        `SignalDefinition.enabled` (Sprint 47).
        """
        enabled_conditions = [c for c in rule.conditions if c.enabled]
        if not all(_evaluate_condition(c, signal) for c in enabled_conditions):
            return None

        priority = _combine_priority(rule.priority, signal.priority)
        eligible_channels = tuple(c for c in rule.channels if c in _CHANNELS_BY_PRIORITY[priority])

        is_duplicate = await self._is_duplicate(signal, rule, priority)
        status = AlertStatus.SUPPRESSED if is_duplicate else AlertStatus.GENERATED
        explanation = _build_explanation(signal)
        reason = _build_reason(rule, signal, explanation)
        if is_duplicate:
            reason += " Suppressed: duplicate alert within cooldown/repeat policy."

        alert = Alert(
            id=str(uuid.uuid4()),
            rule_id=rule.id,
            ticker=signal.ticker,
            company_name=signal.company_name,
            signal_name=signal.signal_name,
            alert_type=ALERT_TYPE_SIGNAL_TRIGGERED,
            priority=priority,
            status=status,
            reason=reason,
            confidence=signal.confidence,
            score=signal.score,
            eligible_channels=eligible_channels,
            explanation=explanation,
            created_at=self._now_fn(),
        )
        return await self._alert_repository.create_alert(alert)

    async def evaluate_signals(self, signals: list[SignalResult], rule: AlertRule) -> AlertBatch:
        """Evaluate multiple signals against one alert rule."""
        alerts = [alert for signal in signals if (alert := await self.evaluate_signal(signal, rule)) is not None]
        return _build_batch(alerts)

    async def evaluate_rules(self, signal: SignalResult, rules: list[AlertRule]) -> AlertBatch:
        """Evaluate one signal against multiple alert rules (only those
        with `enabled=True` are considered)."""
        alerts = [
            alert
            for rule in rules
            if rule.enabled
            if (alert := await self.evaluate_signal(signal, rule)) is not None
        ]
        return _build_batch(alerts)

    async def evaluate_batch(self, signals: list[SignalResult], rules: list[AlertRule]) -> AlertBatch:
        """Evaluate multiple signals against multiple alert rules (the
        full cross product; only `enabled=True` rules are considered)."""
        alerts = [
            alert
            for rule in rules
            if rule.enabled
            for signal in signals
            if (alert := await self.evaluate_signal(signal, rule)) is not None
        ]
        return _build_batch(alerts)

    async def _is_duplicate(self, signal: SignalResult, rule: AlertRule, priority: AlertPriority) -> bool:
        """A prior `GENERATED` alert counts as a duplicate baseline; a
        `SUPPRESSED` one never resets the cooldown clock (see module
        docstring). With `repeat_allowed=False`, any matching prior
        `GENERATED` alert suppresses this one, regardless of elapsed time
        (fire-once semantics). With `repeat_allowed=True` (the default),
        only a prior `GENERATED` alert within `cooldown_minutes` of now
        counts.
        """
        candidate_key = {
            "ticker": signal.ticker,
            "signal_name": signal.signal_name,
            "priority": priority,
            "rule_id": rule.id,
        }
        now = self._now_fn()

        for existing in await self._alert_repository.list_alerts():
            if existing.status != AlertStatus.GENERATED:
                continue
            if not _matches_dedup_key(existing, candidate_key, self._dedup_fields):
                continue
            if not rule.repeat_allowed:
                return True
            elapsed_minutes = (now - existing.created_at).total_seconds() / 60
            if elapsed_minutes < rule.cooldown_minutes:
                return True
        return False


def _evaluate_condition(condition: AlertCondition, signal: SignalResult) -> bool:
    actual = getattr(signal, condition.field, None)
    if actual is None:
        return False
    return _apply_operator(condition.operator, actual, condition.value)


def _apply_operator(operator: AlertOperator, actual: Any, expected: Any) -> bool:
    # `actual`/`expected` are genuinely `Any` — arbitrary attribute values
    # compared against arbitrary configured values, this function's whole
    # purpose. Every branch's own comparison operator already returns a
    # real `bool` at runtime for any well-behaved comparable pair (the
    # only kind `AlertCondition` ever configures); `bool(...)` here is a
    # correct, harmless narrowing for mypy, not a behavior change.
    if operator == AlertOperator.EQUALS:
        return bool(actual == expected)
    if operator == AlertOperator.NOT_EQUALS:
        return bool(actual != expected)
    if operator == AlertOperator.GREATER_THAN:
        return bool(actual > expected)
    if operator == AlertOperator.GREATER_EQUAL:
        return bool(actual >= expected)
    if operator == AlertOperator.LESS_THAN:
        return bool(actual < expected)
    if operator == AlertOperator.LESS_EQUAL:
        return bool(actual <= expected)
    if operator == AlertOperator.BETWEEN:
        low, high = expected
        return bool(low <= actual <= high)
    if operator == AlertOperator.IN:
        return actual in expected
    return actual not in expected  # AlertOperator.NOT_IN


def _build_explanation(signal: SignalResult) -> AlertExplanation:
    """v1.2 Priority 1 (§4): a structured, evidence-based explanation of
    why this alert exists — every field read directly from the already-
    computed `SignalResult`, nothing recomputed or invented here."""
    return AlertExplanation(
        signal_category=signal.category,
        weighted_score=signal.score,
        matched_condition_count=len(signal.matched_conditions),
        failed_condition_count=len(signal.failed_conditions),
        matched_conditions=signal.matched_conditions,
        failed_conditions=signal.failed_conditions,
        signal_reason=signal.reason,
    )


def _build_reason(rule: AlertRule, signal: SignalResult, explanation: AlertExplanation) -> str:
    """v1.2 Priority 1 (§4): replaces the pre-v1.2 boilerplate
    (`"Rule {rule.name!r} matched signal {signal.signal_name!r} for
    {signal.ticker}."`, identical for every alert regardless of what
    actually happened) with a sentence grounded in the signal's own real,
    already-computed evidence (`signal.reason` — the engine's own
    weighted-match description, e.g. "Triggered: 2 of 2 conditions
    matched (weighted score 100.0%)."), so `reason` alone (as shown in
    the frontend Notification Center's summary, and in
    `GET /alerts/{id}`) is no longer indistinguishable across every alert
    this rule has ever produced."""
    subject = f"{signal.company_name} ({signal.ticker})" if signal.company_name else signal.ticker
    return (
        f"{subject}: signal {signal.signal_name!r} {'triggered' if signal.triggered else 'did not trigger'} "
        f"under rule {rule.name!r} — {signal.reason} "
        f"({explanation.matched_condition_count} matched / {explanation.failed_condition_count} failed condition(s))."
    )


def _combine_priority(rule_priority: AlertPriority, signal_priority: SignalPriority) -> AlertPriority:
    """An alert's priority is the more severe of the rule's own declared
    priority and the triggering signal's priority — an alert should never
    be understated relative to either input. No exact algorithm is given
    by the sprint spec; this max-of-both-severities rule is a documented,
    flagged judgment call (mirrors `app.signals.engine._confidence`'s own
    similarly-flagged formula from Sprint 47).
    """
    mapped_signal_priority = _SIGNAL_PRIORITY_TO_ALERT_PRIORITY[signal_priority]
    if _ALERT_PRIORITY_RANK[mapped_signal_priority] > _ALERT_PRIORITY_RANK[rule_priority]:
        return mapped_signal_priority
    return rule_priority


def _matches_dedup_key(existing: Alert, candidate_key: dict[str, Any], dedup_fields: frozenset[str]) -> bool:
    return all(getattr(existing, field) == candidate_key[field] for field in dedup_fields)


def _build_batch(alerts: list[Alert]) -> AlertBatch:
    generated = sum(1 for a in alerts if a.status == AlertStatus.GENERATED)
    suppressed = sum(1 for a in alerts if a.status == AlertStatus.SUPPRESSED)
    summary = (
        f"{len(alerts)} alert candidate(s) evaluated; {generated} generated, {suppressed} suppressed."
        if alerts
        else "No alert candidates (no rule conditions matched)."
    )
    return AlertBatch(alerts=tuple(alerts), generated=generated, suppressed=suppressed, summary=summary)
