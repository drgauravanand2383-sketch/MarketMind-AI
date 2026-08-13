"""Tests for app.operations.migrations.discovery: the single collection
point Alembic's env.py and StartupValidationService's "model metadata
discovery" check both consume."""

from __future__ import annotations

from sqlalchemy import MetaData

from app.operations.migrations.discovery import (
    collect_metadata,
    collect_table_names,
    duplicate_table_names,
)


def test_collect_metadata_returns_one_entry_per_repository_package() -> None:
    metadata = collect_metadata()
    assert len(metadata) == 10
    assert all(isinstance(m, MetaData) for m in metadata)


def test_collect_table_names_is_non_empty() -> None:
    names = collect_table_names()
    assert len(names) > 0


def test_collect_table_names_includes_known_tables() -> None:
    names = collect_table_names()
    assert "recommendation_results" in names
    assert "risk_assessments" in names
    assert "backtest_requests" in names
    assert "explainability_results" in names


def test_collect_table_names_is_sorted() -> None:
    names = collect_table_names()
    assert list(names) == sorted(names)


def test_collect_table_names_is_deterministic_across_calls() -> None:
    assert collect_table_names() == collect_table_names()


def test_duplicate_table_names_is_empty_for_the_real_schema() -> None:
    """Every repository package's own table names must not collide with
    another package's — a genuine startup-safety property, not just a
    circumstantial fact about today's schema."""
    assert duplicate_table_names() == ()


def test_no_table_name_appears_in_two_different_packages() -> None:
    seen: set[str] = set()
    for metadata in collect_metadata():
        for table_name in metadata.tables:
            assert table_name not in seen, f"{table_name!r} is claimed by more than one repository package"
            seen.add(table_name)
