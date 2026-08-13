"""Unit tests for KnowledgeHub.

Uses a mocked CompositeKnowledgeRepository only — no PostgreSQL, ChromaDB,
or SQLite is required anywhere in this file.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.knowledge.hub import KnowledgeHub
from app.knowledge.models import KnowledgeSearchFilters
from app.repositories.knowledge.composite.repository import CompositeKnowledgeRepository
from app.repositories.knowledge.models import KnowledgeRecord, SearchResult


def _mock_repository() -> AsyncMock:
    return AsyncMock(spec=CompositeKnowledgeRepository)


def _search_result(record_id: str) -> SearchResult:
    return SearchResult(id=record_id, score=1.0, text="text", metadata={})


def _knowledge_record(record_id: str) -> KnowledgeRecord:
    return KnowledgeRecord(id=record_id, title=f"Title {record_id}", source_provider_id="rss")


# --- Semantic query routing tests -----------------------------------------------------------


async def test_query_calls_repository_search_with_semantic_true() -> None:
    repo = _mock_repository()
    repo.search.return_value = []
    hub = KnowledgeHub(repo)

    await hub.query("Apple earnings", top_k=3)

    repo.search.assert_awaited_once()
    called_query = repo.search.call_args.args[0]
    assert called_query.semantic is True
    assert called_query.query_text == "Apple earnings"
    assert called_query.top_k == 3


async def test_query_returns_resolved_knowledge_records() -> None:
    repo = _mock_repository()
    repo.search.return_value = [_search_result("rec-1"), _search_result("rec-2")]
    repo.get.side_effect = lambda record_id: _knowledge_record(record_id)
    hub = KnowledgeHub(repo)

    records = await hub.query("Apple earnings")

    assert [r.id for r in records] == ["rec-1", "rec-2"]
    assert all(isinstance(r, KnowledgeRecord) for r in records)


async def test_query_never_returns_search_result_type() -> None:
    repo = _mock_repository()
    repo.search.return_value = [_search_result("rec-1")]
    repo.get.return_value = _knowledge_record("rec-1")
    hub = KnowledgeHub(repo)

    records = await hub.query("Apple earnings")

    assert not any(isinstance(r, SearchResult) for r in records)


# --- Structured query routing tests -----------------------------------------------------------


async def test_search_with_company_filter_routes_structured() -> None:
    repo = _mock_repository()
    repo.search.return_value = []
    hub = KnowledgeHub(repo)

    await hub.search(KnowledgeSearchFilters(company="Apple"))

    called_query = repo.search.call_args.args[0]
    assert called_query.semantic is False
    assert called_query.filters == {"company": "Apple"}


async def test_search_with_provider_and_source_filters_routes_structured() -> None:
    repo = _mock_repository()
    repo.search.return_value = []
    hub = KnowledgeHub(repo)

    await hub.search(KnowledgeSearchFilters(provider="rss", source="Reuters"))

    called_query = repo.search.call_args.args[0]
    assert called_query.semantic is False
    assert called_query.filters == {"provider": "rss", "source": "Reuters"}


async def test_search_with_date_range_filters_routes_structured() -> None:
    repo = _mock_repository()
    repo.search.return_value = []
    hub = KnowledgeHub(repo)

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 12, 31, tzinfo=timezone.utc)
    await hub.search(KnowledgeSearchFilters(start_date=start, end_date=end))

    called_query = repo.search.call_args.args[0]
    assert called_query.semantic is False
    assert called_query.filters == {"start_date": start, "end_date": end}


async def test_search_with_no_structured_filters_routes_semantic() -> None:
    repo = _mock_repository()
    repo.search.return_value = []
    hub = KnowledgeHub(repo)

    await hub.search(KnowledgeSearchFilters())

    called_query = repo.search.call_args.args[0]
    assert called_query.semantic is True
    assert called_query.filters == {}


async def test_search_passes_top_k_through() -> None:
    repo = _mock_repository()
    repo.search.return_value = []
    hub = KnowledgeHub(repo)

    await hub.search(KnowledgeSearchFilters(company="Apple", top_k=20))

    called_query = repo.search.call_args.args[0]
    assert called_query.top_k == 20


# --- get_by_id tests -----------------------------------------------------------


async def test_get_by_id_delegates_to_repository_get() -> None:
    repo = _mock_repository()
    repo.get.return_value = _knowledge_record("rec-1")
    hub = KnowledgeHub(repo)

    record = await hub.get_by_id("rec-1")

    repo.get.assert_awaited_once_with("rec-1")
    assert record is not None
    assert record.id == "rec-1"


async def test_get_by_id_returns_none_when_not_found() -> None:
    repo = _mock_repository()
    repo.get.return_value = None
    hub = KnowledgeHub(repo)

    assert await hub.get_by_id("does-not-exist") is None


# --- Empty results tests -----------------------------------------------------------


async def test_query_with_no_results_returns_empty_list() -> None:
    repo = _mock_repository()
    repo.search.return_value = []
    hub = KnowledgeHub(repo)

    assert await hub.query("nothing relevant") == []


async def test_search_with_no_results_returns_empty_list() -> None:
    repo = _mock_repository()
    repo.search.return_value = []
    hub = KnowledgeHub(repo)

    assert await hub.search(KnowledgeSearchFilters(company="Nonexistent")) == []


# --- Invalid filter validation tests -----------------------------------------------------------


def test_filters_reject_start_date_after_end_date() -> None:
    with pytest.raises(ValidationError):
        KnowledgeSearchFilters(
            start_date=datetime(2026, 12, 31, tzinfo=timezone.utc),
            end_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )


def test_filters_reject_non_positive_top_k() -> None:
    with pytest.raises(ValidationError):
        KnowledgeSearchFilters(top_k=0)


def test_filters_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        KnowledgeSearchFilters(unexpected_field="x")


def test_filters_accept_a_valid_date_range() -> None:
    filters = KnowledgeSearchFilters(
        start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 12, 31, tzinfo=timezone.utc),
    )
    assert filters.start_date is not None
    assert filters.end_date is not None


# --- Repository exception propagation tests -----------------------------------------------------------


async def test_query_propagates_repository_exception() -> None:
    repo = _mock_repository()
    repo.search.side_effect = RuntimeError("repository unavailable")
    hub = KnowledgeHub(repo)

    with pytest.raises(RuntimeError, match="repository unavailable"):
        await hub.query("Apple")


async def test_search_propagates_repository_exception() -> None:
    repo = _mock_repository()
    repo.search.side_effect = RuntimeError("repository unavailable")
    hub = KnowledgeHub(repo)

    with pytest.raises(RuntimeError, match="repository unavailable"):
        await hub.search(KnowledgeSearchFilters(company="Apple"))


async def test_get_by_id_propagates_repository_exception() -> None:
    repo = _mock_repository()
    repo.get.side_effect = RuntimeError("repository unavailable")
    hub = KnowledgeHub(repo)

    with pytest.raises(RuntimeError, match="repository unavailable"):
        await hub.get_by_id("rec-1")


async def test_query_propagates_exception_from_record_resolution() -> None:
    """If get() fails while resolving search results into full records,
    that failure must propagate too, not be swallowed."""
    repo = _mock_repository()
    repo.search.return_value = [_search_result("rec-1")]
    repo.get.side_effect = RuntimeError("repository unavailable")
    hub = KnowledgeHub(repo)

    with pytest.raises(RuntimeError, match="repository unavailable"):
        await hub.query("Apple")
