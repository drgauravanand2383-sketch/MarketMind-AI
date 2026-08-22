"""Domain models for the Alert & Notification Engine.

The engine consumes `app.signals.models.SignalResult` (Sprint 47) only —
no signal-detection logic is redefined or modified here. Nothing in this
package sends an email, SMS, push notification, or Telegram/Discord/Slack/
webhook message, and nothing executes a trade — the engine only decides
whether an alert should exist, why, how important it is, and which
notification channels would be appropriate. Actual delivery is out of
scope, implemented by a future sprint.

Design note — no AND/OR/nested group logic: unlike `app.screening.models`
(Sprint 45) and `app.signals.models` (Sprint 47), this sprint's own
"Alert Evaluation Engine Capabilities" list does not mention AND logic, OR
logic, or nested evaluation anywhere. `AlertRule.conditions` therefore
combine with a single, simple, always-AND semantics (every enabled
condition must pass) — no `AlertConditionGroup` model exists, and none is
needed. This is a deliberate simplification versus the two prior sprints,
not an oversight: adding unrequested nested-group machinery here would be
speculative complexity this sprint's spec never asked for.

Design note — additive fields, flagged per this codebase's established
precedent (`Watchlist.items`, `MarketDataSnapshot`, `EarningsReport`, and
others): `Alert.rule_id` and `Alert.eligible_channels` are not in this
sprint's literal Alert field list, but both are structurally required by
capabilities the sprint explicitly does require:
  - "Duplicate criteria: Ticker, Signal, Priority, Rule" (Deduplication)
    is unimplementable without knowing which rule produced an alert — the
    literal field list has no way to identify "Rule" at all otherwise.
  - "Determine eligible channels" (Alert Evaluation Engine capability) has
    nowhere to record its answer without an `eligible_channels` field.

Design note — `Alert.alert_type`: a fixed, non-configurable literal,
`"SIGNAL_TRIGGERED"`, for every alert this sprint produces — the engine's
only alert-generation pathway is a Signal Detection result. Modeling it as
its own field (rather than omitting it) anticipates future alert sources
(e.g. a price-threshold or news-event pathway) without a schema change,
while never inventing behavior beyond what this sprint implements.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.signals.models import ConditionEvaluation, SignalCategory, SignalResult

__all__ = [
    "AlertOperator",
    "NotificationChannel",
    "AlertStatus",
    "AlertPriority",
    "AlertCondition",
    "AlertRule",
    "AlertExplanation",
    "Alert",
    "AlertBatch",
]

ALERT_TYPE_SIGNAL_TRIGGERED = "SIGNAL_TRIGGERED"


class AlertOperator(str, Enum):
    EQUALS = "EQUALS"
    NOT_EQUALS = "NOT_EQUALS"
    GREATER_THAN = "GREATER_THAN"
    GREATER_EQUAL = "GREATER_EQUAL"
    LESS_THAN = "LESS_THAN"
    LESS_EQUAL = "LESS_EQUAL"
    BETWEEN = "BETWEEN"
    IN = "IN"
    NOT_IN = "NOT_IN"


class NotificationChannel(str, Enum):
    EMAIL = "EMAIL"
    PUSH = "PUSH"
    SMS = "SMS"
    TELEGRAM = "TELEGRAM"
    DISCORD = "DISCORD"
    SLACK = "SLACK"
    WEBHOOK = "WEBHOOK"
    IN_APP = "IN_APP"


class AlertStatus(str, Enum):
    PENDING = "PENDING"
    GENERATED = "GENERATED"
    SUPPRESSED = "SUPPRESSED"
    DISMISSED = "DISMISSED"
    EXPIRED = "EXPIRED"


class AlertPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


_ALERT_CONDITION_FIELDS: frozenset[str] = frozenset(
    name for name in SignalResult.model_fields if name not in {"matched_conditions", "failed_conditions"}
)

_LIST_LIKE_OPERATORS = frozenset({AlertOperator.IN, AlertOperator.NOT_IN})


class AlertCondition(BaseModel):
    """One alert condition: `field` `operator` `value`, evaluated against a
    `SignalResult`. `field` must be one of `SignalResult`'s own scalar
    field names (`ticker`, `company_name`, `signal_name`, `category`,
    `triggered`, `confidence`, `score`, `priority`, `reason`, `timestamp`)
    — its two tuple-typed fields (`matched_conditions`/`failed_conditions`)
    are not comparable by a single operator/value pair and are excluded.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    field: str = Field(min_length=1)
    operator: AlertOperator
    value: Any = None
    enabled: bool = True

    @model_validator(mode="after")
    def _validate_field_and_value(self) -> AlertCondition:
        if self.field not in _ALERT_CONDITION_FIELDS:
            raise ValueError(
                f"Condition {self.id!r} references unknown field {self.field!r}. "
                f"Expected one of {sorted(_ALERT_CONDITION_FIELDS)!r}."
            )

        if self.operator == AlertOperator.BETWEEN:
            if not isinstance(self.value, (list, tuple)) or len(self.value) != 2:
                raise ValueError(
                    f"Condition {self.id!r}: BETWEEN requires a value of exactly [low, high]."
                )
            low, high = self.value
            if low is None or high is None:
                raise ValueError(f"Condition {self.id!r}: BETWEEN bounds must not be None.")
            if low > high:
                raise ValueError(
                    f"Condition {self.id!r}: BETWEEN low bound {low!r} exceeds high bound {high!r}."
                )
        elif self.operator in _LIST_LIKE_OPERATORS:
            if not isinstance(self.value, (list, tuple)) or len(self.value) == 0:
                raise ValueError(
                    f"Condition {self.id!r}: {self.operator.value} requires a non-empty list of values."
                )
        elif self.value is None:
            raise ValueError(f"Condition {self.id!r}: {self.operator.value} requires a value.")

        return self


