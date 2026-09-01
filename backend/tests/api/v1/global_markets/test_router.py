"""End-to-end tests for the Global Market Intelligence API (`/api/v1/global-markets`)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi.testclient import TestClient

from app.global_markets.intelligence_report import CategoryIntelligenceReport
from app.global_markets.models import (
    DataFreshnessStatus,
    DataProvenance,
    IntelligenceRun,
    IntelligenceRunStatus,
    NormalizedAssetSnapshot,
    PerformanceWindow,
    ReportCategory,
    WindowedPerformance,
)
from app.global_markets.ranked_asset import RankedAsset
from app.repositories.global_markets.postgres.ranked_asset_repository import PostgresRankedAssetRepository
from app.repositories.global_markets.postgres.report_repository import PostgresIntelligenceReportRepository
from app.repositories.global_markets.postgres.repository import PostgresGlobalMarketRunRepository
from tests.api.v1._auth_fixtures import make_authenticated_headers

_NOW = datetime(2026, 8, 31, 9, 0, tzinfo=UTC)
_PROVENANCE = DataProvenance(
    source_timestamp=_NOW, retrieved_at=_NOW, provider="test-fixture", data_freshness_status=DataFreshnessStatus.LIVE
)


def _run(run_id: str, run_date: date, **overrides: object) -> IntelligenceRun:
    defaults: dict[str, object] = {
        "id": run_id,
        "run_date": run_date,
        "status": IntelligenceRunStatus.COMPLETED,
        "triggered_by": "scheduler",
        "started_at": _NOW,
    }
    defaults.update(overrides)
    return IntelligenceRun(**defaults)  # type: ignore[arg-type]


def _ranked_asset(
    run_id: str, category: ReportCategory, ticker: str, rank: int, **overrides: object
) -> RankedAsset:
    defaults: dict[str, object] = {
        "run_id": run_id,
        "category": category,
        "rank": rank,
        "final_score": 100.0 - rank,
        "snapshot": NormalizedAssetSnapshot(
            ticker=ticker, report_category=category, price=100.0, provenance=_PROVENANCE
        ),
    }
    defaults.update(overrides)
    return RankedAsset(**defaults)  # type: ignore[arg-type]


def _report(run_id: str, category: ReportCategory, **overrides: object) -> CategoryIntelligenceReport:
    defaults: dict[str, object] = {
        "run_id": run_id,
        "category": category,
        "generated_at": _NOW,
        "overall_summary": "A quiet session overall.",
        "provider": "anthropic",
        "model": "claude-sonnet-5",
    }
    defaults.update(overrides)
    return CategoryIntelligenceReport(**defaults)  # type: ignore[arg-type]


# --- Auth -----------------------------------------------------------


def test_list_runs_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/global-markets/runs")
    assert response.status_code == 401


async def test_list_runs_requires_read_permission(client: TestClient, auth_repository, auth_service) -> None:
    headers = await make_authenticated_headers(auth_repository, auth_service, permissions=("some_other:read",))
    response = client.get("/api/v1/global-markets/runs", headers=headers)
    assert response.status_code == 403


# --- /categories -----------------------------------------------------------


def test_list_categories_returns_all_nine(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/api/v1/global-markets/categories", headers=auth_headers)
    assert response.status_code == 200
    categories = response.json()["data"]
    assert len(categories) == 9
    assert {c["category"] for c in categories} == {c.value for c in ReportCategory}


# --- /runs -----------------------------------------------------------


async def test_list_runs_empty_initially(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/api/v1/global-markets/runs", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["total"] == 0


async def test_list_runs_orders_most_recent_first(
    client: TestClient, auth_headers: dict[str, str], global_market_run_repository: PostgresGlobalMarketRunRepository
) -> None:
    await global_market_run_repository.create_run(_run("run-1", date(2026, 8, 27)))
    await global_market_run_repository.create_run(_run("run-2", date(2026, 8, 29)))

    response = client.get("/api/v1/global-markets/runs", headers=auth_headers)

    assert response.status_code == 200
    ids = [r["id"] for r in response.json()["data"]]
    assert ids == ["run-2", "run-1"]


async def test_list_runs_pagination_rejects_unknown_sort_field(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get("/api/v1/global-markets/runs?sort=nonexistent", headers=auth_headers)
    assert response.status_code == 422


# --- /runs/latest -----------------------------------------------------------


async def test_get_latest_run_returns_404_when_nothing_stored(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get("/api/v1/global-markets/runs/latest", headers=auth_headers)
    assert response.status_code == 404


async def test_get_latest_run_returns_the_most_recent(
    client: TestClient, auth_headers: dict[str, str], global_market_run_repository: PostgresGlobalMarketRunRepository
) -> None:
    await global_market_run_repository.create_run(_run("run-1", date(2026, 8, 27)))
    await global_market_run_repository.create_run(_run("run-2", date(2026, 8, 29)))

    response = client.get("/api/v1/global-markets/runs/latest", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["data"]["id"] == "run-2"


# --- /runs/{run_id} -----------------------------------------------------------


async def test_get_run_returns_404_for_unknown_id(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/api/v1/global-markets/runs/does-not-exist", headers=auth_headers)
    assert response.status_code == 404


async def test_get_run_returns_the_stored_run(
    client: TestClient, auth_headers: dict[str, str], global_market_run_repository: PostgresGlobalMarketRunRepository
) -> None:
    await global_market_run_repository.create_run(_run("run-1", date(2026, 8, 29)))

    response = client.get("/api/v1/global-markets/runs/run-1", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["data"]["run_date"] == "2026-08-29"


# --- /runs/{run_id}/ranked-assets -----------------------------------------------------------


async def test_list_ranked_assets_for_run_spans_every_category(
    client: TestClient,
    auth_headers: dict[str, str],
    global_market_ranked_asset_repository: PostgresRankedAssetRepository,
) -> None:
    await global_market_ranked_asset_repository.replace_ranked_assets(
        "run-1", ReportCategory.US_EQUITY, (_ranked_asset("run-1", ReportCategory.US_EQUITY, "AAPL", 1),)
    )
    await global_market_ranked_asset_repository.replace_ranked_assets(
        "run-1", ReportCategory.INDIA_EQUITY, (_ranked_asset("run-1", ReportCategory.INDIA_EQUITY, "RELIANCE", 1),)
    )

    response = client.get("/api/v1/global-markets/runs/run-1/ranked-assets", headers=auth_headers)

    assert response.status_code == 200
    tickers = {a["snapshot"]["ticker"] for a in response.json()["data"]}
    assert tickers == {"AAPL", "RELIANCE"}


# --- /runs/{run_id}/categories/{category}/ranked-assets -----------------------------------------------------------


async def test_list_ranked_assets_for_category_orders_by_rank(
    client: TestClient,
    auth_headers: dict[str, str],
    global_market_ranked_asset_repository: PostgresRankedAssetRepository,
) -> None:
    await global_market_ranked_asset_repository.replace_ranked_assets(
        "run-1",
        ReportCategory.US_EQUITY,
        (
            _ranked_asset("run-1", ReportCategory.US_EQUITY, "MSFT", 2),
            _ranked_asset("run-1", ReportCategory.US_EQUITY, "AAPL", 1),
        ),
    )

    response = client.get(
        "/api/v1/global-markets/runs/run-1/categories/US_EQUITY/ranked-assets", headers=auth_headers
    )

    assert response.status_code == 200
    tickers = [a["snapshot"]["ticker"] for a in response.json()["data"]]
    assert tickers == ["AAPL", "MSFT"]


async def test_ranked_assets_response_exposes_performance_windows(
    client: TestClient,
    auth_headers: dict[str, str],
    global_market_ranked_asset_repository: PostgresRankedAssetRepository,
) -> None:
    window = WindowedPerformance(
        window=PerformanceWindow.Y5,
        start_value=10.0,
        end_value=34.0,
        percent_change=240.0,
        observation_start=_NOW,
        observation_end=_NOW,
        periods_used=1250,
        is_complete=True,
    )
    await global_market_ranked_asset_repository.replace_ranked_assets(
        "run-1",
        ReportCategory.US_EQUITY,
        (_ranked_asset("run-1", ReportCategory.US_EQUITY, "AAPL", 1, performance_windows=(window,)),),
    )

    response = client.get(
        "/api/v1/global-markets/runs/run-1/categories/US_EQUITY/ranked-assets", headers=auth_headers
    )

    assert response.status_code == 200
    windows = response.json()["data"][0]["performance_windows"]
    assert windows[0]["window"] == "5Y"
    assert windows[0]["percent_change"] == 240.0


async def test_list_ranked_assets_for_category_only_returns_that_category(
    client: TestClient,
    auth_headers: dict[str, str],
    global_market_ranked_asset_repository: PostgresRankedAssetRepository,
) -> None:
    await global_market_ranked_asset_repository.replace_ranked_assets(
        "run-1", ReportCategory.US_EQUITY, (_ranked_asset("run-1", ReportCategory.US_EQUITY, "AAPL", 1),)
    )
    await global_market_ranked_asset_repository.replace_ranked_assets(
        "run-1", ReportCategory.INDIA_EQUITY, (_ranked_asset("run-1", ReportCategory.INDIA_EQUITY, "RELIANCE", 1),)
    )

    response = client.get(
        "/api/v1/global-markets/runs/run-1/categories/INDIA_EQUITY/ranked-assets", headers=auth_headers
    )

    assert response.status_code == 200
    tickers = [a["snapshot"]["ticker"] for a in response.json()["data"]]
    assert tickers == ["RELIANCE"]


def test_list_ranked_assets_for_category_rejects_an_invalid_category(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get(
        "/api/v1/global-markets/runs/run-1/categories/NOT_A_CATEGORY/ranked-assets", headers=auth_headers
    )
    assert response.status_code == 422


# --- /runs/{run_id}/reports and /categories/{category}/report -----------------------------------------


async def test_list_reports_for_run(
    client: TestClient,
    auth_headers: dict[str, str],
    global_market_report_repository: PostgresIntelligenceReportRepository,
) -> None:
    await global_market_report_repository.save_report(_report("run-1", ReportCategory.US_EQUITY))
    await global_market_report_repository.save_report(_report("run-1", ReportCategory.INDIA_EQUITY))

    response = client.get("/api/v1/global-markets/runs/run-1/reports", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["total"] == 2


async def test_get_report_for_category_returns_404_when_missing(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get(
        "/api/v1/global-markets/runs/run-1/categories/US_EQUITY/report", headers=auth_headers
    )
    assert response.status_code == 404


async def test_get_report_for_category_returns_the_stored_report(
    client: TestClient,
    auth_headers: dict[str, str],
    global_market_report_repository: PostgresIntelligenceReportRepository,
) -> None:
    await global_market_report_repository.save_report(
        _report("run-1", ReportCategory.US_EQUITY, overall_summary="Momentum led by large caps.")
    )

    response = client.get(
        "/api/v1/global-markets/runs/run-1/categories/US_EQUITY/report", headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json()["data"]["overall_summary"] == "Momentum led by large caps."


# --- Repository unavailable -----------------------------------------------------------


def test_returns_503_when_repository_not_configured(
    client: TestClient, auth_headers: dict[str, str], app
) -> None:
    app.state.global_market_run_repository = None

    response = client.get("/api/v1/global-markets/runs", headers=auth_headers)

    assert response.status_code == 503
