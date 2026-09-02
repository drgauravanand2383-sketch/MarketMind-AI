"""Tests for `CategoryDataPipeline` (`app.global_markets.pipeline.category_pipeline`)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.global_markets.eligibility.models import EligibilityCheckResult, PennyStockMarket
from app.global_markets.eligibility.provider import PennyStockEligibilityProvider
from app.global_markets.models import (
    DataFreshnessStatus,
    NormalizedAssetSnapshot,
    PerformanceWindow,
    ReportCategory,
)
from app.global_markets.pipeline.category_pipeline import CategoryDataPipeline
from app.global_markets.ranking.defaults import DEFAULT_MAIN_RANKING_WEIGHTS, DEFAULT_PENNY_MICROCAP_RANKING_WEIGHTS
from app.global_markets.universe.models import UniverseEntry
from app.market_data.models import HistoricalSeries, Interval, MarketQuote
from app.providers.market_data.mock import MockMarketDataProvider

_NOW = datetime(2026, 8, 29, 3, 0, tzinfo=UTC)


def _now_fn() -> datetime:
    return _NOW


def _universe(*tickers: str) -> tuple[UniverseEntry, ...]:
    return tuple(UniverseEntry(ticker=ticker, name=ticker) for ticker in tickers)


class _RejectAllEligibilityProvider(PennyStockEligibilityProvider):
    def evaluate(self, snapshot: NormalizedAssetSnapshot) -> EligibilityCheckResult:
        return EligibilityCheckResult(
            ticker=snapshot.ticker,
            market=PennyStockMarket.US,
            eligible=False,
            failed_reasons=("rejected for test",),
            data_completeness_ratio=1.0,
        )


class _AcceptAllEligibilityProvider(PennyStockEligibilityProvider):
    def evaluate(self, snapshot: NormalizedAssetSnapshot) -> EligibilityCheckResult:
        return EligibilityCheckResult(
            ticker=snapshot.ticker,
            market=PennyStockMarket.US,
            eligible=True,
            failed_reasons=(),
            data_completeness_ratio=1.0,
        )


class _RecordsHistoryStartProvider(MockMarketDataProvider):
    """Wraps the deterministic mock, recording the `start` date every
    `get_price_history` call was made with."""

    def __init__(self) -> None:
        super().__init__()
        self.history_starts: list[date] = []

    async def get_price_history(
        self,
        ticker: str,
        interval: Interval,
        start: date | None = None,
        end: date | None = None,
    ) -> HistoricalSeries:
        if start is not None:
            self.history_starts.append(start)
        return await super().get_price_history(ticker, interval, start=start, end=end)


class _OneTickerFailsProvider(MockMarketDataProvider):
    """Wraps the deterministic mock, raising for one configured ticker."""

    def __init__(self, failing_ticker: str) -> None:
        super().__init__()
        self._failing_ticker = failing_ticker

    async def get_quote(self, ticker: str) -> MarketQuote:
        if ticker == self._failing_ticker:
            raise RuntimeError("simulated provider failure")
        return await super().get_quote(ticker)


# --- Empty universe -----------------------------------------------------------


async def test_empty_universe_returns_no_ranked_assets() -> None:
    pipeline = CategoryDataPipeline(MockMarketDataProvider(), now_fn=_now_fn)

    result = await pipeline.run(
        "run-1", ReportCategory.US_EQUITY, (), DEFAULT_MAIN_RANKING_WEIGHTS, DataFreshnessStatus.LIVE
    )

    assert result == ()


# --- Basic ranking shape -----------------------------------------------------------


async def test_ranks_a_universe_and_respects_top_n() -> None:
    pipeline = CategoryDataPipeline(MockMarketDataProvider(), now_fn=_now_fn)
    universe = _universe("AAPL", "MSFT", "GOOG")

    result = await pipeline.run(
        "run-1", ReportCategory.US_EQUITY, universe, DEFAULT_MAIN_RANKING_WEIGHTS, DataFreshnessStatus.LIVE
    )

    assert 0 < len(result) <= 3
    assert [asset.rank for asset in result] == list(range(1, len(result) + 1))


async def test_ranked_assets_carry_their_full_performance_window_set() -> None:
    """The windowed returns the ranking consumed are persisted on the
    result, not discarded — this is what lets the UI show a 3Y/5Y track
    record next to each pick."""
    provider = _RecordsHistoryStartProvider()
    pipeline = CategoryDataPipeline(provider, now_fn=_now_fn)

    result = await pipeline.run(
        "run-1",
        ReportCategory.US_EQUITY,
        _universe("AAPL"),
        DEFAULT_MAIN_RANKING_WEIGHTS,
        DataFreshnessStatus.LIVE,
    )

    assert result
    windows = {w.window for w in result[0].performance_windows}
    assert PerformanceWindow.Y5 in windows
    assert PerformanceWindow.H24 in windows


async def test_every_ranked_asset_carries_the_run_id_and_category() -> None:
    pipeline = CategoryDataPipeline(MockMarketDataProvider(), now_fn=_now_fn)
    universe = _universe("AAPL")

    result = await pipeline.run(
        "run-42", ReportCategory.US_EQUITY, universe, DEFAULT_MAIN_RANKING_WEIGHTS, DataFreshnessStatus.LIVE
    )

    assert all(asset.run_id == "run-42" for asset in result)
    assert all(asset.category is ReportCategory.US_EQUITY for asset in result)


async def test_top_n_truncates_a_larger_universe() -> None:
    pipeline = CategoryDataPipeline(MockMarketDataProvider(), now_fn=_now_fn)
    # INDIA_PENNY_STOCK's top_n is 20; feed it more than that to exercise truncation
    # against a real (small) top_n instead of US_EQUITY's 15.
    universe = _universe(*[f"T{i}" for i in range(25)])

    result = await pipeline.run(
        "run-1",
        ReportCategory.INDIA_PENNY_STOCK,
        universe,
        DEFAULT_PENNY_MICROCAP_RANKING_WEIGHTS,
        DataFreshnessStatus.LIVE,
    )

    assert len(result) <= 20


# --- History lookback -----------------------------------------------------------


async def test_pipeline_requests_at_least_five_years_of_daily_history() -> None:
    """The 3Y/5Y performance windows can only complete if the pipeline
    actually asks the provider for that much history."""
    provider = _RecordsHistoryStartProvider()
    pipeline = CategoryDataPipeline(provider, now_fn=_now_fn)

    await pipeline.run(
        "run-1",
        ReportCategory.US_EQUITY,
        _universe("AAPL"),
        DEFAULT_MAIN_RANKING_WEIGHTS,
        DataFreshnessStatus.LIVE,
    )

    assert provider.history_starts
    span_days = (_NOW.date() - provider.history_starts[0]).days
    assert span_days >= 5 * 365


# --- Per-ticker fetch failure isolation -----------------------------------------------------------


async def test_one_ticker_fetch_failure_does_not_abort_the_category() -> None:
    pipeline = CategoryDataPipeline(_OneTickerFailsProvider("MSFT"), now_fn=_now_fn)
    universe = _universe("AAPL", "MSFT", "GOOG")

    result = await pipeline.run(
        "run-1", ReportCategory.US_EQUITY, universe, DEFAULT_MAIN_RANKING_WEIGHTS, DataFreshnessStatus.LIVE
    )

    tickers = {asset.snapshot.ticker for asset in result}
    assert "MSFT" not in tickers
    assert tickers == {"AAPL", "GOOG"}


async def test_every_ticker_failing_returns_an_empty_result() -> None:
    class _AlwaysFailsProvider(MockMarketDataProvider):
        async def get_quote(self, ticker: str) -> MarketQuote:
            raise RuntimeError("simulated total outage")

    pipeline = CategoryDataPipeline(_AlwaysFailsProvider(), now_fn=_now_fn)

    result = await pipeline.run(
        "run-1", ReportCategory.US_EQUITY, _universe("AAPL"), DEFAULT_MAIN_RANKING_WEIGHTS, DataFreshnessStatus.LIVE
    )

    assert result == ()


# --- Eligibility filtering -----------------------------------------------------------


async def test_eligibility_provider_rejecting_everything_yields_no_ranked_assets() -> None:
    pipeline = CategoryDataPipeline(MockMarketDataProvider(), now_fn=_now_fn)

    result = await pipeline.run(
        "run-1",
        ReportCategory.US_PENNY_STOCK,
        _universe("AAPL", "MSFT"),
        DEFAULT_PENNY_MICROCAP_RANKING_WEIGHTS,
        DataFreshnessStatus.LIVE,
        eligibility_provider=_RejectAllEligibilityProvider(),
    )

    assert result == ()


async def test_eligibility_provider_accepting_everything_behaves_like_no_filter() -> None:
    pipeline = CategoryDataPipeline(MockMarketDataProvider(), now_fn=_now_fn)
    universe = _universe("AAPL", "MSFT")

    without_filter = await pipeline.run(
        "run-1", ReportCategory.US_PENNY_STOCK, universe, DEFAULT_PENNY_MICROCAP_RANKING_WEIGHTS,
        DataFreshnessStatus.LIVE,
    )
    with_accept_all = await pipeline.run(
        "run-1",
        ReportCategory.US_PENNY_STOCK,
        universe,
        DEFAULT_PENNY_MICROCAP_RANKING_WEIGHTS,
        DataFreshnessStatus.LIVE,
        eligibility_provider=_AcceptAllEligibilityProvider(),
    )

    assert len(without_filter) == len(with_accept_all)


# --- Risk classification -----------------------------------------------------------


async def test_classify_risk_false_leaves_risk_classification_none() -> None:
    pipeline = CategoryDataPipeline(MockMarketDataProvider(), now_fn=_now_fn)

    result = await pipeline.run(
        "run-1", ReportCategory.US_EQUITY, _universe("AAPL"), DEFAULT_MAIN_RANKING_WEIGHTS, DataFreshnessStatus.LIVE
    )

    assert all(asset.risk_classification is None for asset in result)


async def test_classify_risk_true_populates_risk_classification() -> None:
    pipeline = CategoryDataPipeline(MockMarketDataProvider(), now_fn=_now_fn)

    result = await pipeline.run(
        "run-1",
        ReportCategory.US_PENNY_STOCK,
        _universe("AAPL"),
        DEFAULT_PENNY_MICROCAP_RANKING_WEIGHTS,
        DataFreshnessStatus.LIVE,
        classify_risk=True,
    )

    assert all(asset.risk_classification is not None for asset in result)


# --- Provenance/freshness passthrough -----------------------------------------------------------


async def test_freshness_status_is_carried_onto_every_snapshot() -> None:
    pipeline = CategoryDataPipeline(MockMarketDataProvider(), now_fn=_now_fn)

    result = await pipeline.run(
        "run-1",
        ReportCategory.US_EQUITY,
        _universe("AAPL"),
        DEFAULT_MAIN_RANKING_WEIGHTS,
        DataFreshnessStatus.PREVIOUS_CLOSE,
    )

    assert all(
        asset.snapshot.provenance.data_freshness_status is DataFreshnessStatus.PREVIOUS_CLOSE for asset in result
    )
