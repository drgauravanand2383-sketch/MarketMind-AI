"""Tests for `FactorScoringService` (`app.global_markets.ranking.factor_scoring`)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.global_markets.models import (
    AssetPerformanceProfile,
    DataFreshnessStatus,
    DataProvenance,
    NormalizedAssetSnapshot,
    PerformanceWindow,
    ReportCategory,
    WindowedPerformance,
)
from app.global_markets.ranking.factor_scoring import FactorScoringService
from app.global_markets.ranking.models import RankingFactor
from app.market_data.models import HistoricalPrice

_PROVENANCE = DataProvenance(
    source_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
    provider="test-fixture",
    data_freshness_status=DataFreshnessStatus.LIVE,
)


def _window(
    period: PerformanceWindow, percent_change: float, *, days: int = 10, is_complete: bool = True
) -> WindowedPerformance:
    end = datetime(2026, 1, 30, tzinfo=UTC)
    return WindowedPerformance(
        window=period,
        start_value=100.0,
        end_value=100.0 * (1 + percent_change / 100.0),
        percent_change=percent_change,
        observation_start=end - timedelta(days=days),
        observation_end=end,
        periods_used=days,
        is_complete=is_complete,
    )


def _profile(ticker: str, windows: tuple[WindowedPerformance, ...]) -> AssetPerformanceProfile:
    return AssetPerformanceProfile(ticker=ticker, windows=windows, provenance=_PROVENANCE)


def _snapshot(ticker: str, **overrides: object) -> NormalizedAssetSnapshot:
    defaults: dict[str, object] = {
        "ticker": ticker,
        "report_category": ReportCategory.US_EQUITY,
        "price": 100.0,
        "avg_daily_volume": 1_000_000.0,
        "market_cap": 1_000_000_000.0,
        "provenance": _PROVENANCE,
    }
    defaults.update(overrides)
    return NormalizedAssetSnapshot(**defaults)  # type: ignore[arg-type]


def _flat_prices(count: int, start: float = 100.0) -> tuple[HistoricalPrice, ...]:
    """A perfectly flat (zero-volatility) daily series."""
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return tuple(
        HistoricalPrice(
            date=base + timedelta(days=i), open=start, high=start + 1.0, low=start, close=start, volume=1000
        )
        for i in range(count)
    )


def _volatile_prices(count: int, seed_amplitude: float = 20.0) -> tuple[HistoricalPrice, ...]:
    """A series that swings sharply day to day — deliberately high volatility."""
    base = datetime(2026, 1, 1, tzinfo=UTC)
    prices = []
    for i in range(count):
        close = 100.0 + (seed_amplitude if i % 2 == 0 else -seed_amplitude / 2)
        prices.append(
            HistoricalPrice(
                date=base + timedelta(days=i),
                open=close,
                high=close + 1.0,
                low=max(close - 1.0, 0.1),
                close=close,
                volume=1000,
            )
        )
    return tuple(prices)


def _factor(scores: tuple, factor: RankingFactor) -> float:
    return next(s.value for s in scores if s.factor is factor)


# --- Price performance -----------------------------------------------------------


def test_higher_multi_window_performance_scores_higher() -> None:
    service = FactorScoringService()
    assets = {
        "LOW": (
            _profile("LOW", (_window(PerformanceWindow.D10, 1.0), _window(PerformanceWindow.M1, 1.0))),
            _snapshot("LOW"),
            _flat_prices(30),
        ),
        "HIGH": (
            _profile("HIGH", (_window(PerformanceWindow.D10, 20.0), _window(PerformanceWindow.M1, 20.0))),
            _snapshot("HIGH"),
            _flat_prices(30),
        ),
    }

    scores = service.score_batch(assets)

    assert _factor(scores["HIGH"], RankingFactor.PRICE_PERFORMANCE) > _factor(
        scores["LOW"], RankingFactor.PRICE_PERFORMANCE
    )


def test_price_performance_includes_the_shortest_new_windows() -> None:
    """24H/1W joined the recent-focused cluster alongside 10D/15D/1M."""
    service = FactorScoringService()
    assets = {
        "LOW": (
            _profile("LOW", (_window(PerformanceWindow.H24, 1.0), _window(PerformanceWindow.W1, 1.0))),
            _snapshot("LOW"),
            _flat_prices(30),
        ),
        "HIGH": (
            _profile("HIGH", (_window(PerformanceWindow.H24, 20.0), _window(PerformanceWindow.W1, 20.0))),
            _snapshot("HIGH"),
            _flat_prices(30),
        ),
    }

    scores = service.score_batch(assets)

    assert _factor(scores["HIGH"], RankingFactor.PRICE_PERFORMANCE) > _factor(
        scores["LOW"], RankingFactor.PRICE_PERFORMANCE
    )


def test_price_performance_ignores_multi_year_windows() -> None:
    """3Y/5Y are reported for display (a stock's long-term track record)
    but must not move the recent-focused Top-N price score — the ranking
    stays recent-focused by explicit product decision."""
    service = FactorScoringService()
    assets = {
        "ONLY_LONG_TERM": (
            # A spectacular 3Y/5Y return, but nothing in the recent-focused
            # cluster (24H/1W/10D/15D/1M).
            _profile(
                "ONLY_LONG_TERM",
                (_window(PerformanceWindow.Y3, 500.0), _window(PerformanceWindow.Y5, 900.0)),
            ),
            _snapshot("ONLY_LONG_TERM"),
            _flat_prices(30),
        ),
        "RECENT_MOVER": (
            _profile("RECENT_MOVER", (_window(PerformanceWindow.D10, 5.0),)),
            _snapshot("RECENT_MOVER"),
            _flat_prices(30),
        ),
    }

    scores = service.score_batch(assets)

    # ONLY_LONG_TERM has no window in the price-score cluster, so it scores
    # 0.0 (missing data is never guessed as average) despite its 3Y/5Y
    # numbers -- proof that a spectacular multi-year return alone cannot
    # buy a higher recent price-performance score.
    assert _factor(scores["ONLY_LONG_TERM"], RankingFactor.PRICE_PERFORMANCE) == 0.0
    assert _factor(scores["RECENT_MOVER"], RankingFactor.PRICE_PERFORMANCE) > 0.0


def test_missing_performance_windows_score_zero_not_average() -> None:
    service = FactorScoringService()
    assets = {
        "HAS_DATA": (
            _profile("HAS_DATA", (_window(PerformanceWindow.D10, 10.0),)),
            _snapshot("HAS_DATA"),
            _flat_prices(30),
        ),
        "NO_DATA": (_profile("NO_DATA", ()), _snapshot("NO_DATA"), _flat_prices(30)),
    }

    scores = service.score_batch(assets)

    assert _factor(scores["NO_DATA"], RankingFactor.PRICE_PERFORMANCE) == 0.0


# --- Momentum: acceleration vs deceleration -----------------------------------------------------------


def test_recent_acceleration_scores_higher_momentum_than_deceleration() -> None:
    service = FactorScoringService()
    # ACCELERATING: fast very-recent pace (24H) vs slow week-long pace (1W).
    accelerating = _profile(
        "ACCEL",
        (
            _window(PerformanceWindow.H24, 1.0, days=1),  # 1.0%/day recently
            _window(PerformanceWindow.W1, 0.7, days=7),  # 0.1%/day over the week
        ),
    )
    # DECELERATING: slow very-recent pace vs fast week-long pace.
    decelerating = _profile(
        "DECEL",
        (
            _window(PerformanceWindow.H24, 0.1, days=1),  # 0.1%/day recently
            _window(PerformanceWindow.W1, 7.0, days=7),  # 1.0%/day over the week
        ),
    )
    assets = {
        "ACCEL": (accelerating, _snapshot("ACCEL"), _flat_prices(30)),
        "DECEL": (decelerating, _snapshot("DECEL"), _flat_prices(30)),
    }

    scores = service.score_batch(assets)

    assert _factor(scores["ACCEL"], RankingFactor.MOMENTUM) > _factor(scores["DECEL"], RankingFactor.MOMENTUM)


# --- Liquidity -----------------------------------------------------------


def test_higher_traded_value_scores_higher_liquidity() -> None:
    service = FactorScoringService()
    assets = {
        "THIN": (
            _profile("THIN", ()),
            _snapshot("THIN", avg_daily_traded_value=1_000.0),
            _flat_prices(30),
        ),
        "DEEP": (
            _profile("DEEP", ()),
            _snapshot("DEEP", avg_daily_traded_value=100_000_000.0),
            _flat_prices(30),
        ),
    }

    scores = service.score_batch(assets)

    assert _factor(scores["DEEP"], RankingFactor.VOLUME_LIQUIDITY) > _factor(
        scores["THIN"], RankingFactor.VOLUME_LIQUIDITY
    )


# --- Risk (inverted: higher score = lower risk) -----------------------------------------------------------


def test_flat_series_scores_higher_risk_safety_than_volatile_series() -> None:
    service = FactorScoringService()
    assets = {
        "STABLE": (_profile("STABLE", ()), _snapshot("STABLE"), _flat_prices(60)),
        "VOLATILE": (_profile("VOLATILE", ()), _snapshot("VOLATILE"), _volatile_prices(60)),
    }

    scores = service.score_batch(assets)

    assert _factor(scores["STABLE"], RankingFactor.RISK) > _factor(scores["VOLATILE"], RankingFactor.RISK)


# --- Data confidence -----------------------------------------------------------


def test_more_complete_windows_and_fields_scores_higher_confidence() -> None:
    service = FactorScoringService()
    complete_profile = _profile(
        "COMPLETE",
        tuple(_window(w, 5.0, is_complete=True) for w in PerformanceWindow),
    )
    sparse_profile = _profile("SPARSE", (_window(PerformanceWindow.D10, 5.0, is_complete=False),))
    assets = {
        "COMPLETE": (complete_profile, _snapshot("COMPLETE"), _flat_prices(30)),
        "SPARSE": (sparse_profile, _snapshot("SPARSE", avg_daily_volume=None, market_cap=None), _flat_prices(30)),
    }

    scores = service.score_batch(assets)

    assert _factor(scores["COMPLETE"], RankingFactor.SOURCE_CONFIDENCE) > _factor(
        scores["SPARSE"], RankingFactor.SOURCE_CONFIDENCE
    )


# --- Batch shape -----------------------------------------------------------


def test_every_asset_gets_exactly_five_factor_scores() -> None:
    service = FactorScoringService()
    assets = {"A": (_profile("A", ()), _snapshot("A"), _flat_prices(30))}

    scores = service.score_batch(assets)

    assert len(scores["A"]) == 5
    assert {s.factor for s in scores["A"]} == {
        RankingFactor.PRICE_PERFORMANCE,
        RankingFactor.MOMENTUM,
        RankingFactor.VOLUME_LIQUIDITY,
        RankingFactor.RISK,
        RankingFactor.SOURCE_CONFIDENCE,
    }
