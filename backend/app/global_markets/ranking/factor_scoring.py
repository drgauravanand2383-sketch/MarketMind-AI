"""FactorScoringService — computes the named `FactorScore`s
`WeightedRankingEngine` combines, from already-fetched/computed data only.

Every factor is **cross-sectionally normalized**: scaled 0-100 relative
to the other assets in the same ranking run, never against a fixed
absolute threshold. There is no single universal scale for "good
momentum" or "good liquidity" that applies identically across India
equities, forex pairs, and crypto — only relative-to-peers-in-this-batch
is meaningful, which is also exactly what a "Top N" selection needs.

A factor a given asset has no usable data for scores `0.0` for that one
factor (never guessed as "average") — `SOURCE_CONFIDENCE` separately and
honestly reflects how much of the full picture was actually available,
so a low score is never silently indistinguishable from "genuinely
weak."

This module performs arithmetic only — no reasoning, no narrative, no
LLM call. "AI is responsible for interpretation, not ranking or
arithmetic" (explicit product requirement) is satisfied by construction:
nothing here can be an agent, because nothing here is non-deterministic.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping

from app.global_markets.models import AssetPerformanceProfile, NormalizedAssetSnapshot, PerformanceWindow
from app.global_markets.ranking.models import FactorScore, RankingFactor
from app.market_data.models import HistoricalPrice

__all__ = ["FactorScoringService"]

_PERFORMANCE_WINDOWS_FOR_PRICE_SCORE = (
    PerformanceWindow.H24,
    PerformanceWindow.W1,
    PerformanceWindow.D10,
    PerformanceWindow.D15,
    PerformanceWindow.M1,
)
"""Deliberately still the sub-monthly cluster — recent-focused ranking,
unchanged in kind from before the 24H/1W/3Y/5Y windows existed. 3Y/5Y are
reported (see `AssetPerformanceProfile`) so a stock's multi-year track
record is visible, but this batch's Top-N selection is not re-weighted
toward them."""
_MOMENTUM_SHORT_WINDOW = PerformanceWindow.H24
_MOMENTUM_LONG_WINDOW = PerformanceWindow.W1
_ALL_WINDOWS = tuple(PerformanceWindow)


class FactorScoringService:
    """Computes cross-sectionally normalized `FactorScore`s for a batch of assets."""

    def score_batch(
        self,
        assets: dict[str, tuple[AssetPerformanceProfile, NormalizedAssetSnapshot, tuple[HistoricalPrice, ...]]],
    ) -> dict[str, tuple[FactorScore, ...]]:
        """Score every asset in `assets` relative to the others in the same batch.

        Args:
            assets: ticker -> (performance profile, normalized snapshot,
                the raw sorted-ascending price history that produced the
                profile — needed for volatility, which no
                `WindowedPerformance` alone carries).
        """
        price_perf_raw = {
            ticker: self._blended_price_performance(profile) for ticker, (profile, _, _) in assets.items()
        }
        momentum_raw = {ticker: self._momentum(profile) for ticker, (profile, _, _) in assets.items()}
        liquidity_raw = {ticker: self._liquidity(snapshot) for ticker, (_, snapshot, _) in assets.items()}
        volatility_raw = {ticker: self._volatility(prices) for ticker, (_, _, prices) in assets.items()}
        confidence_raw = {
            ticker: self._data_completeness(profile, snapshot) for ticker, (profile, snapshot, _) in assets.items()
        }

        price_perf_scaled = _minmax_scale(price_perf_raw)
        momentum_scaled = _minmax_scale(momentum_raw)
        liquidity_scaled = _minmax_scale(liquidity_raw)
        risk_scaled = _minmax_scale(volatility_raw, invert=True)  # lower volatility -> higher (better) score
        confidence_scaled = _minmax_scale(confidence_raw)

        return {
            ticker: (
                FactorScore(factor=RankingFactor.PRICE_PERFORMANCE, value=price_perf_scaled[ticker]),
                FactorScore(factor=RankingFactor.MOMENTUM, value=momentum_scaled[ticker]),
                FactorScore(factor=RankingFactor.VOLUME_LIQUIDITY, value=liquidity_scaled[ticker]),
                FactorScore(factor=RankingFactor.RISK, value=risk_scaled[ticker]),
                FactorScore(factor=RankingFactor.SOURCE_CONFIDENCE, value=confidence_scaled[ticker]),
            )
            for ticker in assets
        }

    @staticmethod
    def _blended_price_performance(profile: AssetPerformanceProfile) -> float | None:
        """Average `percent_change` across the recent-focused windows
        (24H/1W/10D/15D/1M) that actually completed — "multi-window
        performance," not a single one-day gain."""
        values = [
            window.percent_change
            for window in profile.windows
            if window.window in _PERFORMANCE_WINDOWS_FOR_PRICE_SCORE and window.is_complete
        ]
        return sum(values) / len(values) if values else None

    @staticmethod
    def _momentum(profile: AssetPerformanceProfile) -> float | None:
        """Recent daily pace of change vs. the longer-term daily pace —
        positive means accelerating, negative means decelerating (the
        explicit "price acceleration/deceleration" requirement)."""
        short = profile.window(_MOMENTUM_SHORT_WINDOW)
        long = profile.window(_MOMENTUM_LONG_WINDOW)
        if short is None or long is None or not short.is_complete or not long.is_complete:
            return None
        short_days = (short.observation_end - short.observation_start).days
        long_days = (long.observation_end - long.observation_start).days
        if short_days <= 0 or long_days <= 0:
            return None
        return (short.percent_change / short_days) - (long.percent_change / long_days)

    @staticmethod
    def _liquidity(snapshot: NormalizedAssetSnapshot) -> float | None:
        """Log-scaled average daily traded value (preferred) or volume —
        log-scaling keeps one very large-cap asset from making every
        other asset's liquidity look like zero by comparison."""
        raw = snapshot.avg_daily_traded_value
        if raw is None and snapshot.avg_daily_volume is not None and snapshot.price is not None:
            raw = snapshot.avg_daily_volume * snapshot.price
        if raw is None or raw <= 0:
            return None
        return math.log1p(raw)

    @staticmethod
    def _volatility(prices: tuple[HistoricalPrice, ...]) -> float | None:
        """Raw (non-annualized) standard deviation of daily log returns
        over the supplied history — a relative-within-this-batch risk
        proxy only; deliberately not annualized, since equities/forex/
        crypto have genuinely different trading-day conventions (see
        `app.global_markets.performance.engine`'s own docstring) and this
        module never presents volatility as a standalone absolute figure,
        only as one cross-sectionally scaled ranking factor."""
        if len(prices) < 3:
            return None
        returns = [
            math.log(prices[i].close / prices[i - 1].close)
            for i in range(1, len(prices))
            if prices[i - 1].close > 0
        ]
        if len(returns) < 2:
            return None
        return statistics.pstdev(returns)

    @staticmethod
    def _data_completeness(profile: AssetPerformanceProfile, snapshot: NormalizedAssetSnapshot) -> float:
        """The fraction of the (now 10) performance windows that fully
        completed, blended with whether core snapshot fields were present
        at all — always computable (never `None`), since "how much do we
        actually know" is itself always knowable. A newly-listed asset or
        one on a low-history provider will legitimately never complete
        the 3Y/5Y windows; that honestly lowers this score rather than
        being silently excluded from the denominator."""
        complete_windows = sum(1 for window in profile.windows if window.is_complete)
        window_ratio = complete_windows / len(_ALL_WINDOWS)
        core_fields = (snapshot.price, snapshot.avg_daily_volume, snapshot.market_cap)
        field_ratio = sum(1 for field in core_fields if field is not None) / len(core_fields)
        return (window_ratio + field_ratio) / 2.0


def _minmax_scale(raw_values: Mapping[str, float | None], *, invert: bool = False) -> dict[str, float]:
    """Cross-sectional min-max scaling to `[0, 100]`. A ticker with `None`
    scores `0.0` for this factor (missing data is never rewarded); every
    ticker scores `50.0` when every present value is identical (no
    meaningful spread to rank by) or when nothing in the batch has data
    for this factor at all."""
    present = {ticker: value for ticker, value in raw_values.items() if value is not None}
    if not present:
        return {ticker: 50.0 for ticker in raw_values}

    lowest, highest = min(present.values()), max(present.values())
    scaled: dict[str, float] = {}
    for ticker, value in raw_values.items():
        if value is None:
            scaled[ticker] = 0.0
            continue
        if highest == lowest:
            scaled[ticker] = 50.0
            continue
        percentile = (value - lowest) / (highest - lowest) * 100.0
        scaled[ticker] = round((100.0 - percentile) if invert else percentile, 4)
    return scaled
