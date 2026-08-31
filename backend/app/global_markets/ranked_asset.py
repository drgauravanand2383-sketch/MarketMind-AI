"""RankedAsset — one persisted, ranked result for one asset within one
report category of one `IntelligenceRun`.

Deliberately NOT added to `app.global_markets.models`: that module is
the acyclic leaf both `app.repositories.global_markets` and
`app.workflows.global_markets` depend on without pulling in `ranking` or
`eligibility` (see `IntelligenceRun`'s own docstring on that constraint).
`RankedAsset` legitimately composes `FactorScore`
(`app.global_markets.ranking.models`) and `RiskClassification`
(`app.global_markets.ranking.classification`), so it lives in its own
sibling module instead — `models.py` stays a cycle-free leaf.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.global_markets.models import NormalizedAssetSnapshot, ReportCategory
from app.global_markets.ranking.classification import RiskClassification
from app.global_markets.ranking.models import FactorScore

__all__ = ["RankedAsset"]


class RankedAsset(BaseModel):
    """One asset's final, persisted ranked result — the "Persist Ranked
    Assets" entity from this feature's own orchestration diagram. One row
    per (run, category, ticker); `WeightedRankingEngine`'s own tie-break
    (`(-final_score, ticker)`) is what gives `rank` a deterministic value.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    category: ReportCategory
    rank: int = Field(gt=0)
    final_score: float = Field(ge=0.0, le=100.0)
    factor_scores: tuple[FactorScore, ...] = Field(default_factory=tuple)
    snapshot: NormalizedAssetSnapshot
    risk_classification: RiskClassification | None = None
    """Only populated for `PENNY_MICROCAP_REPORT_CATEGORIES` — the five
    main categories don't compute a risk classification (see
    `app.global_markets.ranking.classification.classify`'s own docstring
    on what it needs as input)."""
