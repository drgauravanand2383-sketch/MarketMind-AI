"""Market Data Refresh Workflow (Milestone 13).

Refreshes market snapshots for every canonical entity in the Milestone 12
reference set, via `MarketSnapshotService` — the same service Research
uses, so the scheduled refresh keeps the *same* cache Research reads from
warm, rather than maintaining a second, separate cache.

`execute(context)` is the WorkflowProtocol entry point (Sprint 29), the
same contract `MorningPipeline` implements — registered with
`WorkflowEngine`/`Scheduler` exactly the way Milestone 11's ingestion
pipeline is.

Milestone 14 §11: this workflow runs in-process inside the live server's
own APScheduler-triggered execution (unlike an operational script, which
builds its own throwaway `FastAPI()` app and shares no `ConnectionManager`
state with real connected clients) — making it a valid, real trigger point
for `MARKET_SNAPSHOT_REFRESHED`. `event_publisher` is optional so this
workflow's own unit tests (and any caller with no WebSocket infra
configured) are unaffected.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.core.context import ExecutionContext
from app.services.entity_resolution.service import EntityResolutionService
from app.services.market_snapshot.models import MarketSnapshotStatus
from app.services.market_snapshot.service import MarketSnapshotService
from app.workflows.market_data_refresh.models import MarketDataRefreshResult

if TYPE_CHECKING:
    from app.api.ws.publishers.event_publisher import EventPublisher

__all__ = ["MarketDataRefreshWorkflow"]

_logger = logging.getLogger("marketmind.workflows.market_data_refresh")


class MarketDataRefreshWorkflow:
    """Refreshes market snapshots for every known canonical entity."""

    def __init__(
        self,
        market_snapshot_service: MarketSnapshotService,
        entity_resolver: EntityResolutionService,
        event_publisher: EventPublisher | None = None,
    ) -> None:
        """Initialize the workflow.

        Args:
            market_snapshot_service: Used for every quote request — this
                workflow never calls a MarketDataProvider directly.
            entity_resolver: Enumerates the canonical entities to refresh
                (`list_references()`). A required, non-Optional
                dependency here: with no entities to refresh, this
                workflow has nothing meaningful to do, so
                `app.bootstrap.build_market_data_refresh_workflow`
                returns `None` (not constructed) rather than a workflow
                that would always report zero entities.
            event_publisher: Milestone 14, optional. When supplied,
                `execute()` publishes `MARKET_SNAPSHOT_REFRESHED` after
                every run. `None` (the default) preserves this workflow's
                pre-Milestone-14 behavior exactly — no event is published.
        """
        self._market_snapshot_service = market_snapshot_service
        self._entity_resolver = entity_resolver
        self._event_publisher = event_publisher

    async def execute(self, context: ExecutionContext) -> MarketDataRefreshResult:
        started_at = datetime.now(UTC)
        entity_ids = [reference.entity_id for reference in self._entity_resolver.list_references()]

        _logger.info(
            "market_data_refresh_started",
            extra={"execution_id": context.execution_id, "entity_count": len(entity_ids)},
        )

        results = await self._market_snapshot_service.get_snapshots(entity_ids, use_cache=False)

        fresh_count = sum(1 for result in results if result.status == MarketSnapshotStatus.FRESH)
        stale_count = sum(1 for result in results if result.status == MarketSnapshotStatus.STALE)
        unavailable_count = len(results) - fresh_count - stale_count
        completed_at = datetime.now(UTC)

        _logger.info(
            "market_data_refresh_completed",
            extra={
                "execution_id": context.execution_id,
                "entities_requested": len(entity_ids),
                "fresh_count": fresh_count,
                "stale_count": stale_count,
                "unavailable_count": unavailable_count,
                "duration_seconds": (completed_at - started_at).total_seconds(),
            },
        )

        refresh_result = MarketDataRefreshResult(
            execution_id=context.execution_id,
            started_at=started_at,
            completed_at=completed_at,
            entities_requested=len(entity_ids),
            fresh_count=fresh_count,
            stale_count=stale_count,
            unavailable_count=unavailable_count,
            results=results,
        )
        if self._event_publisher is not None:
            await self._event_publisher.publish_market_snapshot_refreshed(refresh_result)
        return refresh_result
