"""Job-state tracking for Initial Portfolio Analysis (v1.2 Priority 8).

In-memory only, deliberately — the same documented tradeoff
`InMemoryCycleLock`/`InMemoryContinuousIntelligenceStateStore` already make
for same-process-only state (`app.services.continuous_intelligence.locking`/
`.state`): this store answers "is a job for this portfolio in flight or
already settled right now, in this process", not "what happened,
durably, forever". The durable outcome of a settled job is the real
`RecommendationResult`/`RiskAssessment` rows already persisted by
`PortfolioRecommendationService`/`RiskAnalyticsService` — this store never
duplicates that data, only the transient ANALYZING/ERROR status those two
repositories have no field for.

Restart semantics: a restart loses every in-flight/ERROR record. That is
safe, never a source of duplicate work — `InitialPortfolioAnalysisService
.ensure_initial_analysis()` always re-checks whether a
`RecommendationRequest` already exists for the portfolio before doing
anything, so a lost ANALYZING record simply means the next trigger (the
next company added, or an explicit retry) starts a fresh attempt rather
than resuming a phantom one.
"""

from __future__ import annotations

from typing import Protocol

from app.services.initial_analysis.models import InitialAnalysisState

__all__ = ["InitialAnalysisStateStore", "InMemoryInitialAnalysisStateStore"]


class InitialAnalysisStateStore(Protocol):
    """The async state-store interface `InitialPortfolioAnalysisService` depends on."""

    async def get(self, portfolio_id: str) -> InitialAnalysisState | None: ...

    async def set(self, state: InitialAnalysisState) -> None: ...


class InMemoryInitialAnalysisStateStore:
    """A plain process-local dict, keyed by portfolio_id. See module docstring."""

    def __init__(self) -> None:
        self._states: dict[str, InitialAnalysisState] = {}

    async def get(self, portfolio_id: str) -> InitialAnalysisState | None:
        return self._states.get(portfolio_id)

    async def set(self, state: InitialAnalysisState) -> None:
        self._states[state.portfolio_id] = state
