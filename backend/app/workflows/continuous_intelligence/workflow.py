"""Continuous Intelligence Workflow (Milestone 15).

`execute(context)` is the WorkflowProtocol entry point (Sprint 29), the
same contract `MorningPipeline`/`MarketDataRefreshWorkflow` implement —
registered with `WorkflowEngine`/`Scheduler` exactly the way those two
already are. A thin adapter only: every actual detection/suppression/
publish step lives in `ContinuousIntelligenceService`, reused unchanged
whether invoked from this scheduled workflow or directly (e.g. by
`scripts/run_continuous_intelligence.py`).
"""

from __future__ import annotations

from app.core.context import ExecutionContext
from app.services.continuous_intelligence.models import ContinuousIntelligenceCycleResult
from app.services.continuous_intelligence.service import ContinuousIntelligenceService

__all__ = ["ContinuousIntelligenceWorkflow"]


class ContinuousIntelligenceWorkflow:
    def __init__(self, service: ContinuousIntelligenceService) -> None:
        self._service = service

    async def execute(self, context: ExecutionContext) -> ContinuousIntelligenceCycleResult:
        return await self._service.run_cycle(context.execution_id)
