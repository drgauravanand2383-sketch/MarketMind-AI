"""Tests for PostgresRankedAssetRepository.

Run against an in-memory SQLite database via aiosqlite, exercising the
repository's own replace/list/health-check behavior directly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.global_markets.models import (
    DataFreshnessStatus,
    DataProvenance,
    NormalizedAssetSnapshot,
    PerformanceWindow,
    ReportCategory,
    WindowedPerformance,
)
from app.global_markets.ranked_asset import RankedAsset
from app.global_markets.ranking.classification import RiskClassification
from app.global_markets.ranking.models import FactorScore, RankingFactor
from app.repositories.global_markets.postgres.models import Base
from app.repositories.global_markets.postgres.ranked_asset_repository import PostgresRankedAssetRepository

NOW = datetime(2026, 8, 29, 3, 0, tzinfo=UTC)

_PROVENANCE = DataProvenance(
    source_timestamp=NOW, retrieved_at=NOW, provider="test-fixture", data_freshness_status=DataFreshnessStatus.LIVE
)


@pytest.fixture
async def repository() -> AsyncIterator[PostgresRankedAssetRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PostgresRankedAssetRepository(session_factory)
    finally:
        await engine.dispose()


def _snapshot(ticker: str, **overrides: object) -> NormalizedAssetSnapshot:
    defaults: dict[str, object] = {
        "ticker": ticker,
        "report_category": ReportCategory.US_EQUITY,
        "price": 100.0,
        "provenance": _PROVENANCE,
    }
    defaults.update(overrides)
    return NormalizedAssetSnapshot(**defaults)  # type: ignore[arg-type]


def _asset(
    ticker: str,
    rank: int,
    *,
    run_id: str = "run-1",
    category: ReportCategory = ReportCategory.US_EQUITY,
    **overrides: object,
) -> RankedAsset:
    defaults: dict[str, object] = {
        "run_id": run_id,
        "category": category,
        "rank": rank,
        "final_score": 100.0 - rank,
        "factor_scores": (FactorScore(factor=RankingFactor.PRICE_PERFORMANCE, value=75.0),),
        "snapshot": _snapshot(ticker, report_category=category),
    }
    defaults.update(overrides)
    return RankedAsset(**defaults)  # type: ignore[arg-type]


# --- replace_ranked_assets / list_ranked_assets -----------------------------------------------------------


async def test_replace_then_list_returns_the_stored_assets(repository: PostgresRankedAssetRepository) -> None:
    assets = (_asset("AAPL", 1), _asset("MSFT", 2))

    await repository.replace_ranked_assets("run-1", ReportCategory.US_EQUITY, assets)

    fetched = await repository.list_ranked_assets("run-1", ReportCategory.US_EQUITY)
    assert [a.snapshot.ticker for a in fetched] == ["AAPL", "MSFT"]


async def test_list_ranked_assets_orders_by_rank_ascending(repository: PostgresRankedAssetRepository) -> None:
    assets = (_asset("MSFT", 2), _asset("AAPL", 1))

    await repository.replace_ranked_assets("run-1", ReportCategory.US_EQUITY, assets)

    fetched = await repository.list_ranked_assets("run-1", ReportCategory.US_EQUITY)
    assert [a.rank for a in fetched] == [1, 2]


async def test_list_ranked_assets_empty_when_nothing_stored(repository: PostgresRankedAssetRepository) -> None:
    assert await repository.list_ranked_assets("run-1", ReportCategory.US_EQUITY) == []


async def test_factor_scores_and_snapshot_round_trip(repository: PostgresRankedAssetRepository) -> None:
    asset = _asset("AAPL", 1, snapshot=_snapshot("AAPL", market_cap=3_000_000_000.0, currency="USD"))

    await repository.replace_ranked_assets("run-1", ReportCategory.US_EQUITY, (asset,))

    fetched = (await repository.list_ranked_assets("run-1", ReportCategory.US_EQUITY))[0]
    assert fetched.snapshot.market_cap == 3_000_000_000.0
    assert fetched.snapshot.currency == "USD"
    assert fetched.factor_scores[0].factor is RankingFactor.PRICE_PERFORMANCE
    assert fetched.factor_scores[0].value == 75.0


def _window(period: PerformanceWindow, percent_change: float, *, is_complete: bool = True) -> WindowedPerformance:
    return WindowedPerformance(
        window=period,
        start_value=100.0,
        end_value=100.0 * (1 + percent_change / 100.0),
        percent_change=percent_change,
        observation_start=datetime(2021, 8, 29, tzinfo=UTC),
        observation_end=NOW,
        periods_used=1200,
        is_complete=is_complete,
    )


async def test_performance_windows_round_trip(repository: PostgresRankedAssetRepository) -> None:
    asset = _asset(
        "AAPL",
        1,
        performance_windows=(
            _window(PerformanceWindow.H24, 1.5),
            _window(PerformanceWindow.Y5, 240.0),
            _window(PerformanceWindow.Y3, 60.0, is_complete=False),
        ),
    )

    await repository.replace_ranked_assets("run-1", ReportCategory.US_EQUITY, (asset,))

    fetched = (await repository.list_ranked_assets("run-1", ReportCategory.US_EQUITY))[0]
    by_window = {w.window: w for w in fetched.performance_windows}
    assert by_window[PerformanceWindow.Y5].percent_change == 240.0
    assert by_window[PerformanceWindow.Y5].is_complete is True
    assert by_window[PerformanceWindow.Y3].is_complete is False
    assert by_window[PerformanceWindow.H24].observation_end == NOW


async def test_performance_windows_default_to_empty_when_not_provided(
    repository: PostgresRankedAssetRepository,
) -> None:
    await repository.replace_ranked_assets("run-1", ReportCategory.US_EQUITY, (_asset("AAPL", 1),))

    fetched = (await repository.list_ranked_assets("run-1", ReportCategory.US_EQUITY))[0]
    assert fetched.performance_windows == ()


async def test_risk_classification_round_trips_when_present(repository: PostgresRankedAssetRepository) -> None:
    asset = _asset(
        "PENNY",
        1,
        category=ReportCategory.US_PENNY_STOCK,
        risk_classification=RiskClassification.STRONG_MOMENTUM_HIGH_RISK,
        snapshot=_snapshot("PENNY", report_category=ReportCategory.US_PENNY_STOCK),
    )

    await repository.replace_ranked_assets("run-1", ReportCategory.US_PENNY_STOCK, (asset,))

    fetched = (await repository.list_ranked_assets("run-1", ReportCategory.US_PENNY_STOCK))[0]
    assert fetched.risk_classification is RiskClassification.STRONG_MOMENTUM_HIGH_RISK


async def test_risk_classification_is_none_when_not_set(repository: PostgresRankedAssetRepository) -> None:
    await repository.replace_ranked_assets("run-1", ReportCategory.US_EQUITY, (_asset("AAPL", 1),))

    fetched = (await repository.list_ranked_assets("run-1", ReportCategory.US_EQUITY))[0]
    assert fetched.risk_classification is None


# --- Idempotent replace: retry never duplicates or leaks -----------------------------------------------


async def test_replacing_a_category_removes_its_previous_rows(repository: PostgresRankedAssetRepository) -> None:
    await repository.replace_ranked_assets("run-1", ReportCategory.US_EQUITY, (_asset("AAPL", 1), _asset("MSFT", 2)))

    await repository.replace_ranked_assets("run-1", ReportCategory.US_EQUITY, (_asset("GOOG", 1),))

    fetched = await repository.list_ranked_assets("run-1", ReportCategory.US_EQUITY)
    assert [a.snapshot.ticker for a in fetched] == ["GOOG"]


async def test_replacing_one_category_does_not_touch_another_category(
    repository: PostgresRankedAssetRepository,
) -> None:
    await repository.replace_ranked_assets("run-1", ReportCategory.US_EQUITY, (_asset("AAPL", 1),))
    await repository.replace_ranked_assets(
        "run-1",
        ReportCategory.INDIA_EQUITY,
        (_asset("RELIANCE", 1, category=ReportCategory.INDIA_EQUITY, snapshot=_snapshot("RELIANCE")),),
    )

    await repository.replace_ranked_assets("run-1", ReportCategory.US_EQUITY, (_asset("MSFT", 1),))

    assert [a.snapshot.ticker for a in await repository.list_ranked_assets("run-1", ReportCategory.US_EQUITY)] == [
        "MSFT"
    ]
    assert [
        a.snapshot.ticker for a in await repository.list_ranked_assets("run-1", ReportCategory.INDIA_EQUITY)
    ] == ["RELIANCE"]


async def test_replacing_one_run_does_not_touch_another_run(repository: PostgresRankedAssetRepository) -> None:
    await repository.replace_ranked_assets("run-1", ReportCategory.US_EQUITY, (_asset("AAPL", 1),))
    await repository.replace_ranked_assets("run-2", ReportCategory.US_EQUITY, (_asset("MSFT", 1, run_id="run-2"),))

    assert [a.snapshot.ticker for a in await repository.list_ranked_assets("run-1", ReportCategory.US_EQUITY)] == [
        "AAPL"
    ]
    assert [a.snapshot.ticker for a in await repository.list_ranked_assets("run-2", ReportCategory.US_EQUITY)] == [
        "MSFT"
    ]


async def test_replace_with_an_empty_tuple_clears_the_category(repository: PostgresRankedAssetRepository) -> None:
    await repository.replace_ranked_assets("run-1", ReportCategory.US_EQUITY, (_asset("AAPL", 1),))

    await repository.replace_ranked_assets("run-1", ReportCategory.US_EQUITY, ())

    assert await repository.list_ranked_assets("run-1", ReportCategory.US_EQUITY) == []


async def test_replace_rejects_an_asset_whose_run_id_does_not_match(
    repository: PostgresRankedAssetRepository,
) -> None:
    mismatched = _asset("AAPL", 1, run_id="different-run")

    with pytest.raises(ValueError, match="does not match"):
        await repository.replace_ranked_assets("run-1", ReportCategory.US_EQUITY, (mismatched,))


async def test_replace_rejects_an_asset_whose_category_does_not_match(
    repository: PostgresRankedAssetRepository,
) -> None:
    mismatched = _asset("AAPL", 1, category=ReportCategory.INDIA_EQUITY)

    with pytest.raises(ValueError, match="does not match"):
        await repository.replace_ranked_assets("run-1", ReportCategory.US_EQUITY, (mismatched,))


# --- list_ranked_assets_for_run -----------------------------------------------------------


async def test_list_ranked_assets_for_run_spans_every_category(repository: PostgresRankedAssetRepository) -> None:
    await repository.replace_ranked_assets("run-1", ReportCategory.US_EQUITY, (_asset("AAPL", 1),))
    await repository.replace_ranked_assets(
        "run-1",
        ReportCategory.INDIA_EQUITY,
        (_asset("RELIANCE", 1, category=ReportCategory.INDIA_EQUITY, snapshot=_snapshot("RELIANCE")),),
    )

    fetched = await repository.list_ranked_assets_for_run("run-1")

    assert {a.snapshot.ticker for a in fetched} == {"AAPL", "RELIANCE"}


async def test_list_ranked_assets_for_run_excludes_other_runs(repository: PostgresRankedAssetRepository) -> None:
    await repository.replace_ranked_assets("run-1", ReportCategory.US_EQUITY, (_asset("AAPL", 1),))
    await repository.replace_ranked_assets("run-2", ReportCategory.US_EQUITY, (_asset("MSFT", 1, run_id="run-2"),))

    fetched = await repository.list_ranked_assets_for_run("run-1")

    assert [a.snapshot.ticker for a in fetched] == ["AAPL"]


# --- health_check -----------------------------------------------------------


async def test_health_check_true_against_reachable_database(repository: PostgresRankedAssetRepository) -> None:
    assert await repository.health_check() is True


async def test_health_check_false_when_database_unreachable() -> None:
    broken_engine = create_async_engine("sqlite+aiosqlite:///nonexistent/no/such/path.db")
    session_factory = async_sessionmaker(broken_engine, expire_on_commit=False)

    repository = PostgresRankedAssetRepository(session_factory)

    assert await repository.health_check() is False
