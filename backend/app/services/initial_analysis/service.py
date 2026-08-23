"""InitialPortfolioAnalysisService — v1.2 Priority 8.

Root cause of an empty new-watchlist Decision Center (traced against the
real code, not assumed): `WatchlistService` is deliberately metadata-only
("no market scanning and no AI reasoning of any kind" — its own module
docstring) and nothing else in this codebase ever calls
`RiskAnalyticsService.assess_portfolio()`/`PortfolioRecommendationService
.generate_recommendations()` on a portfolio's behalf automatically:

- `POST /portfolio/recommendations` (`app.api.v1.portfolio.router`) is the
  *only* caller of `generate_recommendations()` anywhere in this codebase,
  and it requires the client to supply `evidence: list[CandidateEvidence]`
  itself — there has never been an automatic evidence-sourcing pipeline
  (confirmed by `ContinuousIntelligenceService`'s own docstring: "this
  service never calls `assess_portfolio()`/`generate_recommendations()`
  itself (no evidence-sourcing pipeline exists to feed them)").
- `assess_portfolio()` has *zero* callers anywhere in production code — the
  Portfolio router's own docstring names this outright as a "known gap":
  "`GET /portfolio/risk` is a read-only lookup of an already-stored
  RiskAssessment; no endpoint anywhere calls `RiskAnalyticsService
  .assess_portfolio()`."
- `ContinuousIntelligenceService._detect_risk`/`_detect_recommendations`
  only ever look up the *most-recently-stored* request for a portfolio; if
  none exists yet they return `(0, [], [])` immediately — the 15-minute
  cycle detects *changes* to an existing assessment, it never bootstraps
  the first one. A portfolio with no initial assessment is silently
  skipped by every single CI cycle, forever.

Nothing was broken; no evaluation service had a bug. This service is the
one piece of composition that was simply never built: the very first
`CandidateEvidence` bundle for a brand new portfolio, sourced entirely from
already-existing services (no new scoring, no second evaluation engine),
and the one call each into `PortfolioRecommendationService`/
`RiskAnalyticsService` needed to give a new watchlist an initial state.

Ordering note (corrects the task brief's own stated flow): Risk is
*downstream* of Recommendations, not upstream — `RiskAnalyticsService
.assess_portfolio()` takes an already-generated `RecommendationResult` as
a required argument (see `app.risk.engine`'s own module docstring:
"Evaluates already-generated RecommendationResult... output for portfolio
risk characteristics"). This service therefore always generates the
Recommendation first, then feeds its result into Risk — the reverse order
is not something this architecture can support, and building a second
"Risk from scratch" path would be exactly the "second evaluation engine"
this priority forbids.

Evidence sourced per company, mirroring exactly what `ContinuousIntelligenceService
._detect_signals` already does per-entity (Milestone 15/16), just newly
composed at the portfolio level and triggered once, at watchlist-creation
time, instead of never:

- `market_snapshot`: `PortfolioMarketSnapshotService.get_portfolio_snapshot()`
  (Milestone 14) — real, available immediately.
- `signals`: `SignalDetectionService.evaluate_company()` against every
  enabled `SignalDefinition`, fed a `MarketDataSnapshot` built from the
  market snapshot above (`build_market_data_snapshot`) — pure, synchronous,
  no new I/O.
- `alerts`: `AlertService.evaluate_rules()` for every triggered signal,
  against every enabled `AlertRule` — the real, existing alert pathway,
  with its own untouched cooldown/dedup (Sprint 48), exactly like CI's own
  `_detect_signals`. Never publishes `ALERT_GENERATED` itself — CI's own
  cycle doesn't either; only the manual Alerts REST endpoint does.
- `screening_result`/`research_report`/`portfolio_summary`/`planning_score`:
  left `None` — Screening, Company Research, and Portfolio Intelligence are
  AI/agent-driven subsystems with no existing automatic trigger for a new
  watchlist, and adding one is out of this priority's scope (and would
  make watchlist creation depend on a Claude API call). This is an honest
  "unavailable input", not a fabricated one — `PortfolioRecommendationService
  ._confidence()` already reports lower confidence for a candidate built
  from fewer evidence sources, exactly as designed.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

from app.alerts.engine import AlertService
from app.alerts.models import Alert
from app.recommendations.engine import PortfolioRecommendationService
from app.recommendations.models import CandidateEvidence, RecommendationRequest
from app.risk.engine import RiskAnalyticsService
from app.risk.models import MarketDataCoverageStatus
from app.services.continuous_intelligence.locking import CycleLock, InMemoryCycleLock
from app.services.initial_analysis.models import InitialAnalysisState, InitialAnalysisStatus
from app.services.initial_analysis.state import (
    InitialAnalysisStateStore,
    InMemoryInitialAnalysisStateStore,
)
from app.services.portfolio_market_snapshot.service import PortfolioMarketSnapshotService
from app.services.portfolio_market_snapshot.signal_adapter import build_market_data_snapshot
from app.signals.engine import SignalDetectionService
from app.signals.models import SignalResult
from app.watchlist.exceptions import WatchlistNotFoundError
from app.watchlist.models import Watchlist
from app.watchlist.service import WatchlistService

if TYPE_CHECKING:
    from app.api.ws.publishers.event_publisher import EventPublisher

__all__ = ["InitialPortfolioAnalysisService"]

_LOCK_KEY_PREFIX = "initial_analysis"

_logger = logging.getLogger("marketmind.services.initial_analysis")


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


class InitialPortfolioAnalysisService:
    """Bootstraps a brand new portfolio's first Risk/Recommendation state.

    Pure composition over already-existing services (see module docstring)
    — no new scoring, no new scheduler. `ensure_initial_analysis()` is
    idempotent and safe to call repeatedly/concurrently for the same
    portfolio: a `CycleLock` (same abstraction Continuous Intelligence
    already uses, a fresh instance here so this service's own concurrency
    is independent of whether CI is enabled) prevents two attempts running
    at once, and an existence check — "does a RecommendationRequest already
    reference this portfolio?" — makes a repeat call for an
    already-analyzed portfolio a cheap no-op rather than a duplicate
    assessment.
    """

    def __init__(
        self,
        *,
        watchlist_service: WatchlistService,
        portfolio_market_snapshot_service: PortfolioMarketSnapshotService,
        signal_service: SignalDetectionService,
        alert_service: AlertService,
        recommendation_service: PortfolioRecommendationService,
        risk_service: RiskAnalyticsService,
        state_store: InitialAnalysisStateStore | None = None,
        lock: CycleLock | None = None,
        event_publisher: EventPublisher | None = None,
        now_fn: Callable[[], datetime] = _default_now,
    ) -> None:
        self._watchlist_service = watchlist_service
        self._portfolio_market_snapshot_service = portfolio_market_snapshot_service
        self._signal_service = signal_service
        self._alert_service = alert_service
        self._recommendation_service = recommendation_service
        self._risk_service = risk_service
        self._state_store = state_store or InMemoryInitialAnalysisStateStore()
        self._lock = lock or InMemoryCycleLock()
        self._event_publisher = event_publisher
        self._now_fn = now_fn

    async def get_status(self, portfolio_id: str) -> InitialAnalysisState:
        """Return the current initial-analysis status for `portfolio_id`.

        Never raises for "not yet analyzed" — only `WatchlistNotFoundError`
        propagates (no watchlist means no valid status to report at all).
        """
        state = await self._state_store.get(portfolio_id)
        if state is not None:
            return state

        # No in-process job record (never triggered yet, or this process
        # restarted after a completed job — see `state.py`'s own restart
        # semantics). Self-heal from whatever is actually persisted rather
        # than claiming "unavailable" for a portfolio that was, in truth,
        # already analyzed before this process started.
        existing = await self._find_existing_request(portfolio_id)
        if existing is not None:
            return InitialAnalysisState(
                portfolio_id=portfolio_id,
                status=InitialAnalysisStatus.READY,
                detail=(
                    "Restored from persisted results after a process restart; "
                    "the original READY/PARTIAL distinction was not durably recorded."
                ),
                recommendation_request_id=existing.id,
                completed_at=existing.created_at,
            )

        watchlist = await self._watchlist_service.get_watchlist(portfolio_id)
        if not watchlist.items:
            return InitialAnalysisState(
                portfolio_id=portfolio_id,
                status=InitialAnalysisStatus.UNAVAILABLE,
                detail="No companies tracked yet.",
            )
        return InitialAnalysisState(
            portfolio_id=portfolio_id,
            status=InitialAnalysisStatus.UNAVAILABLE,
            detail="Initial analysis has not run yet.",
        )

    async def ensure_initial_analysis(self, portfolio_id: str) -> None:
        """Run the initial analysis for `portfolio_id`, unless one already
        exists or is already in flight. Never raises — designed to be
        called from a `BackgroundTasks` job or a retry endpoint, neither of
        which has anyone to propagate an exception to; failures are
        recorded via the state store instead (`InitialAnalysisStatus.ERROR`).
        """
        if await self._find_existing_request(portfolio_id) is not None:
            return

        execution_id = str(uuid.uuid4())
        lock_key = f"{_LOCK_KEY_PREFIX}:{portfolio_id}"
        acquired = await self._lock.try_acquire(execution_id, lock_key)
        if not acquired:
            # Another attempt (a second `add_company` call, or a manual
            # retry) is already running this exact job — graceful skip,
            # not a failure, exactly like Continuous Intelligence's own
            # cycle lock (§4/§11: the same portfolio must never be
            # evaluated simultaneously by two paths).
            return
        try:
            if await self._find_existing_request(portfolio_id) is not None:
                return
            await self._run(portfolio_id)
        finally:
            await self._lock.release(execution_id, lock_key)

    async def _find_existing_request(self, portfolio_id: str) -> RecommendationRequest | None:
        requests = [r for r in await self._recommendation_service.list_requests() if portfolio_id in r.watchlist_ids]
        if not requests:
            return None
        return max(requests, key=lambda r: r.created_at)

    async def _run(self, portfolio_id: str) -> None:
        started_at = self._now_fn()
        await self._state_store.set(
            InitialAnalysisState(
                portfolio_id=portfolio_id,
                status=InitialAnalysisStatus.ANALYZING,
                detail="Initial analysis in progress.",
                started_at=started_at,
            )
        )

        try:
            watchlist = await self._watchlist_service.get_watchlist(portfolio_id)
        except WatchlistNotFoundError:
            # The watchlist was deleted before this background job ran —
            # nothing to analyze, and no portfolio left for anyone to poll
            # status for. Leave no dangling ANALYZING record behind.
            await self._state_store.set(
                InitialAnalysisState(
                    portfolio_id=portfolio_id,
                    status=InitialAnalysisStatus.ERROR,
                    detail="Watchlist no longer exists.",
                    started_at=started_at,
                    completed_at=self._now_fn(),
                )
            )
            return

        if not watchlist.items:
            await self._state_store.set(
                InitialAnalysisState(
                    portfolio_id=portfolio_id,
                    status=InitialAnalysisStatus.UNAVAILABLE,
                    detail="No companies tracked yet.",
                    started_at=started_at,
                    completed_at=self._now_fn(),
                )
            )
            return

        try:
            evidence = await self._build_evidence(watchlist)

            recommendation_request = await self._recommendation_service.create_request(
                request_name=f"initial-analysis-{portfolio_id}-{uuid.uuid4()}",
                watchlist_ids=(portfolio_id,),
            )
            recommendation_result = await self._recommendation_service.generate_recommendations(
                recommendation_request, evidence
            )
            if self._event_publisher is not None:
                await self._event_publisher.publish_recommendation_generated(recommendation_result)

            risk_request = await self._risk_service.create_request(
                request_name=f"initial-analysis-{portfolio_id}-{uuid.uuid4()}",
                portfolio_id=portfolio_id,
                recommendation_result_id=recommendation_result.request_id,
            )
            assessment = await self._risk_service.assess_portfolio(risk_request, recommendation_result)
            if self._event_publisher is not None:
                await self._event_publisher.publish_risk_assessment_completed(assessment)
        except Exception as exc:  # noqa: BLE001 - a background job must record failure, never crash silently or raise to nowhere
            _logger.warning(
                "initial_portfolio_analysis_failed",
                extra={"portfolio_id": portfolio_id, "error": str(exc)},
            )
            await self._state_store.set(
                InitialAnalysisState(
                    portfolio_id=portfolio_id,
                    status=InitialAnalysisStatus.ERROR,
                    detail=f"Initial analysis failed: {exc}",
                    started_at=started_at,
                    completed_at=self._now_fn(),
                )
            )
            return

        coverage = assessment.market_data_coverage
        is_full_coverage = coverage is not None and coverage.status == MarketDataCoverageStatus.FULL
        status = InitialAnalysisStatus.READY if is_full_coverage else InitialAnalysisStatus.PARTIAL
        detail = (
            "Initial analysis complete: live market data resolved for every tracked company."
            if is_full_coverage
            else "Initial analysis complete, but market data was unavailable for one or more "
            "tracked companies — see the risk assessment's own market_data_coverage for detail."
        )
        await self._state_store.set(
            InitialAnalysisState(
                portfolio_id=portfolio_id,
                status=status,
                detail=detail,
                recommendation_request_id=recommendation_request.id,
                risk_request_id=risk_request.id,
                started_at=started_at,
                completed_at=self._now_fn(),
            )
        )

    async def _build_evidence(self, watchlist: Watchlist) -> list[CandidateEvidence]:
        portfolio_snapshot = await self._portfolio_market_snapshot_service.get_portfolio_snapshot(watchlist)
        definitions = [d for d in await self._signal_service.list_signal_definitions() if d.enabled]
        rules = [r for r in await self._alert_service.list_rules() if r.enabled]

        evidence: list[CandidateEvidence] = []
        for item, snapshot_result in zip(watchlist.items, portfolio_snapshot.company_snapshots, strict=True):
            signals: list[SignalResult] = []
            alerts: list[Alert] = []
            if definitions:
                market_data_snapshot = build_market_data_snapshot(item.ticker, item.company_name, snapshot_result)
                for definition in definitions:
                    signal_result = self._signal_service.evaluate_company(market_data_snapshot, definition)
                    signals.append(signal_result)
                    if signal_result.triggered and rules:
                        batch = await self._alert_service.evaluate_rules(signal_result, rules)
                        alerts.extend(batch.alerts)

            evidence.append(
                CandidateEvidence(
                    ticker=item.ticker,
                    company_name=item.company_name,
                    country=item.country,
                    sector=item.sector,
                    signals=tuple(signals),
                    alerts=tuple(alerts),
                    market_snapshot=snapshot_result,
                )
            )
        return evidence
