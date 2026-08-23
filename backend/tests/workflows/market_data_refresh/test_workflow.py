"""Tests for MarketDataRefreshWorkflow, including Milestone 14's optional
`event_publisher` — publishing `MARKET_SNAPSHOT_REFRESHED` after every run
(§11: this workflow runs in-process inside the live server's own
scheduled execution, a valid real-time-event trigger point unlike an
operational script)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.api.ws.connection_manager.manager import ConnectionManager
from app.api.ws.event_models.event_type import EventType
from app.api.ws.publishers.event_publisher import EventPublisher
from app.api.ws.subscriptions.models import Subscription
from app.auth.models.authentication import AuthenticatedPrincipal
from app.core.context import ExecutionContext, TriggerType, WorkflowStatus
from app.providers.market_data.mock import MockMarketDataProvider
from app.services.entity_resolution.models import CompanyReference
from app.services.entity_resolution.service import EntityResolutionService
from app.services.market_snapshot.cache import InMemoryMarketSnapshotCache
from app.services.market_snapshot.service import MarketSnapshotService
from app.workflows.market_data_refresh.workflow import MarketDataRefreshWorkflow
from tests.api.ws.fakes import FakeWebSocket

DELL_REFERENCE = CompanyReference(
    entity_id="dell", canonical_name="Dell Technologies Inc.", ticker="DELL",
    exchange="NYSE", country="United States", sector="Technology",
    industry="Computer Hardware", aliases=("Dell",),
)


def _context(execution_id: str = "exec-1") -> ExecutionContext:
    return ExecutionContext(
        workflow_id="WF-MARKET-DATA-REFRESH",
        execution_id=execution_id,
        workflow_type="market_data_refresh",
        trigger=TriggerType.SCHEDULED,
        initiated_by="test",
        started_at=datetime.now(UTC),
        trace_id=execution_id,
        participating_agents=(),
        status=WorkflowStatus.RUNNING,
    )


def _workflow(event_publisher: EventPublisher | None = None) -> MarketDataRefreshWorkflow:
    market_snapshot_service = MarketSnapshotService(
        MockMarketDataProvider(), EntityResolutionService((DELL_REFERENCE,)), InMemoryMarketSnapshotCache(60.0)
    )
    return MarketDataRefreshWorkflow(
        market_snapshot_service, EntityResolutionService((DELL_REFERENCE,)), event_publisher
    )


async def test_execute_without_event_publisher_preserves_pre_milestone_14_behavior() -> None:
    """§18 regression: no event_publisher supplied -> execute() behaves
    exactly as before Milestone 14, no publish attempted."""
    workflow = _workflow(event_publisher=None)

    result = await workflow.execute(_context())

    assert result.entities_requested == 1
    assert result.fresh_count == 1


async def _subscribed_manager() -> tuple[ConnectionManager, FakeWebSocket]:
    manager = ConnectionManager()
    ws = FakeWebSocket()
    principal = AuthenticatedPrincipal(user_id="u1", username="u1", roles=(), permissions=(), token_id="t1")
    connection_id = await manager.connect(ws, principal)
    manager.subscribe(connection_id, Subscription(event_types=frozenset({EventType.MARKET_SNAPSHOT_REFRESHED})))
    return manager, ws


async def test_execute_with_event_publisher_publishes_market_snapshot_refreshed() -> None:
    manager, ws = await _subscribed_manager()
    workflow = _workflow(event_publisher=EventPublisher(manager))

    result = await workflow.execute(_context(execution_id="exec-42"))

    assert len(ws.sent) == 1
    from app.api.ws.event_models.events import EventEnvelope

    envelope = EventEnvelope.model_validate_json(ws.sent[0])
    assert envelope.event.event_type == EventType.MARKET_SNAPSHOT_REFRESHED
    assert envelope.event.correlation_id == "exec-42"
    assert envelope.event.payload.execution_id == result.execution_id
    assert envelope.event.payload.fresh_count == result.fresh_count
