"""Explicit, typed significance thresholds for Continuous Intelligence (§3).

Every number here is a named, documented field — never an unexplained
literal inline in a detector. Built from `AppSettings` in
`app.bootstrap.build_continuous_intelligence_service` (`MARKET_CHANGE_THRESHOLD`,
`NEWS_SIGNIFICANCE_THRESHOLD`, ... — see that module and
`docs/architecture/CONTINUOUS_INTELLIGENCE.md` §3 for the full list and
defaults), but constructible directly for tests without touching settings.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["ContinuousIntelligenceThresholds"]


class ContinuousIntelligenceThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    market_change_percent_threshold: float = Field(
        default=3.0, gt=0,
        description=(
            "Minimum |change_percent| (e.g. 3.0 = 3%) versus the previously "
            "observed price for a market move to be significant."
        ),
    )
    news_significance_threshold: int = Field(
        default=2, ge=1,
        description=(
            "Minimum number of newly-seen knowledge records for one watched "
            "entity since the last cycle to be significant."
        ),
    )
    news_high_confidence_threshold: float = Field(
        default=0.75, gt=0, le=1,
        description=(
            "MarketIntelligence.group_confidence (0-1) an entity's evidence must "
            "newly cross to count as 'new high-confidence evidence.'"
        ),
    )
    recommendation_score_delta_threshold: float = Field(
        default=10.0, gt=0,
        description=(
            "Minimum |overall_score| delta (0-100 scale) for a recommendation "
            "change to be significant, when the RecommendationType itself did "
            "not also change."
        ),
    )
    strategy_alignment_delta_threshold: float = Field(
        default=10.0, gt=0,
        description=(
            "Minimum |overall_alignment| delta (0-100 scale) for a strategy "
            "evaluation change to be significant."
        ),
    )
    suppression_cooldown_minutes: float = Field(
        default=60.0, ge=0,
        description="How long an identical DetectedChange fingerprint is suppressed after being emitted once.",
    )
    cycle_lock_ttl_seconds: float = Field(
        default=300.0, gt=0,
        description="Milestone 16 §5/§6: how long a cycle-lock claim (PostgresCycleLock) is honored before being "
        "treated as abandoned and automatically reclaimed by the next caller. Should comfortably exceed a normal "
        "cycle's duration but not so long that a genuinely crashed holder blocks recovery for an unreasonable time.",
    )
