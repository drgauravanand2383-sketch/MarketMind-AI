"""GlobalMarketIntelligenceWorkflow — the orchestrator satisfying
`app.workflows.engine.WorkflowProtocol`.

Creates one `IntelligenceRun`, resolves each configured `ReportCategory`'s
own `MarketSessionContext` independently (per approved Decision 1 —
never a shared, global "today"), and persists the run. This workflow's
own structure — one independently try/except-wrapped step per category,
never aborting the other eight on one failure — is exactly the shape
Phase 2 plugged real data-fetch/ranking into, and Phase 3 plugs LLM
narrative interpretation into.

Phase 2: when `category_pipeline`/`universe_registry`/
`ranked_asset_repository` are all supplied, each successfully-resolved
category also fetches its configured universe, scores, ranks, and
persists its `RankedAsset`s via `CategoryDataPipeline` — still isolated
per category, so one market's data-fetch failure never aborts another's.

Phase 3: when `research_agent`/`penny_microcap_agent`/`report_repository`
are supplied, each category with at least one ranked asset also generates
and persists a `CategoryIntelligenceReport` — `research_agent` for
`MAIN_REPORT_CATEGORIES`, `penny_microcap_agent` for
`PENNY_MICROCAP_REPORT_CATEGORIES`. Narrative generation is best-effort:
its failure never flips a category's own `succeeded` outcome, because the
deterministic ranking step is this category's core, durable value — a
missing report for a given run is itself honestly queryable (no stored
`CategoryIntelligenceReport`), never silently masked as a category
failure (see `_generate_and_persist_report`'s own docstring).

Any Phase 2 or Phase 3 dependency being `None` (e.g. no live
`MarketDataProvider`/`LLMService` configured at startup) degrades this
workflow back to the next simplest behavior it can still offer, never
crashing — matching this codebase's established "degrade, never crash"
convention for an unavailable dependency.

Phase 5: when `event_publisher` is supplied, `execute()` publishes
`GLOBAL_MARKET_INTELLIGENCE_RUN_COMPLETED` exactly once, immediately
after the run is successfully, durably persisted via `create_run` —
never before persistence (a client fetching the run over REST the
moment the event arrives must always find it there), and never on the
idempotent-short-circuit or duplicate-race return paths (no duplicate
event for a run that was already announced). A delivery failure is
caught and logged, never allowed to fail an already-persisted run — see
`execute()`'s own try/except around the publish call, mirroring
`ContinuousIntelligenceService`'s established "a publish failure must
not lose the underlying detected state" precedent.

`run_date` is the master scheduler's own IST calendar date (approved
Decision 1: "the master report scheduler runs at 08:30 Asia/Kolkata") —
deliberately distinct from any individual category's own
`MarketSessionContext.market_session_date`, which is independently
resolved per market region and may legitimately differ (e.g. China's
`market_session_date` can already be "today" while India's is still
"yesterday," depending on the exact instant `execute()` runs).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from app.agents.global_markets_research.agent import GlobalMarketsResearchAgent
from app.agents.global_markets_research.models import GlobalMarketsResearchRequest
from app.agents.penny_microcap_intelligence.agent import PennyMicrocapIntelligenceAgent
from app.agents.penny_microcap_intelligence.models import PennyMicrocapIntelligenceRequest
from app.core.context import ExecutionContext
from app.global_markets.models import (
    MAIN_REPORT_CATEGORIES,
    REPORT_CATEGORY_DEFINITIONS,
    CategoryRunOutcome,
    IntelligenceRun,
    MarketSessionContext,
    ReportCategory,
)
from app.global_markets.pipeline.category_pipeline import CategoryDataPipeline
from app.global_markets.ranked_asset import RankedAsset
from app.global_markets.ranking.defaults import DEFAULT_MAIN_RANKING_WEIGHTS, DEFAULT_PENNY_MICROCAP_RANKING_WEIGHTS
from app.global_markets.ranking.models import RankingWeights
from app.global_markets.session.resolver import MarketSessionResolutionService
from app.global_markets.universe.registry import UniverseRegistry
from app.repositories.global_markets.ranked_asset_repository import BaseRankedAssetRepository
from app.repositories.global_markets.report_repository import BaseIntelligenceReportRepository
from app.repositories.global_markets.repository import (
    BaseGlobalMarketRunRepository,
    DuplicateIntelligenceRunError,
)

if TYPE_CHECKING:
    # Type-checking only: `app.api.ws` is pure API-layer infrastructure —
    # this module never imports it at runtime, matching `app.bootstrap`'s
    # own established reasoning for `EventPublisher` (see that module's
    # `TYPE_CHECKING` block) — `event_publisher` is always injected by the
    # caller, never constructed here.
    from app.api.ws.publishers.event_publisher import EventPublisher

__all__ = ["MASTER_SCHEDULER_TIMEZONE", "GlobalMarketIntelligenceWorkflow"]

MASTER_SCHEDULER_TIMEZONE = ZoneInfo("Asia/Kolkata")

_logger = logging.getLogger("marketmind.workflows.global_markets")


def _default_now() -> datetime:
    return datetime.now(UTC)


def _default_run_id() -> str:
    return str(uuid.uuid4())


def _ranking_weights_for(category: ReportCategory) -> RankingWeights:
    if category in MAIN_REPORT_CATEGORIES:
        return DEFAULT_MAIN_RANKING_WEIGHTS
    return DEFAULT_PENNY_MICROCAP_RANKING_WEIGHTS


class GlobalMarketIntelligenceWorkflow:
    """Orchestrates one Global Market Intelligence run across every
    configured `ReportCategory`, each category's own session resolution,
    data fetch/ranking, and narrative generation (each only when wired)
    isolated so one market's failure never aborts the rest."""

    def __init__(
        self,
        session_resolver: MarketSessionResolutionService,
        run_repository: BaseGlobalMarketRunRepository | None,
        *,
        categories: tuple[ReportCategory, ...] = tuple(REPORT_CATEGORY_DEFINITIONS),
        now_fn: Callable[[], datetime] = _default_now,
        id_fn: Callable[[], str] = _default_run_id,
        category_pipeline: CategoryDataPipeline | None = None,
        universe_registry: UniverseRegistry | None = None,
        ranked_asset_repository: BaseRankedAssetRepository | None = None,
        research_agent: GlobalMarketsResearchAgent | None = None,
        penny_microcap_agent: PennyMicrocapIntelligenceAgent | None = None,
        report_repository: BaseIntelligenceReportRepository | None = None,
        event_publisher: EventPublisher | None = None,
    ) -> None:
        """Initialize the workflow.

        Args:
            session_resolver: Resolves each category's `MarketSessionContext`.
            run_repository: Persists the resulting `IntelligenceRun`. When
                `None` (e.g. PostgreSQL unreachable at startup), the
                workflow still runs and returns its result — it simply
                isn't persisted, matching this codebase's established
                "degrade, never crash" convention for an unavailable
                repository.
            categories: Which `ReportCategory` members to run this
                execution — defaults to all nine. A future retry-one-
                category capability passes a narrower tuple here.
            now_fn: Injected clock (UTC) — tests pass a fixed value for
                deterministic, reproducible results.
            id_fn: Injected id generator — tests pass a fixed value for
                deterministic assertions.
            category_pipeline: Fetches/scores/ranks one category's
                universe — see `CategoryDataPipeline`. `None` degrades to
                session-resolution-only behavior for that category.
            universe_registry: Supplies each category's candidate
                tickers. `None` degrades the same way as `category_pipeline`.
            ranked_asset_repository: Persists each category's ranked
                results. `None` degrades the same way.
            research_agent: Generates a narrative report for
                `MAIN_REPORT_CATEGORIES`. `None` skips narrative
                generation for those categories only.
            penny_microcap_agent: Generates a narrative report for
                `PENNY_MICROCAP_REPORT_CATEGORIES`. `None` skips
                narrative generation for those categories only.
            report_repository: Persists each category's
                `CategoryIntelligenceReport`. `None` skips narrative
                generation entirely (no agent is ever called without
                somewhere to persist its result).
            event_publisher: Publishes `GLOBAL_MARKET_INTELLIGENCE_RUN_
                COMPLETED` once the run is successfully persisted. `None`
                (the default) publishes nothing — this workflow's own
                unit tests (and any caller with no WebSocket infra
                configured) are unaffected, matching
                `MarketDataRefreshWorkflow`'s own established convention
                for this exact parameter.
        """
        self._session_resolver = session_resolver
        self._run_repository = run_repository
        self._categories = categories
        self._now_fn = now_fn
        self._id_fn = id_fn
        self._category_pipeline = category_pipeline
        self._universe_registry = universe_registry
        self._ranked_asset_repository = ranked_asset_repository
        self._research_agent = research_agent
        self._penny_microcap_agent = penny_microcap_agent
        self._report_repository = report_repository
        self._event_publisher = event_publisher

    async def execute(self, context: ExecutionContext) -> IntelligenceRun:
        as_of = self._now_fn()
        run_date = as_of.astimezone(MASTER_SCHEDULER_TIMEZONE).date()

        if self._run_repository is not None:
            already_stored = await self._run_repository.get_run_by_date(run_date)
            if already_stored is not None:
                # Idempotent scheduled runs: a run for this run_date
                # already exists (the scheduler fired twice, or a manual
                # trigger raced the automatic one). Return it without
                # redoing any category resolution or data-fetch work.
                return already_stored

        run_id = self._id_fn()
        outcomes = tuple(
            [await self._resolve_category(context, run_id, category, as_of) for category in self._categories]
        )
        status = IntelligenceRun.derive_status(outcomes)

        run = IntelligenceRun(
            id=run_id,
            run_date=run_date,
            status=status,
            category_outcomes=outcomes,
            triggered_by=context.initiated_by,
            started_at=as_of,
            completed_at=self._now_fn(),
        )

        if self._run_repository is None:
            return run

        try:
            persisted_run = await self._run_repository.create_run(run)
        except DuplicateIntelligenceRunError:
            # A genuine race: another execution's create_run committed
            # between this run's own early-return check above and its own
            # create_run call. This run's own freshly-computed RankedAssets
            # (if any were persisted) are simply not referenced by the
            # returned IntelligenceRun — an accepted, pre-existing
            # tradeoff (the original Phase 1 code already discarded the
            # freshly-built IntelligenceRun object itself on this same
            # race); full distributed-lock idempotency is out of scope.
            # No event publish here either: the execution that actually
            # won the race already published for this run_date.
            existing = await self._run_repository.get_run_by_date(run_date)
            return existing if existing is not None else run

        await self._publish_run_completed(persisted_run)
        return persisted_run

    async def _publish_run_completed(self, run: IntelligenceRun) -> None:
        """Best-effort: publish `GLOBAL_MARKET_INTELLIGENCE_RUN_COMPLETED`
        for a run that was just successfully, durably persisted. Never
        raises — a WebSocket delivery failure must not fail an
        already-persisted run, mirroring `ContinuousIntelligenceService`'s
        own "a publish failure must not lose the underlying detected
        state" precedent (`app/services/continuous_intelligence/service.py`).
        """
        if self._event_publisher is None:
            return
        try:
            await self._event_publisher.publish_global_market_intelligence_run_completed(run)
        except Exception as exc:  # noqa: BLE001 - a publish failure must not fail an already-persisted run
            _logger.warning(
                "global_market_intelligence_publish_failed",
                extra={"run_id": run.id, "run_date": str(run.run_date), "error": str(exc)},
            )

    async def _resolve_category(
        self, context: ExecutionContext, run_id: str, category: ReportCategory, as_of: datetime
    ) -> CategoryRunOutcome:
        """Resolve one category's `MarketSessionContext`, then (when
        wired) fetch/score/rank/persist its `RankedAsset`s, then (when
        wired) generate/persist its narrative report — isolated: a
        session or ranking failure here becomes that one category's own
        failed outcome; a narrative failure never does (see
        `_generate_and_persist_report`)."""
        definition = REPORT_CATEGORY_DEFINITIONS[category]
        try:
            session_context = self._session_resolver.resolve(definition.market_region, as_of=as_of)
        except Exception as exc:  # noqa: BLE001 - one category's failure must never abort the run
            return CategoryRunOutcome(category=category, succeeded=False, market_session_context=None, error=str(exc))

        if self._category_pipeline is None or self._universe_registry is None or self._ranked_asset_repository is None:
            return CategoryRunOutcome(category=category, succeeded=True, market_session_context=session_context)

        is_penny_microcap = category not in MAIN_REPORT_CATEGORIES
        try:
            universe = self._universe_registry.get(category)
            ranked_assets = await self._category_pipeline.run(
                run_id,
                category,
                universe,
                _ranking_weights_for(category),
                session_context.data_freshness_status,
                classify_risk=is_penny_microcap,
            )
            await self._ranked_asset_repository.replace_ranked_assets(run_id, category, ranked_assets)
        except Exception as exc:  # noqa: BLE001 - one category's failure must never abort the run
            return CategoryRunOutcome(
                category=category, succeeded=False, market_session_context=session_context, error=str(exc)
            )

        if ranked_assets:
            await self._generate_and_persist_report(
                context, run_id, category, session_context, ranked_assets, is_penny_microcap
            )

        return CategoryRunOutcome(category=category, succeeded=True, market_session_context=session_context)

    async def _generate_and_persist_report(
        self,
        context: ExecutionContext,
        run_id: str,
        category: ReportCategory,
        session_context: MarketSessionContext,
        ranked_assets: tuple[RankedAsset, ...],
        is_penny_microcap: bool,
    ) -> None:
        """Best-effort narrative generation and persistence.

        Never raises, and never affects the category's own `succeeded`/
        `error` outcome: the deterministic ranking step already completed
        and persisted successfully by the time this runs, which is this
        category's core, durable value. A narrative report is an
        additive enhancement layered on top — its absence for a given
        run is itself honestly queryable (no stored
        `CategoryIntelligenceReport` for that `(run_id, category)`),
        never silently reported as a category failure.
        """
        if self._report_repository is None:
            return
        try:
            if is_penny_microcap:
                if self._penny_microcap_agent is None:
                    return
                penny_request = PennyMicrocapIntelligenceRequest(
                    run_id=run_id,
                    category=category,
                    market_session_context=session_context,
                    ranked_assets=ranked_assets,
                )
                report = await self._penny_microcap_agent.run(context, penny_request)
            else:
                if self._research_agent is None:
                    return
                research_request = GlobalMarketsResearchRequest(
                    run_id=run_id,
                    category=category,
                    market_session_context=session_context,
                    ranked_assets=ranked_assets,
                )
                report = await self._research_agent.run(context, research_request)
            await self._report_repository.save_report(report)
        except Exception:  # noqa: BLE001 - narrative generation must never fail a category
            return
