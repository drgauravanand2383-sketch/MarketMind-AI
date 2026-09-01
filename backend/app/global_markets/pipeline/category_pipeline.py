"""CategoryDataPipeline — the single-category deterministic pipeline:
fetch -> normalize -> compute performance -> score factors -> (optional)
eligibility filter -> rank -> truncate to top_n -> `RankedAsset`.

Deterministic and I/O-bounded only by the injected `MarketDataProvider` —
no LLM call, no reasoning, no fabricated data anywhere in this module
("AI is responsible for interpretation, not ranking or arithmetic" is
satisfied by construction — see `FactorScoringService`'s own docstring
for the same discipline this module composes). One ticker's fetch
failure is isolated and simply excluded from the category's batch — it
never aborts the rest of the category, mirroring
`GlobalMarketIntelligenceWorkflow._resolve_category`'s own per-category
isolation one level up.

Eligibility filtering and risk classification are both optional
(`eligibility_provider`/`classify_risk`) — the five main categories pass
neither; every penny/micro-cap category passes both (the workflow wires
a real, per-market `PennyStockEligibilityCriteria` via
`app.global_markets.eligibility.defaults.eligibility_provider_for_category`).
What's still missing is a populated screening universe: Phase 1
deliberately left every penny/micro-cap `DEFAULT_UNIVERSES` entry empty
rather than fabricate tickers (see that module's own docstring), so
today this pipeline simply has nothing to fetch for those categories and
correctly returns an empty result, not a failure.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from app.global_markets.eligibility.provider import PennyStockEligibilityProvider
from app.global_markets.models import (
    REPORT_CATEGORY_DEFINITIONS,
    AssetPerformanceProfile,
    DataFreshnessStatus,
    NormalizedAssetSnapshot,
    ReportCategory,
)
from app.global_markets.normalization.normalizer import MarketDataNormalizer
from app.global_markets.performance.engine import PerformanceCalculationService
from app.global_markets.ranked_asset import RankedAsset
from app.global_markets.ranking.classification import classify
from app.global_markets.ranking.engine import WeightedRankingEngine
from app.global_markets.ranking.factor_scoring import FactorScoringService
from app.global_markets.ranking.models import FactorScore, RankingFactor, RankingWeights
from app.global_markets.universe.models import UniverseEntry
from app.market_data.models import HistoricalPrice, Interval
from app.providers.market_data.provider import MarketDataProvider

__all__ = ["CategoryDataPipeline"]

_HISTORY_LOOKBACK_DAYS = 1900
"""Comfortably covers the longest performance window (5Y = 1826 days)
plus the year-shift-anchoring slack `PerformanceCalculationService`
needs: an anchor exactly 5 calendar years back may land on a weekend or
holiday, so the series must extend a little before it for the
"nearest bar at or before the anchor" snap to still be a real bar."""


def _default_now() -> datetime:
    return datetime.now(UTC)


class CategoryDataPipeline:
    """Runs the full deterministic data pipeline for one `ReportCategory`."""

    def __init__(self, provider: MarketDataProvider, *, now_fn: Callable[[], datetime] = _default_now) -> None:
        self._provider = provider
        self._now_fn = now_fn
        self._normalizer = MarketDataNormalizer()
        self._performance = PerformanceCalculationService()
        self._factor_scoring = FactorScoringService()

    async def run(
        self,
        run_id: str,
        category: ReportCategory,
        universe: tuple[UniverseEntry, ...],
        ranking_weights: RankingWeights,
        freshness_status: DataFreshnessStatus,
        *,
        eligibility_provider: PennyStockEligibilityProvider | None = None,
        classify_risk: bool = False,
    ) -> tuple[RankedAsset, ...]:
        """Fetch, score, and rank `universe`, returning at most `top_n`
        (per `REPORT_CATEGORY_DEFINITIONS[category]`) `RankedAsset`s.

        An empty `universe` (the current, honest state for every
        penny/micro-cap category) simply returns `()` — never an error.
        """
        definition = REPORT_CATEGORY_DEFINITIONS[category]
        now = self._now_fn()
        start = now.date() - timedelta(days=_HISTORY_LOOKBACK_DAYS)

        batch: dict[str, tuple[AssetPerformanceProfile, NormalizedAssetSnapshot, tuple[HistoricalPrice, ...]]] = {}
        for entry in universe:
            try:
                quote = await self._provider.get_quote(entry.ticker)
                history = await self._provider.get_price_history(
                    entry.ticker, Interval.ONE_DAY, start=start, end=now.date()
                )
            except Exception:  # noqa: BLE001 - one ticker's fetch failure must never abort the category
                continue

            snapshot = self._normalizer.normalize(
                quote=quote,
                report_category=category,
                provider_name=self._provider.provider_name(),
                history=history,
                freshness_status=freshness_status,
                retrieved_at=now,
            )

            if eligibility_provider is not None and not eligibility_provider.evaluate(snapshot).eligible:
                continue

            profile = self._performance.calculate(definition.market_region, history, snapshot.provenance)
            prices = tuple(sorted(history.prices, key=lambda price: price.date))
            batch[entry.ticker] = (profile, snapshot, prices)

        if not batch:
            return ()

        factor_scores = self._factor_scoring.score_batch(batch)
        ranked_scores = WeightedRankingEngine(ranking_weights).rank(factor_scores)

        ranked_assets: list[RankedAsset] = []
        for score in ranked_scores[: definition.top_n]:
            risk_classification = None
            if classify_risk:
                risk_classification = classify(
                    momentum_score=_factor_value(score.factor_scores, RankingFactor.MOMENTUM),
                    risk_score=_factor_value(score.factor_scores, RankingFactor.RISK),
                    data_confidence_score=_factor_value(score.factor_scores, RankingFactor.SOURCE_CONFIDENCE),
                )
            ranked_assets.append(
                RankedAsset(
                    run_id=run_id,
                    category=category,
                    rank=score.rank,
                    final_score=score.final_score,
                    factor_scores=score.factor_scores,
                    performance_windows=batch[score.ticker][0].windows,
                    snapshot=batch[score.ticker][1],
                    risk_classification=risk_classification,
                )
            )
        return tuple(ranked_assets)


def _factor_value(factor_scores: tuple[FactorScore, ...], factor: RankingFactor) -> float:
    return next(fs.value for fs in factor_scores if fs.factor is factor)
