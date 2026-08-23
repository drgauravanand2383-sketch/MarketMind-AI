"""Previous-state tracking for Continuous Intelligence — in-memory and
persistent implementations of the same async interface.

Restart semantics (§4/§7, Milestone 16): every `observe_*` method returns
the previous value for a key it has already seen (`None` on first
observation — first observation establishes the baseline silently). Every
detector in `app.services.continuous_intelligence.detector` treats a
`None` previous value as "nothing to compare against yet" — never as
"changed from nothing." A restart therefore never causes a flood of
duplicate "changes" *by construction*, regardless of which backing store
is in use:

- `InMemoryContinuousIntelligenceStateStore` (Milestone 15): a plain
  process-local dict, lost on every restart — every key is "first
  observation" again after a restart, so one comparison is silently
  skipped (self-heals on the next cycle), never duplicated.
- `PostgresContinuousIntelligenceStateStore` (Milestone 16 §2): backed by
  the durable `continuous_intelligence_state` table (see
  `app.repositories.continuous_intelligence`), so the previous value
  genuinely survives a restart — the same "genuinely new change after
  restart is detected, unchanged state after restart emits nothing"
  behavior, but now without the one-comparison gap the in-memory version
  has immediately after a restart.

Both classes implement the exact same async method set, so
`ContinuousIntelligenceService`/`ChangeDetectionService` are written
against the interface, never against a concrete backing store.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from app.recommendations.models import RecommendationType
from app.repositories.continuous_intelligence.repository import (
    BaseContinuousIntelligenceStateRepository,
)
from app.risk.models import RiskSeverity
from app.services.market_snapshot.models import MarketSnapshot

__all__ = [
    "ContinuousIntelligenceStateStore",
    "InMemoryContinuousIntelligenceStateStore",
    "PostgresContinuousIntelligenceStateStore",
]

_MARKET = "MARKET"
_MARKET_STATUS = "MARKET_STATUS"
_NEWS = "NEWS"
_NEWS_CONFIDENCE = "NEWS_CONFIDENCE"
_RISK_SEVERITY = "RISK_SEVERITY"
_RECOMMENDATION = "RECOMMENDATION"
_STRATEGY_ALIGNMENT = "STRATEGY_ALIGNMENT"
_SIGNAL_TRIGGERED = "SIGNAL_TRIGGERED"


def _default_now() -> datetime:
    return datetime.now(UTC)


class ContinuousIntelligenceStateStore(Protocol):
    """The async previous-state-tracking interface both implementations satisfy."""

    async def observe_market(self, entity_id: str, snapshot: MarketSnapshot | None) -> MarketSnapshot | None: ...

    async def observe_market_status(self, entity_id: str, status: str) -> str | None: ...

    async def observe_news(self, entity_id: str, record_ids: frozenset[str]) -> frozenset[str] | None: ...

    async def observe_news_confidence(self, entity_id: str, confidence: float) -> float | None: ...

    async def observe_risk_severity(self, portfolio_id: str, severity: RiskSeverity) -> RiskSeverity | None: ...

    async def observe_recommendation(
        self, key: str, recommendation: RecommendationType, score: float
    ) -> tuple[RecommendationType, float] | None: ...

    async def observe_strategy_alignment(self, portfolio_id: str, alignment: float) -> float | None: ...

    async def observe_signal_triggered(self, key: str, triggered: bool) -> bool | None: ...


class InMemoryContinuousIntelligenceStateStore:
    """Tracks the last-observed value per domain/key in a plain
    process-local dict, so a detector can diff "current vs previous"
    without any downstream engine needing to expose a history API of its
    own (none of them do — see `docs/architecture/CONTINUOUS_INTELLIGENCE.md`
    §4). Lost on every restart — see this module's own docstring."""

    def __init__(self) -> None:
        self._market: dict[str, MarketSnapshot] = {}
        self._market_status: dict[str, str] = {}
        self._news_record_ids: dict[str, frozenset[str]] = {}
        self._news_confidence: dict[str, float] = {}
        self._risk_severity: dict[str, RiskSeverity] = {}
        self._recommendation: dict[str, tuple[RecommendationType, float]] = {}
        self._strategy_alignment: dict[str, float] = {}
        self._signal_triggered: dict[str, bool] = {}

    async def observe_market(self, entity_id: str, snapshot: MarketSnapshot | None) -> MarketSnapshot | None:
        """Returns the previously-observed `MarketSnapshot` for
        `entity_id` (`None` on first observation), then records `snapshot`
        as current — unless `snapshot` is `None` (no FRESH/STALE data this
        cycle), in which case nothing is overwritten, so a later real
        snapshot is still compared against the last genuine one, not a gap."""
        previous = self._market.get(entity_id)
        if snapshot is not None:
            self._market[entity_id] = snapshot
        return previous

    async def observe_market_status(self, entity_id: str, status: str) -> str | None:
        previous = self._market_status.get(entity_id)
        self._market_status[entity_id] = status
        return previous

    async def observe_news(self, entity_id: str, record_ids: frozenset[str]) -> frozenset[str] | None:
        """Returns the previously-observed set of knowledge-record ids
        for `entity_id` (`None` on first observation)."""
        previous = self._news_record_ids.get(entity_id)
        self._news_record_ids[entity_id] = record_ids
        return previous

    async def observe_news_confidence(self, entity_id: str, confidence: float) -> float | None:
        previous = self._news_confidence.get(entity_id)
        self._news_confidence[entity_id] = confidence
        return previous

    async def observe_risk_severity(self, portfolio_id: str, severity: RiskSeverity) -> RiskSeverity | None:
        previous = self._risk_severity.get(portfolio_id)
        self._risk_severity[portfolio_id] = severity
        return previous

    async def observe_recommendation(
        self, key: str, recommendation: RecommendationType, score: float
    ) -> tuple[RecommendationType, float] | None:
        """`key` is caller-composed (typically `f"{portfolio_id}:{ticker}"`)."""
        previous = self._recommendation.get(key)
        self._recommendation[key] = (recommendation, score)
        return previous

    async def observe_strategy_alignment(self, portfolio_id: str, alignment: float) -> float | None:
        previous = self._strategy_alignment.get(portfolio_id)
        self._strategy_alignment[portfolio_id] = alignment
        return previous

    async def observe_signal_triggered(self, key: str, triggered: bool) -> bool | None:
        """`key` is caller-composed (typically
        `f"{entity_id}:{signal_definition_id}"`)."""
        previous = self._signal_triggered.get(key)
        self._signal_triggered[key] = triggered
        return previous


