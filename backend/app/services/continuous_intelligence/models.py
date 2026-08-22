"""Domain models for Continuous Intelligence (Milestone 15).

This package detects meaningful changes across Market, News/Knowledge, and
Decision Context (Risk/Recommendation/Strategy/Signal) and turns them into
`DetectedChange` records — never a second business engine: every score,
severity, and evaluation used to detect a change is read from an existing
service's already-computed output (`RiskAssessment`, `RecommendationResult`,
`StrategyEvaluationResult`, `SignalResult`, `MarketSnapshotResult`), never
recomputed with new logic here.

Design note — `ChangePriority`, a new 5-tier scale (`INFO`/`LOW`/`MEDIUM`/
`HIGH`/`CRITICAL`): none of this codebase's three existing severity/priority
enums has exactly this shape (`AlertPriority`/`SignalPriority` are
`LOW`/`MEDIUM`/`HIGH`/`CRITICAL` — no `INFO`; `RiskSeverity` is
`LOW`/`MODERATE`/`HIGH`/`CRITICAL` — `MODERATE` not `MEDIUM`, no `INFO`
either), so introducing a new one is unavoidable to satisfy this milestone's
own explicit "INFO/LOW/MEDIUM/HIGH/CRITICAL" requirement (§6). It is not a
second, incompatible severity system: every existing enum maps into it
deterministically via `priority_from_alert_priority`/
`priority_from_risk_severity`/`priority_from_signal_priority` below, and
`INFO` is reserved for this scale's own bottom tier (magnitude-banding, not
borrowed from any existing enum, which has no equivalent of "notable but
barely above threshold").
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.alerts.models import AlertPriority
from app.risk.models import RiskSeverity
from app.signals.models import SignalPriority

__all__ = [
    "ChangeDomain",
    "ChangePriority",
    "DetectedChange",
    "ContinuousIntelligenceCycleResult",
    "priority_from_alert_priority",
    "priority_from_risk_severity",
    "priority_from_signal_priority",
    "priority_from_magnitude",
]


class ChangeDomain(str, Enum):
    """Which part of the system a `DetectedChange` originated from —
    directly maps to the WS event type this milestone publishes it as
    (see `app.services.continuous_intelligence.service`)."""

    MARKET = "MARKET"
    NEWS = "NEWS"
    RISK = "RISK"
    RECOMMENDATION = "RECOMMENDATION"
    STRATEGY = "STRATEGY"
    SIGNAL = "SIGNAL"


class ChangePriority(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


_ALERT_PRIORITY_MAP: dict[AlertPriority, ChangePriority] = {
    AlertPriority.LOW: ChangePriority.LOW,
    AlertPriority.MEDIUM: ChangePriority.MEDIUM,
    AlertPriority.HIGH: ChangePriority.HIGH,
    AlertPriority.CRITICAL: ChangePriority.CRITICAL,
}

_RISK_SEVERITY_MAP: dict[RiskSeverity, ChangePriority] = {
    RiskSeverity.LOW: ChangePriority.LOW,
    RiskSeverity.MODERATE: ChangePriority.MEDIUM,
    RiskSeverity.HIGH: ChangePriority.HIGH,
    RiskSeverity.CRITICAL: ChangePriority.CRITICAL,
}

_SIGNAL_PRIORITY_MAP: dict[SignalPriority, ChangePriority] = {
    SignalPriority.LOW: ChangePriority.LOW,
    SignalPriority.MEDIUM: ChangePriority.MEDIUM,
    SignalPriority.HIGH: ChangePriority.HIGH,
    SignalPriority.CRITICAL: ChangePriority.CRITICAL,
}


def priority_from_alert_priority(value: AlertPriority) -> ChangePriority:
    return _ALERT_PRIORITY_MAP[value]


def priority_from_risk_severity(value: RiskSeverity) -> ChangePriority:
    return _RISK_SEVERITY_MAP[value]


def priority_from_signal_priority(value: SignalPriority) -> ChangePriority:
    return _SIGNAL_PRIORITY_MAP[value]


def priority_from_magnitude(magnitude: float, threshold: float) -> ChangePriority:
    """Deterministic magnitude banding for domains with no existing
    categorical severity to borrow (Market/News/Recommendation/Strategy):
    a change must already be `>= threshold` to exist as a `DetectedChange`
    at all (the detector's own significance gate), so this only decides
    *how* significant, via how many multiples of the configured threshold
    it crossed. `threshold` must be positive (validated by the caller's
    own config model)."""
    ratio = magnitude / threshold
    if ratio >= 8:
        return ChangePriority.CRITICAL
    if ratio >= 4:
        return ChangePriority.HIGH
    if ratio >= 2:
        return ChangePriority.MEDIUM
    return ChangePriority.LOW


class DetectedChange(BaseModel):
    """One meaningful, already-classified change — the unit this package
    detects, deduplicates, suppresses, and (if not suppressed) publishes
    as a WS event / routes to a notification. `fingerprint` is this
    change's deduplication identity (see
    `app.services.continuous_intelligence.suppression`) — deliberately a
    stable, inspectable string key (`"{domain}:{entity_id}:{detail}"`),
    the same named-field-key approach `AlertService._is_duplicate`
    already uses, not a hash.
    """

    model_config = ConfigDict(extra="forbid")

    fingerprint: str = Field(min_length=1)
    domain: ChangeDomain
    entity_id: str = Field(min_length=1)
    """Canonical entity id (market/news/signal) or portfolio_id (risk/
    recommendation/strategy) — whichever this domain's state is keyed by."""
    label: str = Field(min_length=1)
    """Human-readable identifier for display — a ticker, company name, or
    portfolio name."""
    priority: ChangePriority
    summary: str = Field(min_length=1)
    previous_value: str | None = None
    current_value: str | None = None
    portfolio_id: str | None = None
    """Decision-context linkage (§7) — set when this change was
    determined to matter to a specific portfolio; `None` for a market/news
    change with no portfolio impact determined yet."""
    event_fingerprint: str | None = None
    """v1.2 Priority 1 (§7): the portfolio-agnostic identity of the
    underlying real-world event — set once at detection time to the same
    value `fingerprint` originally had, and never rewritten afterward.
    `DecisionImpactService.attach_portfolio_context` appends `:{portfolio_id}`
    to `fingerprint` itself (deliberately — see that module's own
    docstring: two portfolios tracking the same ticker must each
    independently pass suppression) — which means `fingerprint` alone can
    no longer answer "is this the same underlying event as that other
    one, just routed to a different portfolio?" `event_fingerprint`
    answers exactly that, without changing any existing suppression/
    routing behavior. A future task can group `DetectedChange`s sharing
    one `event_fingerprint` across portfolios; this task only ensures the
    identity survives portfolio expansion. `None` only for a
    `DetectedChange` constructed before this field existed (never emitted
    by this codebase after v1.2)."""
    impacted_portfolio_ids: tuple[str, ...] = Field(default_factory=tuple)
    """v1.2 Priority 2 (cross-portfolio notification grouping): the
    complete list of every portfolio this underlying event was found
    impacted for *and* which independently survived its own per-portfolio
    suppression check — attached identically to every published copy of
    one `event_fingerprint` group by `ContinuousIntelligenceService._route`
    (see that method's own docstring). Never used for routing/delivery or
    suppression (`fingerprint`/`portfolio_id` remain the source of truth
    for both, unchanged) — purely presentation metadata so a single
    received WS frame is self-sufficient to render "Affected: N
    portfolios" without needing every other frame in the group to have
    arrived first. Empty for a change with no portfolio impact, or for
    Risk/Recommendation/Strategy changes (already inherently
    single-portfolio, never fanned out)."""
    detected_at: datetime


class ContinuousIntelligenceCycleResult(BaseModel):
    """The outcome of one `ContinuousIntelligenceService.run_cycle()` run
    — every count §19 (observability) requires, plus the actual detected/
    suppressed changes for inspectability (mirrors
    `MarketDataRefreshResult`'s own "never just a count" precedent)."""

    model_config = ConfigDict(extra="forbid")

    execution_id: str
    started_at: datetime
    completed_at: datetime
    entities_examined: int = 0
    market_changes_detected: int = 0
    news_changes_detected: int = 0
    decision_changes_detected: int = 0
    events_emitted: int = 0
    events_suppressed: int = 0
    notifications_published: int = 0
    failures: tuple[str, ...] = Field(default_factory=tuple)
    changes: tuple[DetectedChange, ...] = Field(default_factory=tuple)
    suppressed: tuple[DetectedChange, ...] = Field(default_factory=tuple)

    @property
    def duration_seconds(self) -> float:
        return (self.completed_at - self.started_at).total_seconds()
