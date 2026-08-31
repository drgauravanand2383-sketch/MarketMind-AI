"""Ranking contract models — the extensible scoring shape Phase 1
establishes, deliberately without a hardcoded final ranking formula (per
this module's own explicit "do not prematurely hardcode the final
ranking formula" requirement).

`RankingFactor` names every input the architecture must eventually
support (price performance, momentum, volume/liquidity, volatility,
market cap, risk, source confidence, data freshness, cross-source
agreement, news/event impact, technical signals, fundamental signals —
the exact list this module's own requirements name) even though Phase 1
computes real values for only a subset of them (later phases add the
rest without changing this contract).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["RankingFactor", "FactorScore", "RankingWeights", "RankedAssetScore"]


class RankingFactor(StrEnum):
    """One named, individually-inspectable ranking input."""

    PRICE_PERFORMANCE = "PRICE_PERFORMANCE"
    MOMENTUM = "MOMENTUM"
    VOLUME_LIQUIDITY = "VOLUME_LIQUIDITY"
    VOLATILITY = "VOLATILITY"
    MARKET_CAP = "MARKET_CAP"
    RISK = "RISK"
    SOURCE_CONFIDENCE = "SOURCE_CONFIDENCE"
    DATA_FRESHNESS = "DATA_FRESHNESS"
    CROSS_SOURCE_AGREEMENT = "CROSS_SOURCE_AGREEMENT"
    NEWS_EVENT_IMPACT = "NEWS_EVENT_IMPACT"
    TECHNICAL_SIGNAL = "TECHNICAL_SIGNAL"
    FUNDAMENTAL_SIGNAL = "FUNDAMENTAL_SIGNAL"


class FactorScore(BaseModel):
    """One factor's normalized (0-100) contribution for one asset —
    always inspectable, never a black-box number. `explanation` is
    optional free text a later phase's scoring logic can attach (e.g.
    "+11.4% over 15D, top decile of category") — Phase 1 never
    fabricates one; a factor computed without a human-readable reason
    simply omits it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    factor: RankingFactor
    value: float = Field(ge=0.0, le=100.0)
    explanation: str | None = None


class RankingWeights(BaseModel):
    """Configurable per-factor weights driving `WeightedRankingEngine` —
    mirrors the `ScoringWeights` precedent already established in
    `app.recommendations`/`app.risk`. A factor with no configured weight
    (or weight `0.0`) contributes nothing to the final score, but its
    `FactorScore` is still carried on `RankedAssetScore.factor_scores` for
    inspection — never silently dropped.
    """

    model_config = ConfigDict(extra="forbid")

    weights: dict[RankingFactor, float] = Field(default_factory=dict)

    def weight_for(self, factor: RankingFactor) -> float:
        return self.weights.get(factor, 0.0)


class RankedAssetScore(BaseModel):
    """One asset's final combined score and rank, with every contributing
    `FactorScore` still attached — the "no hidden weighting, every
    contribution inspectable" requirement, satisfied literally.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    ticker: str
    factor_scores: tuple[FactorScore, ...] = Field(default_factory=tuple)
    final_score: float = Field(ge=0.0, le=100.0)
    rank: int = Field(gt=0)