class AlertRule(BaseModel):
    """A named, reusable alert rule: a set of conditions evaluated against
    a `SignalResult`, plus cooldown/repeat/channel policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    enabled: bool = True
    priority: AlertPriority = AlertPriority.MEDIUM
    conditions: tuple[AlertCondition, ...] = Field(default_factory=tuple)
    cooldown_minutes: int = Field(default=0, ge=0)
    repeat_allowed: bool = True
    channels: tuple[NotificationChannel, ...] = Field(default_factory=tuple)
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def _require_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware.")
        return value

    @model_validator(mode="after")
    def _validate_conditions(self) -> AlertRule:
        seen_ids: set[str] = set()
        for condition in self.conditions:
            if condition.id in seen_ids:
                raise ValueError(f"Duplicate condition id {condition.id!r}.")
            seen_ids.add(condition.id)
        return self


class AlertExplanation(BaseModel):
    """v1.2 Priority 1 — a structured "what/why/how confident" breakdown
    of the `SignalResult` that produced an `Alert`, so a human doesn't
    have to reconstruct it from a formatted sentence. Every field is read
    directly from the triggering `SignalResult`'s own already-computed
    output (`app.signals.engine.SignalDetectionService.evaluate_company`)
    — nothing here is recomputed or invented; this is a read-only,
    structured view onto evidence that already existed. See
    `AlertService.evaluate_signal` for construction, and
    `docs/architecture/CONTINUOUS_INTELLIGENCE.md`/
    `docs/architecture/SIGNAL_ALERT_EXPLAINABILITY.md` for the full
    rationale (v1.2 Priority 1).
    """

    model_config = ConfigDict(extra="forbid")

    signal_category: SignalCategory
    weighted_score: float
    """The same value as the parent `Alert.score` — restated here
    alongside its evidence so the two are never read out of context of
    one another."""
    matched_condition_count: int = Field(ge=0)
    failed_condition_count: int = Field(ge=0)
    matched_conditions: tuple[ConditionEvaluation, ...] = Field(default_factory=tuple)
    failed_conditions: tuple[ConditionEvaluation, ...] = Field(default_factory=tuple)
    signal_reason: str
    """`SignalResult.reason` verbatim — the engine's own weighted-match
    description (e.g. "Triggered: 2 of 2 conditions matched (weighted
    score 100.0%).", never the generic `Alert.reason` sentence."""


class Alert(BaseModel):
    """One decision the engine has made about a specific
    `SignalResult`/`AlertRule` pairing: whether it should become a real,
    delivery-eligible alert (`GENERATED`) or was suppressed
    (`SUPPRESSED`) — see `app.alerts.engine.AlertService` for when each
    status is assigned. Never produced for a rule/signal pairing whose
    conditions simply did not match (see the engine's own docstring).
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    company_name: str | None = None
    signal_name: str
    alert_type: str = ALERT_TYPE_SIGNAL_TRIGGERED
    priority: AlertPriority
    status: AlertStatus
    reason: str
    confidence: float
    score: float
    eligible_channels: tuple[NotificationChannel, ...] = Field(default_factory=tuple)
    explanation: AlertExplanation | None = None
    """v1.2 Priority 1: additive, nullable — `None` only for an alert
    persisted before this field existed (a pre-v1.2 row read back from
    storage); every alert generated by this version's `AlertService`
    populates it."""
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def _require_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must be timezone-aware.")
        return value


class AlertBatch(BaseModel):
    """The aggregate outcome of one multi-signal and/or multi-rule
    evaluation run. `alerts` contains every rule/signal pairing whose
    conditions matched (both `GENERATED` and `SUPPRESSED`) — a pairing
    whose conditions did not match at all is not an alert candidate and
    never appears here.
    """

    model_config = ConfigDict(extra="forbid")

    alerts: tuple[Alert, ...] = Field(default_factory=tuple)
    generated: int
    suppressed: int
    summary: str
