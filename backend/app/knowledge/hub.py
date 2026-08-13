"""Production KnowledgeHub — the retrieval service agents use.

KnowledgeHub implements KnowledgeHubInterface (the abstraction
AgentRuntime already depends on, Sprint 5) by delegating every retrieval
to an injected CompositeKnowledgeRepository. It performs no reasoning, no
summarization, no ranking beyond whatever order the repository already
returns, no caching, and no persistence — it exists purely to hide
repository implementation details behind one clean interface for agents.
It communicates only with CompositeKnowledgeRepository: no SQLAlchemy, no
ChromaDB, no direct PostgreSQL or ChromaDB access anywhere in this module.
"""

from __future__ import annotations

from app.core.runtime import KnowledgeHubInterface
from app.knowledge.models import KnowledgeSearchFilters
from app.repositories.knowledge.composite.repository import CompositeKnowledgeRepository
from app.repositories.knowledge.models import KnowledgeRecord, SearchQuery, SearchResult

__all__ = ["KnowledgeHub"]


class KnowledgeHub(KnowledgeHubInterface):
    """The production knowledge retrieval service backing AgentRuntime.knowledge_hub.

    Every method here does exactly one thing: translate a caller's
    request into a SearchQuery, delegate to the injected
    CompositeKnowledgeRepository, and return KnowledgeRecord objects. No
    repository-specific type (SearchResult, ORM models, ChromaDB
    collections) is ever returned to a caller.
    """

    def __init__(self, repository: CompositeKnowledgeRepository) -> None:
        """Initialize the hub.

        Args:
            repository: The CompositeKnowledgeRepository this hub
                delegates every retrieval to, injected by the caller.
                KnowledgeHub never constructs its own repository and
                never talks to PostgreSQL or ChromaDB directly.
        """
        self._repository = repository

    async def query(self, query: str, top_k: int = 5) -> list[KnowledgeRecord]:
        """Natural-language retrieval — always routed to semantic search.

        Satisfies KnowledgeHubInterface's required method.
        """
        search_query = SearchQuery(query_text=query, top_k=top_k, semantic=True)
        results = await self._repository.search(search_query)
        return await self._resolve_records(results)

    async def search(self, filters: KnowledgeSearchFilters) -> list[KnowledgeRecord]:
        """Structured retrieval when any structured filter is present.

        Routing: if `filters` sets any of company/provider/source/
        start_date/end_date, this performs structured retrieval
        (SearchQuery(semantic=False)) using exactly those filters. If none
        are set, it falls back to semantic retrieval
        (SearchQuery(semantic=True)) with no query text — the repository's
        own default ordering applies.
        """
        search_query = self._build_search_query(filters)
        results = await self._repository.search(search_query)
        return await self._resolve_records(results)

    async def get_by_id(self, knowledge_id: str) -> KnowledgeRecord | None:
        """Retrieve a single KnowledgeRecord by id, or None if not found."""
        return await self._repository.get(knowledge_id)

    def _build_search_query(self, filters: KnowledgeSearchFilters) -> SearchQuery:
        """Translate KnowledgeSearchFilters into a SearchQuery, deciding routing."""
        structured_filters: dict[str, object] = {}
        if filters.company is not None:
            structured_filters["company"] = filters.company
        if filters.provider is not None:
            structured_filters["provider"] = filters.provider
        if filters.source is not None:
            structured_filters["source"] = filters.source
        if filters.start_date is not None:
            structured_filters["start_date"] = filters.start_date
        if filters.end_date is not None:
            structured_filters["end_date"] = filters.end_date

        has_structured_filter = bool(structured_filters)
        return SearchQuery(
            filters=structured_filters,
            top_k=filters.top_k,
            semantic=not has_structured_filter,
        )

    async def _resolve_records(self, results: list[SearchResult]) -> list[KnowledgeRecord]:
        """Resolve SearchResults into full KnowledgeRecords via get(), preserving order.

        CompositeKnowledgeRepository.search() returns SearchResult (id,
        score, text, metadata) — a repository-specific shape.
        KnowledgeHub never returns that type to callers; it always
        resolves to the full KnowledgeRecord so every caller sees one
        consistent model regardless of which backend served the request.
        A result whose full record can no longer be fetched is skipped,
        not treated as an error.
        """
        records: list[KnowledgeRecord] = []
        for result in results:
            record = await self._repository.get(result.id)
            if record is not None:
                records.append(record)
        return records
