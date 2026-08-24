"""ContinuousIntelligenceService — the orchestrator (§1/§17).

Composes existing services exactly as they already exist: no new scoring,
no new evaluation algorithm, no second alert/recommendation engine.

- Market: `MarketSnapshotService.get_snapshots()` (Milestone 13).
- News: `KnowledgeHub.query()` + `MarketIntelligenceEngine.analyze()`
  (both pre-existing, already used by `PortfolioIntelligenceAgent`/
  `CompanyResearchAgent`).
- Signals: `SignalDetectionService.evaluate_company()` fed by
  `app.services.portfolio_market_snapshot.signal_adapter` (Milestone 14) —
  every newly-`triggered` signal is additionally fed into the existing
  `AlertService.evaluate_rules()`, the real production alert pathway, with
  its own untouched cooldown/dedup.
- Risk / Recommendations: the most-recently-stored `RiskAssessment`/
  `RecommendationResult` per portfolio (via each service's own
  `list_requests`/`get_*`), compared to the previous cycle's — this
  service never calls `assess_portfolio()`/`generate_recommendations()`
  itself (no evidence-sourcing pipeline exists to feed them; see
  `docs/architecture/CONTINUOUS_INTELLIGENCE.md` §16 for the full
  reasoning).
- Strategy (Milestone 16 §12, `_detect_strategy`, only when
  `strategy_service` is injected): the most-recently-stored
  `StrategyEvaluationResult` whose `recommendation_result_id` — now
  persisted on that result — resolves (via
  `PortfolioRecommendationService.get_request`) to a
  `RecommendationRequest.watchlist_ids` containing the portfolio. An
  evaluation stored before that field existed (`recommendation_result_id
  is None`) is skipped, never guessed at. Milestone 15 left this
  detection disabled entirely because no such linkage existed on a
  *stored* result — resolved by adding the field, not by inventing
  ownership.

Cycle-level locking (§5/§6): `run_cycle()` wraps the entire cycle body in
a `CycleLock` (`InMemoryCycleLock` by default — same-process only;
`PostgresCycleLock` when a durable repository is available — cross-process
safe), so the same cycle can never execute concurrently with itself,
regardless of what triggered the second attempt (scheduler overlap, a
manual operational trigger, or a second process entirely). A contended
lock is a graceful skip, not a failure.

Failure isolation (§17): every per-entity and per-portfolio block is
individually try/except-wrapped — one bad ticker, one unavailable
service, or one publish failure never stops the rest of the cycle. Every
failure is recorded in `ContinuousIntelligenceCycleResult.failures`,
never silently swallowed.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.alerts.engine import AlertService
from app.knowledge.hub import KnowledgeHub
from app.recommendations.engine import PortfolioRecommendationService
from app.risk.engine import RiskAnalyticsService
from app.services.continuous_intelligence.config import ContinuousIntelligenceThresholds
from app.services.continuous_intelligence.decision_impact import DecisionImpactService
from app.services.continuous_intelligence.detector import ChangeDetectionService
from app.services.continuous_intelligence.locking import CycleLock, InMemoryCycleLock
from app.services.continuous_intelligence.models import ChangeDomain, ContinuousIntelligenceCycleResult, DetectedChange
from app.services.continuous_intelligence.state import (
    ContinuousIntelligenceStateStore,
    InMemoryContinuousIntelligenceStateStore,
)
from app.services.continuous_intelligence.suppression import Suppression, SuppressionService
from app.services.entity_resolution.service import EntityResolutionService
from app.services.market_intelligence.engine import MarketIntelligenceEngine
from app.services.market_snapshot.models import MarketSnapshotResult
from app.services.market_snapshot.service import MarketSnapshotService
from app.services.portfolio_market_snapshot.signal_adapter import build_market_data_snapshot
from app.signals.engine import SignalDetectionService
from app.strategy.engine import StrategyEvaluationService
from app.strategy.models import StrategyEvaluationResult

if TYPE_CHECKING:
    from app.api.ws.publishers.event_publisher import EventPublisher

from app.watchlist.service import WatchlistService

__all__ = ["ContinuousIntelligenceService"]

_NEWS_TOP_K = 25
_CYCLE_LOCK_KEY = "continuous_intelligence_cycle"

_logger = logging.getLogger("marketmind.services.continuous_intelligence")


def _default_now() -> datetime:
    return datetime.now(UTC)


class ContinuousIntelligenceService:
    def __init__(
        self,
        *,
        entity_resolver: EntityResolutionService | None,
        market_snapshot_service: MarketSnapshotService,
        knowledge_hub: KnowledgeHub | None,
        signal_service: SignalDetectionService,
        alert_service: AlertService,
        risk_service: RiskAnalyticsService,
        recommendation_service: PortfolioRecommendationService,
        watchlist_service: WatchlistService,
        strategy_service: StrategyEvaluationService | None = None,
        thresholds: ContinuousIntelligenceThresholds | None = None,
        state: ContinuousIntelligenceStateStore | None = None,
        suppression: Suppression | None = None,
        lock: CycleLock | None = None,
        event_publisher: EventPublisher | None = None,
        now_fn: Callable[[], datetime] = _default_now,
    ) -> None:
        self._entity_resolver = entity_resolver
        self._market_snapshot_service = market_snapshot_service
        self._knowledge_hub = knowledge_hub
        self._signal_service = signal_service
        self._alert_service = alert_service
        self._risk_service = risk_service
        self._recommendation_service = recommendation_service
        self._watchlist_service = watchlist_service
        self._strategy_service = strategy_service
        self._thresholds = thresholds or ContinuousIntelligenceThresholds()
        self._state = state or InMemoryContinuousIntelligenceStateStore()
        self._suppression = suppression or SuppressionService(
            self._thresholds.suppression_cooldown_minutes, now_fn=now_fn
        )
        self._lock = lock or InMemoryCycleLock()
        self._decision_impact = DecisionImpactService(watchlist_service)
        self._detector = ChangeDetectionService(self._state, self._thresholds)
        self._market_intelligence_engine = MarketIntelligenceEngine()
        self._event_publisher = event_publisher
        self._now_fn = now_fn

    async def run_cycle(self, execution_id: str) -> ContinuousIntelligenceCycleResult:
        """Run one Continuous Intelligence cycle, guarded by the cycle lock (§5/§6).

        If the lock cannot be acquired (another cycle — same process or a
        different one — is already running), this returns immediately
        with an empty, zero-change `ContinuousIntelligenceCycleResult`
        rather than running concurrently. This is a graceful skip, not a
        failure: it is recorded as a single informational entry in
        `failures` so it is visible in observability/operational output
        without being treated as an application error.
        """
        started_at = self._now_fn()
        _logger.info("continuous_intelligence_cycle_started", extra={"execution_id": execution_id})
        lock_holder = f"{execution_id}:{uuid.uuid4().hex[:8]}"
        acquired = await self._lock.try_acquire(lock_holder, _CYCLE_LOCK_KEY)
        if not acquired:
            _logger.info(
                "continuous_intelligence_cycle_skipped_overlap",
                extra={"execution_id": execution_id},
            )
            completed_at = self._now_fn()
            return ContinuousIntelligenceCycleResult(
                execution_id=execution_id,
                started_at=started_at,
                completed_at=completed_at,
                entities_examined=0,
                market_changes_detected=0,
                news_changes_detected=0,
                decision_changes_detected=0,
                events_emitted=0,
                events_suppressed=0,
                notifications_published=0,
                failures=("cycle_skipped: another continuous intelligence cycle is already running",),
                changes=(),
                suppressed=(),
            )
        try:
            return await self._run_cycle_locked(execution_id, started_at)
        finally:
            await self._lock.release(lock_holder, _CYCLE_LOCK_KEY)

    async def _run_cycle_locked(
        self, execution_id: str, started_at: datetime
    ) -> ContinuousIntelligenceCycleResult:
        failures: list[str] = []
        emitted: list[DetectedChange] = []
        suppressed: list[DetectedChange] = []
        entities_examined = 0
        market_changes_detected = 0
        news_changes_detected = 0
        decision_changes_detected = 0
        events_emitted = 0
        notifications_published = 0

        references = tuple(self._entity_resolver.list_references()) if self._entity_resolver is not None else ()
        entity_ids = [reference.entity_id for reference in references]
        snapshots_by_entity: dict[str, MarketSnapshotResult] = {}
        if entity_ids:
            try:
                # use_cache=False: like MarketDataRefreshWorkflow (Milestone
                # 13), this cycle's entire purpose is to observe the freshest
                # possible state — a cache hit would silently compare a new
                # cycle against itself instead of against genuinely new data.
                results = await self._market_snapshot_service.get_snapshots(entity_ids, use_cache=False)
                snapshots_by_entity = {result.entity_id: result for result in results}
            except Exception as exc:  # noqa: BLE001 - one failed batch must not abort the cycle
                failures.append(f"market_snapshot_batch: {exc}")

        for reference in references:
            entities_examined += 1
            entity_id = reference.entity_id
            label = reference.canonical_name
            snapshot_result = snapshots_by_entity.get(entity_id)

            if snapshot_result is not None:
                try:
                    change = await self._detector.detect_market_change(entity_id, label, snapshot_result)
                    if change is not None:
                        market_changes_detected += 1
                        routed = await self._route(change, reference.ticker)
                        emitted.extend(routed[0])
                        suppressed.extend(routed[1])
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"market:{entity_id}: {exc}")

            if self._knowledge_hub is not None:
                try:
                    news_result = await self._detect_news(entity_id, label, reference.ticker)
                    news_changes_detected += news_result[0]
                    emitted.extend(news_result[1])
                    suppressed.extend(news_result[2])
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"news:{entity_id}: {exc}")

            if snapshot_result is not None:
                try:
                    # A market snapshot exists for this entity only if it
                    # already resolved to a ticker (quote fetching is
                    # ticker-based) — this invariant, not a type gap, is
                    # what `_detect_signals`'s own `ticker: str` (not
                    # `str | None`) already assumes.
                    assert reference.ticker is not None
                    signal_result = await self._detect_signals(entity_id, label, reference.ticker, snapshot_result)
                    decision_changes_detected += signal_result[0]
                    emitted.extend(signal_result[1])
                    suppressed.extend(signal_result[2])
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"signal:{entity_id}: {exc}")

        try:
            watchlists = await self._watchlist_service.list_watchlists()
        except Exception as exc:  # noqa: BLE001
            failures.append(f"watchlists: {exc}")
            watchlists = []

        for watchlist in watchlists:
            portfolio_id = watchlist.id
            label = watchlist.name

            try:
                risk_result = await self._detect_risk(portfolio_id, label)
                decision_changes_detected += risk_result[0]
                emitted.extend(risk_result[1])
                suppressed.extend(risk_result[2])
            except Exception as exc:  # noqa: BLE001
                failures.append(f"risk:{portfolio_id}: {exc}")

            try:
                recommendation_result = await self._detect_recommendations(portfolio_id)
                decision_changes_detected += recommendation_result[0]
                emitted.extend(recommendation_result[1])
                suppressed.extend(recommendation_result[2])
            except Exception as exc:  # noqa: BLE001
                failures.append(f"recommendation:{portfolio_id}: {exc}")

            if self._strategy_service is not None:
                try:
                    strategy_result = await self._detect_strategy(portfolio_id, label)
                    decision_changes_detected += strategy_result[0]
                    emitted.extend(strategy_result[1])
                    suppressed.extend(strategy_result[2])
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"strategy:{portfolio_id}: {exc}")

        events_emitted = len(emitted)
        notifications_published = len(emitted)
        completed_at = self._now_fn()

        result = ContinuousIntelligenceCycleResult(
            execution_id=execution_id,
            started_at=started_at,
            completed_at=completed_at,
            entities_examined=entities_examined,
            market_changes_detected=market_changes_detected,
            news_changes_detected=news_changes_detected,
            decision_changes_detected=decision_changes_detected,
            events_emitted=events_emitted,
            events_suppressed=len(suppressed),
            notifications_published=notifications_published,
            failures=tuple(failures),
            changes=tuple(emitted),
            suppressed=tuple(suppressed),
        )
        _logger.info(
            "continuous_intelligence_cycle_completed",
            extra={
                "execution_id": execution_id,
                "duration_seconds": result.duration_seconds,
                "entities_examined": entities_examined,
                "events_emitted": events_emitted,
                "events_suppressed": len(suppressed),
                "failure_count": len(failures),
            },
        )
        return result

    # --- Per-category detection, each returning (count_detected, emitted, suppressed) -----------------------------

    async def _detect_news(
        self, entity_id: str, label: str, ticker: str | None
    ) -> tuple[int, list[DetectedChange], list[DetectedChange]]:
        assert self._knowledge_hub is not None
        detected = 0
        emitted: list[DetectedChange] = []
        suppressed: list[DetectedChange] = []

        records = await self._knowledge_hub.query(label, top_k=_NEWS_TOP_K)
        record_ids = frozenset(record.id for record in records)
        change = await self._detector.detect_news_change(entity_id, label, record_ids)
        if change is not None:
            detected += 1
            routed = await self._route(change, ticker)
            emitted.extend(routed[0])
            suppressed.extend(routed[1])

        intelligence = self._market_intelligence_engine.analyze(records)
        confidence = next((group.confidence_score for group in intelligence.groups if group.group_key == label), None)
        if confidence is not None:
            confidence_change = await self._detector.detect_news_confidence_change(entity_id, label, confidence)
            if confidence_change is not None:
                detected += 1
                routed = await self._route(confidence_change, ticker)
                emitted.extend(routed[0])
                suppressed.extend(routed[1])

        return detected, emitted, suppressed

    async def _detect_signals(
        self, entity_id: str, label: str, ticker: str, snapshot_result: MarketSnapshotResult
    ) -> tuple[int, list[DetectedChange], list[DetectedChange]]:
        detected = 0
        emitted: list[DetectedChange] = []
        suppressed: list[DetectedChange] = []

        market_data_snapshot = build_market_data_snapshot(ticker, label, snapshot_result)
        definitions = [d for d in await self._signal_service.list_signal_definitions() if d.enabled]
        if not definitions:
            return 0, [], []

        enabled_rules = [rule for rule in await self._alert_service.list_rules() if rule.enabled]

        for definition in definitions:
            signal_result = self._signal_service.evaluate_company(market_data_snapshot, definition)

            change = await self._detector.detect_signal_change(entity_id, label, definition.id, signal_result)
            if change is not None:
                detected += 1
                routed = await self._route(change, ticker)
                emitted.extend(routed[0])
                suppressed.extend(routed[1])

            if signal_result.triggered and enabled_rules:
                # The real, existing alert pathway — its own cooldown/dedup
                # decides GENERATED vs SUPPRESSED, untouched by this milestone.
                await self._alert_service.evaluate_rules(signal_result, enabled_rules)

        return detected, emitted, suppressed

    async def _detect_risk(
        self, portfolio_id: str, label: str
    ) -> tuple[int, list[DetectedChange], list[DetectedChange]]:
        requests = [r for r in await self._risk_service.list_requests() if r.portfolio_id == portfolio_id]
        if not requests:
            return 0, [], []
        latest = max(requests, key=lambda r: r.created_at)
        assessment = await self._risk_service.get_assessment(latest.id)

        change = await self._detector.detect_risk_change(portfolio_id, label, assessment)
        if change is None:
            return 0, [], []
        routed = await self._route(change, None)
        return 1, routed[0], routed[1]

    async def _detect_recommendations(
        self, portfolio_id: str
    ) -> tuple[int, list[DetectedChange], list[DetectedChange]]:
        requests = [r for r in await self._recommendation_service.list_requests() if portfolio_id in r.watchlist_ids]
        if not requests:
            return 0, [], []
        latest = max(requests, key=lambda r: r.created_at)
        result = await self._recommendation_service.get_result(latest.id)

        detected = 0
        emitted: list[DetectedChange] = []
        suppressed: list[DetectedChange] = []
        for candidate in result.recommendations:
            change = await self._detector.detect_recommendation_change(portfolio_id, candidate)
            if change is None:
                continue
            detected += 1
            routed = await self._route(change, None)
            emitted.extend(routed[0])
            suppressed.extend(routed[1])
        return detected, emitted, suppressed

    async def _detect_strategy(
        self, portfolio_id: str, label: str
    ) -> tuple[int, list[DetectedChange], list[DetectedChange]]:
        """Strategy change detection (§16, wired in per Milestone 16 §12):
        finds the most-recently-stored `StrategyEvaluationResult` whose
        `recommendation_result_id` traces back (via
        `PortfolioRecommendationService.get_request`) to a
        `RecommendationRequest.watchlist_ids` containing `portfolio_id` —
        the same "real linkage, never guessed" chain this milestone's
        own §12 investigation established. An evaluation stored before
        this field existed (`recommendation_result_id is None`) is simply
        skipped, never guessed at."""
        assert self._strategy_service is not None
        evaluations = [e for e in await self._strategy_service.list_evaluations() if e.recommendation_result_id]
        if not evaluations:
            return 0, [], []

        matching: list[tuple[StrategyEvaluationResult, datetime]] = []
        for evaluation in evaluations:
            assert evaluation.recommendation_result_id is not None
            try:
                request = await self._recommendation_service.get_request(evaluation.recommendation_result_id)
            except Exception:  # noqa: BLE001 - a dangling/unresolvable reference is skipped, not fatal
                continue
            if portfolio_id in request.watchlist_ids:
                matching.append((evaluation, evaluation.evaluated_at))
        if not matching:
            return 0, [], []

        latest_evaluation, _ = max(matching, key=lambda pair: pair[1])
        change = await self._detector.detect_strategy_change(portfolio_id, label, latest_evaluation)
        if change is None:
            return 0, [], []
        routed = await self._route(change, None)
        return 1, routed[0], routed[1]

    # --- Decision impact + suppression + publish -----------------------------------------------------------

    async def _route(
        self, change: DetectedChange, ticker: str | None
    ) -> tuple[list[DetectedChange], list[DetectedChange]]:
        """Expands `change` across impacted portfolios (§7), applies
        suppression (§8) **per portfolio, independently and unchanged**,
        then publishes (§9) whatever survives.

        v1.2 Priority 2 (cross-portfolio notification grouping): every
        candidate expanded from one `change` shares the same
        `event_fingerprint` (`attach_portfolio_context` never rewrites
        it — only `fingerprint`/`portfolio_id` differ per copy), so one
        `_route()` call is always exactly one underlying event, fanned
        out to at most `len(portfolio_ids)` per-portfolio candidates.
        Suppression is evaluated first, per candidate, exactly as before
        this milestone — grouping never widens or narrows which
        candidates survive. Only *after* that is decided do the
        survivors' `portfolio_id`s get collected into
        `impacted_portfolio_ids` and stamped onto every survivor before
        publish, so each one is self-describing ("this event also
        affects N-1 other portfolios") without needing every other frame
        in the group to have already arrived.

        Deliberately still publishes once per surviving candidate (never
        collapsed into one broadcast) — `EventPublisher`'s own
        `correlation_id` (`portfolio_id or entity_id`) is what lets a
        client subscribe narrowly to one portfolio's events (§10); a
        single collapsed broadcast could only carry one `correlation_id`
        and would silently stop reaching a client narrowly subscribed to
        any of the *other* impacted portfolios. Collapsing three
        network-visible frames into one user-visible Notification Center
        entry is therefore a client-side concern
        (`frontend/src/store/realtime-notification-store.ts`'s
        `event_fingerprint`-keyed upsert) — not a change to how many
        times this method calls `_publish`.
        """
        if change.portfolio_id is None and ticker is not None:
            portfolio_ids = await self._decision_impact.find_impacted_portfolios(ticker)
            candidates = self._decision_impact.attach_portfolio_context(change, portfolio_ids)
        else:
            candidates = (change,)

        emitted: list[DetectedChange] = []
        suppressed: list[DetectedChange] = []
        survivors: list[DetectedChange] = []
        for candidate in candidates:
            if await self._suppression.is_duplicate(candidate.fingerprint):
                suppressed.append(candidate)
                _logger.info(
                    "continuous_intelligence_suppression_hit",
                    extra={"fingerprint": candidate.fingerprint, "domain": candidate.domain.value},
                )
                continue
            await self._suppression.record_emitted(candidate.fingerprint)
            survivors.append(candidate)

        impacted_portfolio_ids = tuple(c.portfolio_id for c in survivors if c.portfolio_id is not None)
        for candidate in survivors:
            grouped = (
                candidate.model_copy(update={"impacted_portfolio_ids": impacted_portfolio_ids})
                if impacted_portfolio_ids
                else candidate
            )
            try:
                await self._publish(grouped)
            except Exception as exc:  # noqa: BLE001 - a publish failure must not lose the underlying detected state
                # The comparison state (detector) and suppression record
                # (above) are already durably written before this point —
                # a failed WebSocket send loses only the *notification*,
                # never the underlying state transition itself (§11). Still
                # surfaced, never silently swallowed (§14).
                _logger.warning(
                    "continuous_intelligence_publish_failed",
                    extra={"fingerprint": grouped.fingerprint, "domain": grouped.domain.value, "error": str(exc)},
                )
            emitted.append(grouped)
        return emitted, suppressed

    async def _publish(self, change: DetectedChange) -> None:
        if self._event_publisher is None:
            return
        if change.domain == ChangeDomain.MARKET:
            await self._event_publisher.publish_significant_market_change(change)
        elif change.domain == ChangeDomain.NEWS:
            await self._event_publisher.publish_significant_news_update(change)
        else:
            await self._event_publisher.publish_portfolio_intelligence_changed(change)