class PostgresContinuousIntelligenceStateStore:
    """Same previous-state-tracking interface as
    `InMemoryContinuousIntelligenceStateStore`, backed by the durable
    `continuous_intelligence_state` table so the previous value survives a
    process restart (§2/§7). Stores only a compact fingerprint/value per
    key — never a full domain result — per §2's explicit "do not persist
    entire domain results if a compact state value is sufficient."

    `MarketSnapshot` is the one value shape here that isn't already a
    JSON-safe primitive; it round-trips through
    `model_dump(mode="json")`/`model_validate` like every other
    Postgres-backed domain model in this codebase.
    """

    def __init__(
        self,
        repository: BaseContinuousIntelligenceStateRepository,
        *,
        now_fn: Any = _default_now,
    ) -> None:
        self._repository = repository
        self._now_fn = now_fn

    async def observe_market(self, entity_id: str, snapshot: MarketSnapshot | None) -> MarketSnapshot | None:
        row = await self._repository.get(_MARKET, entity_id)
        previous = MarketSnapshot.model_validate(row[0]) if row is not None else None
        if snapshot is not None:
            await self._repository.put(_MARKET, entity_id, snapshot.model_dump(mode="json"), self._now_fn())
        return previous

    async def observe_market_status(self, entity_id: str, status: str) -> str | None:
        row = await self._repository.get(_MARKET_STATUS, entity_id)
        previous = row[0] if row is not None else None
        await self._repository.put(_MARKET_STATUS, entity_id, status, self._now_fn())
        return previous

    async def observe_news(self, entity_id: str, record_ids: frozenset[str]) -> frozenset[str] | None:
        row = await self._repository.get(_NEWS, entity_id)
        previous = frozenset(row[0]) if row is not None else None
        await self._repository.put(_NEWS, entity_id, sorted(record_ids), self._now_fn())
        return previous

    async def observe_news_confidence(self, entity_id: str, confidence: float) -> float | None:
        row = await self._repository.get(_NEWS_CONFIDENCE, entity_id)
        previous = row[0] if row is not None else None
        await self._repository.put(_NEWS_CONFIDENCE, entity_id, confidence, self._now_fn())
        return previous

    async def observe_risk_severity(self, portfolio_id: str, severity: RiskSeverity) -> RiskSeverity | None:
        row = await self._repository.get(_RISK_SEVERITY, portfolio_id)
        previous = RiskSeverity(row[0]) if row is not None else None
        await self._repository.put(_RISK_SEVERITY, portfolio_id, severity.value, self._now_fn())
        return previous

    async def observe_recommendation(
        self, key: str, recommendation: RecommendationType, score: float
    ) -> tuple[RecommendationType, float] | None:
        row = await self._repository.get(_RECOMMENDATION, key)
        previous = (RecommendationType(row[0]["type"]), row[0]["score"]) if row is not None else None
        value = {"type": recommendation.value, "score": score}
        await self._repository.put(_RECOMMENDATION, key, value, self._now_fn())
        return previous

    async def observe_strategy_alignment(self, portfolio_id: str, alignment: float) -> float | None:
        row = await self._repository.get(_STRATEGY_ALIGNMENT, portfolio_id)
        previous = row[0] if row is not None else None
        await self._repository.put(_STRATEGY_ALIGNMENT, portfolio_id, alignment, self._now_fn())
        return previous

    async def observe_signal_triggered(self, key: str, triggered: bool) -> bool | None:
        row = await self._repository.get(_SIGNAL_TRIGGERED, key)
        previous = row[0] if row is not None else None
        await self._repository.put(_SIGNAL_TRIGGERED, key, triggered, self._now_fn())
        return previous
