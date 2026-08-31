"""Default `RankingWeights` — configurable starting points, never
hardcoded into either ranking engine itself (both engines accept weights
as an injected dependency; these are just the values `app.bootstrap`
wires in by default).

Main categories weight `PRICE_PERFORMANCE` directly (multi-window return
is a legitimate signal once combined with momentum/liquidity/risk/
confidence — the explicit requirement is "not simply the biggest one-day
gain," not "performance is irrelevant"). Penny/micro-cap categories
deliberately carry **no** `PRICE_PERFORMANCE` weight at all — the
explicit product requirement ("must NOT simply rank by percentage
return") is enforced structurally here, not just by convention.
"""

from __future__ import annotations

from app.global_markets.ranking.models import RankingFactor, RankingWeights

__all__ = ["DEFAULT_MAIN_RANKING_WEIGHTS", "DEFAULT_PENNY_MICROCAP_RANKING_WEIGHTS"]

DEFAULT_MAIN_RANKING_WEIGHTS = RankingWeights(
    weights={
        RankingFactor.PRICE_PERFORMANCE: 0.35,
        RankingFactor.MOMENTUM: 0.20,
        RankingFactor.VOLUME_LIQUIDITY: 0.15,
        RankingFactor.RISK: 0.15,
        RankingFactor.SOURCE_CONFIDENCE: 0.15,
    }
)

DEFAULT_PENNY_MICROCAP_RANKING_WEIGHTS = RankingWeights(
    weights={
        RankingFactor.MOMENTUM: 0.35,
        RankingFactor.VOLUME_LIQUIDITY: 0.25,
        RankingFactor.RISK: 0.20,
        RankingFactor.SOURCE_CONFIDENCE: 0.20,
    }
)
