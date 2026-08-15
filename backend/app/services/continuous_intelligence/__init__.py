"""Continuous Intelligence (Milestone 15, hardened for reliability in Milestone 16).

Detects meaningful changes in Market, News/Knowledge, and Decision Context
(Risk/Recommendation/Strategy/Signal) state, deduplicates and suppresses
noise, and — for changes that survive — publishes an existing/new
real-time WS event and/or feeds an existing engine (e.g. a newly-triggered
signal into `AlertService`). No new business/scoring engine: every engine
this package calls is reused exactly as it already existed. Milestone 16
adds durable (Postgres-backed) comparison state, suppression, and
cycle-level locking as alternatives to the Milestone 15 in-memory
defaults — see `docs/architecture/CONTINUOUS_INTELLIGENCE.md` and
`docs/architecture/CONTINUOUS_INTELLIGENCE_PERSISTENCE.md`.
"""

from app.services.continuous_intelligence.config import ContinuousIntelligenceThresholds
from app.services.continuous_intelligence.locking import (
    CycleLock,
    InMemoryCycleLock,
    PostgresCycleLock,
)
from app.services.continuous_intelligence.models import (
    ChangeDomain,
    ChangePriority,
    ContinuousIntelligenceCycleResult,
    DetectedChange,
)
from app.services.continuous_intelligence.service import ContinuousIntelligenceService
from app.services.continuous_intelligence.state import (
    ContinuousIntelligenceStateStore,
    InMemoryContinuousIntelligenceStateStore,
    PostgresContinuousIntelligenceStateStore,
)
from app.services.continuous_intelligence.suppression import (
    PostgresSuppressionService,
    Suppression,
    SuppressionService,
)

__all__ = [
    "ChangeDomain",
    "ChangePriority",
    "DetectedChange",
    "ContinuousIntelligenceCycleResult",
    "ContinuousIntelligenceThresholds",
    "ContinuousIntelligenceStateStore",
    "InMemoryContinuousIntelligenceStateStore",
    "PostgresContinuousIntelligenceStateStore",
    "Suppression",
    "SuppressionService",
    "PostgresSuppressionService",
    "CycleLock",
    "InMemoryCycleLock",
    "PostgresCycleLock",
    "ContinuousIntelligenceService",
]
