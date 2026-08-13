"""Composite Knowledge Repository.

CompositeKnowledgeRepository coordinates one PostgresKnowledgeRepository
and one ChromaKnowledgeRepository behind a single BaseKnowledgeRepository
interface, so callers never need to know which storage backend handles
which concern. It contains no SQL, no ChromaDB API calls, no business
logic, and no AI — every operation is delegated to the owned repository
that already implements it; this class only routes requests and combines
results.
"""

from __future__ import annotations

from app.repositories.knowledge.chroma.repository import ChromaKnowledgeRepository
from app.repositories.knowledge.models import (
    DeleteResult,
    KnowledgeRecord,
    SaveResult,
    SearchQuery,
    SearchResult,
)
from app.repositories.knowledge.postgres.repository import PostgresKnowledgeRepository
from app.repositories.knowledge.repository import BaseKnowledgeRepository
from app.services.embedding.models import EmbeddingBatch
from app.services.knowledge_ingestion.models import IngestionBatch

__all__ = ["CompositeKnowledgeRepository"]


class CompositeKnowledgeRepository(BaseKnowledgeRepository):
    """Transparently coordinates PostgreSQL and ChromaDB behind one interface.

    Callers interact with this repository exactly like any other
    BaseKnowledgeRepository implementation — they never see which
    underlying store handled a given call, and no storage-specific
    behavior (SQL, ChromaDB collection calls) leaks through this class.
    """

    def __init__(
        self,
        postgres_repository: PostgresKnowledgeRepository,
        chroma_repository: ChromaKnowledgeRepository,
    ) -> None:
        """Initialize the repository.

        Args:
            postgres_repository: The relational (PostgreSQL) repository,
                injected by the caller. Owns `relational_records` and
                structured (non-semantic) search.
            chroma_repository: The vector (ChromaDB) repository, injected
                by the caller. Owns `vector_documents` and semantic search.
        """
        self._postgres = postgres_repository
        self._chroma = chroma_repository

    async def save_batch(
        self, ingestion_batch: IngestionBatch, embedding_batch: EmbeddingBatch
    ) -> SaveResult:
        """Save relational_records to PostgreSQL and vector_documents to
        ChromaDB, then combine both outcomes into one unified SaveResult.

        Each backend is saved to independently: a failure in one does not
        prevent the other from being attempted, and both backends'
        errors (if any) are reported together.
        """
        postgres_result = await self._postgres.save_batch(ingestion_batch, embedding_batch)
        chroma_result = await self._chroma.save_batch(ingestion_batch, embedding_batch)

        return SaveResult(
            batch_id=ingestion_batch.ingestion_metadata.batch_id,
            saved_at=chroma_result.saved_at,
            vector_count=chroma_result.vector_count,
            relational_count=postgres_result.relational_count,
            success=postgres_result.success and chroma_result.success,
            errors=[*postgres_result.errors, *chroma_result.errors],
        )

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        """Route to ChromaDB when `query.semantic` is True, PostgreSQL otherwise.

        Both backends return the same SearchResult shape, so callers never
        see which one actually served the request.
        """
        if query.semantic:
            return await self._chroma.search(query)
        return await self._postgres.search(query)

    async def get(self, record_id: str) -> KnowledgeRecord | None:
        """Retrieve the structured record from PostgreSQL, or None if unavailable."""
        return await self._postgres.get(record_id)

    async def delete(self, record_id: str) -> DeleteResult:
        """Delete `record_id` from both repositories, returning one DeleteResult.

        `deleted` is True if the record existed in either store — a
        caller asking "was this deleted" should get True whenever there
        was anything to remove anywhere in the system, not only when both
        backends happened to have a copy.

        Unlike `save_batch`, a backend failure here is not caught: unlike
        SaveResult, DeleteResult has no `errors` field to represent a
        partial failure, so silently swallowing an exception would
        produce a falsely successful-looking result. If either backend
        raises, this method raises.
        """
        postgres_result = await self._postgres.delete(record_id)
        chroma_result = await self._chroma.delete(record_id)

        return DeleteResult(
            id=record_id, deleted=postgres_result.deleted or chroma_result.deleted
        )

    async def health_check(self) -> bool:
        """Healthy only if both PostgreSQL and ChromaDB are healthy."""
        postgres_healthy = await self._postgres.health_check()
        chroma_healthy = await self._chroma.health_check()
        return postgres_healthy and chroma_healthy
