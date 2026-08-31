"""WeightedRankingEngine — combines named `FactorScore`s into one final
score per asset, via a configurable `RankingWeights`, then ranks.

Contains no business knowledge of what any factor *means* or how it's
computed — that is each factor's own producer's job (a later phase's
performance/risk/liquidity computation). This engine only combines
already-computed, normalized (0-100) factor scores and orders the result.
Deliberately generic so future phases can introduce
`PRICE_PERFORMANCE`/`MOMENTUM`/... factor computation without ever
changing this class — the "extensible scoring/ranking architecture,
never a hardcoded final formula" requirement, made concrete.

Tie-breaking is deterministic and documented: equal final scores sort by
`ticker` ascending — never insertion order, never a random/unstable sort
— so re-ranking identical input always reproduces the identical output
order (a direct requirement: "the exact formula must be configurable and
auditable").
"""

from __future__ import annotations

from app.global_markets.ranking.models import FactorScore, RankedAssetScore, RankingWeights

__all__ = ["WeightedRankingEngine"]


class WeightedRankingEngine:
    """Ranks assets by a weighted combination of their `FactorScore`s."""

    def __init__(self, weights: RankingWeights) -> None:
        self._weights = weights

    def rank(self, asset_factor_scores: dict[str, tuple[FactorScore, ...]]) -> list[RankedAssetScore]:
        """Combine and rank every asset in `asset_factor_scores`.

        Args:
            asset_factor_scores: Ticker -> that asset's already-computed
                `FactorScore`s. An asset whose factors all carry zero
                configured weight (or that has no factors at all) still
                appears in the result, ranked last among ties, with
                `final_score=0.0` — never dropped silently.

        Returns:
            Every input asset, ranked 1..N by `final_score` descending,
            ties broken by `ticker` ascending.
        """
        scored: list[tuple[str, tuple[FactorScore, ...], float]] = []
        for ticker, factor_scores in asset_factor_scores.items():
            scored.append((ticker, factor_scores, self._combine(factor_scores)))

        scored.sort(key=lambda entry: (-entry[2], entry[0]))

        return [
            RankedAssetScore(ticker=ticker, factor_scores=factor_scores, final_score=final_score, rank=rank)
            for rank, (ticker, factor_scores, final_score) in enumerate(scored, start=1)
        ]

    def _combine(self, factor_scores: tuple[FactorScore, ...]) -> float:
        total_weight = sum(self._weights.weight_for(fs.factor) for fs in factor_scores)
        if total_weight <= 0:
            return 0.0
        weighted_sum = sum(fs.value * self._weights.weight_for(fs.factor) for fs in factor_scores)
        return round(weighted_sum / total_weight, 4)
