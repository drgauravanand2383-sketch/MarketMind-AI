"""Tests for PostgresIntelligenceReportRepository.

Run against an in-memory SQLite database via aiosqlite.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.global_markets.intelligence_report import AssetCommentary, CategoryIntelligenceReport
from app.global_markets.models import ReportCategory
from app.repositories.global_markets.postgres.models import Base
from app.repositories.global_markets.postgres.report_repository import PostgresIntelligenceReportRepository

NOW = datetime(2026, 8, 31, 9, 0, tzinfo=UTC)


@pytest.fixture
async def repository() -> AsyncIterator[PostgresIntelligenceReportRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PostgresIntelligenceReportRepository(session_factory)
    finally:
        await engine.dispose()


def _report(
    run_id: str = "run-1", category: ReportCategory = ReportCategory.US_EQUITY, **overrides: object
) -> CategoryIntelligenceReport:
    defaults: dict[str, object] = {
        "run_id": run_id,
        "category": category,
        "generated_at": NOW,
        "overall_summary": "A quiet session overall.",
        "asset_commentaries": (AssetCommentary(ticker="AAPL", rank=1, commentary="Led the category."),),
        "provider": "anthropic",
        "model": "claude-sonnet-5",
    }
    defaults.update(overrides)
    return CategoryIntelligenceReport(**defaults)  # type: ignore[arg-type]


# --- save_report / get_report -----------------------------------------------------------


async def test_save_then_get_returns_it(repository: PostgresIntelligenceReportRepository) -> None:
    await repository.save_report(_report())

    fetched = await repository.get_report("run-1", ReportCategory.US_EQUITY)

    assert fetched is not None
    assert fetched.overall_summary == "A quiet session overall."
    assert fetched.asset_commentaries[0].ticker == "AAPL"


async def test_get_report_missing_returns_none(repository: PostgresIntelligenceReportRepository) -> None:
    assert await repository.get_report("run-1", ReportCategory.US_EQUITY) is None


async def test_risk_note_round_trips_when_present(repository: PostgresIntelligenceReportRepository) -> None:
    await repository.save_report(_report(risk_note="Limited data confidence."))

    fetched = await repository.get_report("run-1", ReportCategory.US_EQUITY)

    assert fetched is not None
    assert fetched.risk_note == "Limited data confidence."


async def test_risk_note_is_none_when_not_set(repository: PostgresIntelligenceReportRepository) -> None:
    await repository.save_report(_report())

    fetched = await repository.get_report("run-1", ReportCategory.US_EQUITY)

    assert fetched is not None
    assert fetched.risk_note is None


# --- Upsert semantics: saving again overwrites, never duplicates -----------------------------------


async def test_saving_again_overwrites_the_previous_report(repository: PostgresIntelligenceReportRepository) -> None:
    await repository.save_report(_report(overall_summary="First version."))

    await repository.save_report(_report(overall_summary="Second version."))

    fetched = await repository.get_report("run-1", ReportCategory.US_EQUITY)
    assert fetched is not None
    assert fetched.overall_summary == "Second version."


async def test_saving_again_does_not_create_a_second_row(repository: PostgresIntelligenceReportRepository) -> None:
    await repository.save_report(_report())
    await repository.save_report(_report())

    reports = await repository.list_reports_for_run("run-1")
    assert len(reports) == 1


async def test_saving_a_different_category_does_not_overwrite_another(
    repository: PostgresIntelligenceReportRepository,
) -> None:
    await repository.save_report(_report(category=ReportCategory.US_EQUITY))
    await repository.save_report(
        _report(
            category=ReportCategory.INDIA_EQUITY,
            asset_commentaries=(AssetCommentary(ticker="RELIANCE", rank=1, commentary="Led."),),
        )
    )

    us = await repository.get_report("run-1", ReportCategory.US_EQUITY)
    india = await repository.get_report("run-1", ReportCategory.INDIA_EQUITY)
    assert us is not None
    assert india is not None
    assert us.asset_commentaries[0].ticker == "AAPL"
    assert india.asset_commentaries[0].ticker == "RELIANCE"


async def test_saving_a_different_run_does_not_overwrite_another(
    repository: PostgresIntelligenceReportRepository,
) -> None:
    await repository.save_report(_report(run_id="run-1"))
    await repository.save_report(_report(run_id="run-2", overall_summary="Different run."))

    run1 = await repository.get_report("run-1", ReportCategory.US_EQUITY)
    run2 = await repository.get_report("run-2", ReportCategory.US_EQUITY)
    assert run1 is not None
    assert run2 is not None
    assert run1.overall_summary == "A quiet session overall."
    assert run2.overall_summary == "Different run."


# --- list_reports_for_run -----------------------------------------------------------


async def test_list_reports_for_run_spans_every_category(repository: PostgresIntelligenceReportRepository) -> None:
    await repository.save_report(_report(category=ReportCategory.US_EQUITY))
    await repository.save_report(_report(category=ReportCategory.INDIA_EQUITY))

    reports = await repository.list_reports_for_run("run-1")

    assert {r.category for r in reports} == {ReportCategory.US_EQUITY, ReportCategory.INDIA_EQUITY}


async def test_list_reports_for_run_excludes_other_runs(repository: PostgresIntelligenceReportRepository) -> None:
    await repository.save_report(_report(run_id="run-1"))
    await repository.save_report(_report(run_id="run-2"))

    reports = await repository.list_reports_for_run("run-1")

    assert len(reports) == 1


async def test_list_reports_for_run_empty_when_nothing_stored(
    repository: PostgresIntelligenceReportRepository,
) -> None:
    assert await repository.list_reports_for_run("run-1") == []


# --- health_check -----------------------------------------------------------


async def test_health_check_true_against_reachable_database(
    repository: PostgresIntelligenceReportRepository,
) -> None:
    assert await repository.health_check() is True


async def test_health_check_false_when_database_unreachable() -> None:
    broken_engine = create_async_engine("sqlite+aiosqlite:///nonexistent/no/such/path.db")
    session_factory = async_sessionmaker(broken_engine, expire_on_commit=False)

    repository = PostgresIntelligenceReportRepository(session_factory)

    assert await repository.health_check() is False
